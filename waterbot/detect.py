"""畫面狀態判讀：把一張遊戲截圖變成 (狀態, 要點哪裡)。

設計原則
--------
1. 只靠 OCR 文字判斷，不靠圖片模板 —— 遊戲改版換美術也不會壞。
2. 文字比對採「幾乎精確」而非「包含」。實測踩過：攻略影片的字幕
   「那開戰進來」被當成「開戰」按鈕。只允許 OCR 多認一兩個雜字，
   不接受整句話。
3. **按鈕座標一律用 OCR 真正讀到的位置，絕不用推算的。**
   勝利畫面上「返回」和「下一關」同高、只差 143px，猜錯就等於退出關卡。
   讀不到按鈕就回報 NEEDS_HUMAN，寧可停下來。

畫面文字都是從真實遊戲畫面確認過的，不是猜的：
  失敗 = 「戰鬥失敗」+「再戰一次」
  勝利 = 「挑戰勝利」+「下一關」（左邊還有一顆「返回」）
"""
import re
from dataclasses import dataclass

STAGE_RE = re.compile(r"第\s*(\d+)\s*關")
COUNTDOWN_RE = re.compile(r"(\d+)\s*秒後可跳過")

# 同一顆按鈕 / 標題在不同版本或 OCR 誤認下的各種寫法
# 每一組都是「正式寫法」加上實測看過的 OCR 誤認寫法。
# 新增變體前請先確認那串字真的出現在該按鈕上（查 out/run.log 的 OCR 內容），
# 不要加入可能出現在別處的真實詞彙 ——「下一页」「下一级」就是反例。
DEFEAT_BANNER = ("戰鬥失敗", "战斗失败", "戰鬪失敗", "戦鬥失敗")
RETRY_BTN     = ("再戰一次", "再战一次", "再戟一次", "再戰一攻")
VICTORY_BANNER = ("挑戰勝利", "挑战胜利", "戰鬥勝利", "战斗胜利",
                  "挑戰成功", "挑战成功")
NEXT_BTN      = ("下一關", "下一关", "下一闕", "下一闢", "下一關",
                 "繼續挑戰", "继续挑战")
SKIP_BTN      = ("跳過", "跳过")
START_BTN     = ("開戰", "开战", "開戦")
MAIN_BTN      = ("闖關", "闯关")

# 主畫面左下角那排導覽列的「闖關」。這顆按鈕跟別的不一樣：主畫面上
# 還有「商城」和「首充」，點錯就是儲值頁。所以除了文字要對，還要求
# 它真的出現在左下角 —— 實測主畫面上「闖關」在 (0.09, 0.99)，
# 而「商城」在 (0.93, 0.19)、「首充」在 (0.93, 0.58)，離得夠遠。
# 範圍放寬是為了容納不同視窗比例；即使判斷失準也只是不點，不會點錯。
MAIN_BTN_REGION = (0.00, 0.35, 0.90, 1.00)   # x_min, x_max, y_min, y_max（比例）


def _norm(s: str) -> str:
    """去掉 OCR 常見雜訊字元，只留中日文與英數。"""
    return re.sub(r"[^一-鿿0-9A-Za-z]", "", s or "")


@dataclass
class Screen:
    state: str
    click: tuple | None = None   # (x, y) 截圖像素座標
    stage: int | None = None
    note: str = ""
    countdown: int | None = None  # 戰鬥中「還要幾秒才能跳過」，給主迴圈排程用


def _close(text_norm: str, key: str, slack: int) -> bool:
    """文字是不是「就是」這個關鍵字（容許尾端倒數數字與少量雜字）。

    這裡刻意**不做模糊比對**。曾經試過「容許一個字不同」來吸收形近字誤認，
    結果在真實影片上造成兩類危險誤判：
      * 兩字關鍵字失控：「城战」「甙战」「提战」全被當成「开战」，
        其中兩次發生在 648 元的儲值畫面上。
      * 三字也一樣不安全：「下一页」「下一级」是真實詞彙，
        跟「下一關」只差最後一個字，被當成過關按鈕。

    所以改成只認下面各 *_BTN 清單裡明確列出的已知誤認寫法。
    沒見過的誤認會落到 UNKNOWN，程式不動作並把 OCR 內容寫進 log ——
    之後照 log 補一個變體進清單即可。寧可漏點，不可錯點。

    長度上限則是防止整句字幕（例如「那開戰進來」）被當成按鈕。
    """
    t = re.sub(r"\d+$", "", text_norm)
    if not t:
        return False
    return key in t and len(t) <= len(key) + slack


def _find(items, keys, slack=1):
    """找出文字「幾乎就是」某個關鍵字的項目。回傳 (text, cx, cy, conf) 或 None。"""
    best = None
    for text, cx, cy, conf in items:
        n = _norm(text)
        for k in keys:
            if _close(n, k, slack):
                if best is None or conf > best[3]:
                    best = (text, cx, cy, conf)
    return best


def _contains(items, *keys):
    """整句話裡含有關鍵字就算（給倒數提示那種句子用）。"""
    for it in items:
        n = _norm(it[0])
        if any(k in n for k in keys):
            return it
    return None


def classify(ocr_items, w, h) -> Screen:
    stage = None
    st = _contains(ocr_items, "關", "关")
    if st:
        m = STAGE_RE.search(_norm(st[0]))
        if m:
            stage = int(m.group(1))

    # 以「按鈕」為主要依據，不是標題橫幅。
    # 實測原因：橫幅是裝飾字體，OCR 常整個讀爛（「挑戰勝利」→「挑郫膀朻」），
    # 但同一張畫面上的按鈕是一般字體，信心值 1.00。按鈕才是可靠訊號。

    # 1. 失敗 → 再戰一次（這顆按鈕獨自置中，旁邊沒有別的按鈕）
    hit = _find(ocr_items, RETRY_BTN)
    if hit:
        return Screen("DEFEAT", (hit[1], hit[2]), stage, "")

    # 2. 勝利 → 下一關
    #    左邊約 180px 就是「返回」，所以位置只能用 OCR 讀到的，絕不推算。
    hit = _find(ocr_items, NEXT_BTN)
    if hit:
        return Screen("VICTORY", (hit[1], hit[2]), stage, "")

    # 3. 看得到結算橫幅卻讀不到按鈕 → 停下來讓人看，不要亂猜位置
    banner = _find(ocr_items, DEFEAT_BANNER) or _find(ocr_items, VICTORY_BANNER)
    if banner:
        return Screen("NEEDS_HUMAN", None, stage,
                      f"看到結算畫面「{banner[0]}」，但讀不到該點的按鈕")

    # 3. 戰鬥中，跳過鍵已出現 → 點跳過
    if not _contains(ocr_items, "秒後可跳過", "秒后可跳过"):
        hit = _find(ocr_items, SKIP_BTN)
        if hit:
            return Screen("SKIPPABLE", (hit[1], hit[2]), stage)

    # 4. 戰鬥中，跳過鍵還在倒數 → 等
    cd = _contains(ocr_items, "秒後可跳過", "秒后可跳过")
    if cd:
        m = COUNTDOWN_RE.search(_norm(cd[0]))
        secs = int(m.group(1)) if m else None
        return Screen("BATTLE", None, stage,
                      f"剩{secs}秒可跳過" if secs is not None else "",
                      countdown=secs)

    # 5. 關卡畫面 → 開戰
    hit = _find(ocr_items, START_BTN)
    if hit:
        return Screen("STAGE_SELECT", (hit[1], hit[2]), stage)

    # 6. 主畫面（基地）→ 左下角的「闖關」，進去才會看到開戰
    hit = _find(ocr_items, MAIN_BTN)
    if hit:
        x0, x1, y0, y1 = MAIN_BTN_REGION
        if x0 * w <= hit[1] <= x1 * w and y0 * h <= hit[2] <= y1 * h:
            return Screen("MAIN_MENU", (hit[1], hit[2]), stage)
        return Screen("UNKNOWN", None, stage,
                      f"看到「{hit[0]}」但不在左下角導覽列的位置，不敢點")

    # 6. 其他
    if _find(ocr_items, ("LOADING", "LOADINCL", "載入中", "加载中"), slack=3):
        return Screen("LOADING", None, stage)
    if _find(ocr_items, ("2倍速", "倍速"), slack=2):
        return Screen("BATTLE", None, stage, "只看到倍速鍵")
    return Screen("UNKNOWN", None, stage)
