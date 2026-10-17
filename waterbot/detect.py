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
DEFEAT_BANNER = ("戰鬥失敗", "战斗失败", "戰鬪失敗", "戦鬥失敗")
RETRY_BTN     = ("再戰一次", "再战一次", "再戟一次", "再戰一攻")
VICTORY_BANNER = ("挑戰勝利", "挑战胜利", "戰鬥勝利", "战斗胜利",
                  "挑戰成功", "挑战成功")
NEXT_BTN      = ("下一關", "下一关", "下一闢", "繼續挑戰", "继续挑战")
SKIP_BTN      = ("跳過", "跳过")
START_BTN     = ("開戰", "开战", "開戦")


def _norm(s: str) -> str:
    """去掉 OCR 常見雜訊字元，只留中日文與英數。"""
    return re.sub(r"[^一-鿿0-9A-Za-z]", "", s or "")


@dataclass
class Screen:
    state: str
    click: tuple | None = None   # (x, y) 截圖像素座標
    stage: int | None = None
    note: str = ""


def _close(text_norm: str, key: str, slack: int) -> bool:
    """文字是不是「幾乎就是」這個關鍵字。

    要容忍兩種實測踩過的狀況：
      * 形近字誤認：「下一關」被讀成「下一闕」、「再戰一次」讀成「再戟一次」
      * 按鈕上帶倒數：勝利畫面的按鈕其實是「下一關(4)」
    所以先砍掉尾端數字，再允許剛好一個字不一樣。
    但長度仍然卡死，才不會把整句字幕「那開戰進來」當成「開戰」按鈕。
    """
    t = re.sub(r"\d+$", "", text_norm)
    if not t:
        return False
    if key in t and len(t) <= len(key) + slack:
        return True
    if len(t) == len(key):
        diff = sum(1 for a, b in zip(t, key) if a != b)
        return diff <= 1
    return False


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
        return Screen("BATTLE", None, stage,
                      f"剩{m.group(1)}秒可跳過" if m else "")

    # 5. 關卡畫面 → 開戰
    hit = _find(ocr_items, START_BTN)
    if hit:
        return Screen("STAGE_SELECT", (hit[1], hit[2]), stage)

    # 6. 其他
    if _find(ocr_items, ("LOADING", "LOADINCL", "載入中", "加载中"), slack=3):
        return Screen("LOADING", None, stage)
    if _find(ocr_items, ("2倍速", "倍速"), slack=2):
        return Screen("BATTLE", None, stage, "只看到倍速鍵")
    return Screen("UNKNOWN", None, stage)
