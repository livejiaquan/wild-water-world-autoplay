"""城戰模式的畫面判讀：目標清單、城市彈窗、選擇艦隊視窗。

城戰（台灣時間 19:00–20:00）的流程：
    左側目標清單點「防守堡壘F2」→ 地圖跳過去 → 點城市 → 城市彈窗
    → 點按鈕 → 選擇艦隊 → 受損的按「維修」、完好空閒的勾選 → 出征

這裡只負責「看懂畫面」，不點任何東西。點擊與流程在主程式。

辨識準確度的做法
----------------
* 整張先粗讀一次，用「遠征艦隊」這幾個字定出每一列的位置。
* 每一列的狀態格再**裁出來放大三倍**重讀 —— 實測放大後
  空閒中／維修／倒數的信心值大多是 1.00。
* 「能不能出征」不只靠文字。艦船下方的黃色耐久條是純顏色判斷，
  跟 OCR 完全獨立；兩者都說完好才算完好，對不上就不出征。
"""
import re
from dataclasses import dataclass, field

import cv2
import numpy as np

from ocr import ocr

ZOOM = 3                   # 狀態格放大倍數
BAR_FULL = 0.97            # 耐久條比例 >= 這個才算滿。實測滿格 0.99、
                           # 最接近滿的未滿 0.93，中間留了足夠間隔
CHECK_MIN = 0.05           # 綠色勾勾佔比 >= 這個算已勾選（實測 0.12–0.14 vs 0）

TIMER_RE = re.compile(r"(\d{1,2})\s*[:：]\s*(\d{2})")


# --------------------------------------------------------------- 文字工具
def norm_code(s):
    """把目標代號正規化。OCR 會把 E1 讀成 EI、F0 讀成 FO。"""
    s = re.sub(r"\s+", "", s or "").upper()
    return s.replace("O", "0").replace("I", "1").replace("L", "1")


def split_target(name):
    """「防守堡壘F2」→ ("防守", "堡壘", "F2")。讀不出來回 None。"""
    s = re.sub(r"\s+", "", name or "")
    s = s.replace("堡量", "堡壘").replace("堡曡", "堡壘").replace("營池", "營地")
    m = re.search(r"(防守|進攻|进攻)?(堡壘|堡垒|營地|营地)([A-Za-z0-9]{1,3})$", s)
    if not m:
        return None
    side = {"进攻": "進攻"}.get(m.group(1), m.group(1))
    kind = {"堡垒": "堡壘", "营地": "營地"}.get(m.group(2), m.group(2))
    return side, kind, norm_code(m.group(3))


def same_target(a, b):
    """兩個目標名稱是否指同一個城市（只比類型和代號，忽略防守／進攻字樣）。"""
    ta, tb = split_target(a), split_target(b)
    return bool(ta and tb and ta[1:] == tb[1:])


# --------------------------------------------------------------- 艦隊列
@dataclass
class Fleet:
    index: int                    # 第幾列（1 起算）
    anchor_y: int                 # 「遠征艦隊」字樣的 y
    status: str                   # idle / garrison / battle / timer / unknown
    timer: int | None = None      # 倒數秒數（行軍、回程、維修中）
    repair_at: tuple | None = None  # 「維修」按鈕位置；None 代表沒看到
    bar: float | None = None      # 耐久條比例
    selected: bool = False        # 是否已勾選
    tap_at: tuple = (0, 0)        # 要勾選這支艦隊時點哪裡（艦船圖）
    raw: list = field(default_factory=list)  # 放大後 OCR 讀到的字，除錯用

    @property
    def needs_repair(self):
        return self.status == "idle" and self.repair_at is not None

    @property
    def ready(self):
        """可以出征：空閒、沒有維修鈕、耐久條確實是滿的。三者缺一不可。"""
        return (self.status == "idle" and self.repair_at is None
                and self.bar is not None and self.bar >= BAR_FULL)

    @property
    def disagree(self):
        """文字說完好但耐久條說沒滿（或反過來）。這種情況一律不出征。"""
        return (self.status == "idle" and self.repair_at is None
                and self.bar is not None and self.bar < BAR_FULL)


def _bar_fill(img, ay):
    """艦船下方黃色耐久條的填滿比例。

    只數「深色空槽」，其餘都算填滿。條的右端是淺黃漸層，
    用黃色門檻去數會漏掉而系統性偏低（實測滿格只量到 0.85）。
    """
    h, w = img.shape[:2]
    x0, x1 = int(0.04 * w), int(0.30 * w)
    y0, y1 = int(ay + 0.045 * h), int(ay + 0.10 * h)
    hsv = cv2.cvtColor(img[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    yellow = ((hsv[..., 0] >= 10) & (hsv[..., 0] <= 38)
              & (hsv[..., 1] >= 80) & (hsv[..., 2] >= 150))
    if yellow.sum() < 10:
        return None
    r = int(np.argmax(yellow.sum(axis=1)))          # 條的中線
    dark = hsv[r][:, 2] <= 90
    xs = np.where(dark | yellow[r])[0]
    if len(xs) < 10:
        return None
    left, right = xs[0] + 3, xs[-1] - 2              # 扣掉外框
    total = max(1, right - left)
    return 1.0 - dark[left:right].sum() / total


def _checked(img, ay):
    h, w = img.shape[:2]
    roi = img[int(ay - 0.035 * h):int(ay + 0.005 * h), int(0.03 * w):int(0.12 * w)]
    if roi.size == 0:
        return False
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    g = ((hsv[..., 0] >= 40) & (hsv[..., 0] <= 85)
         & (hsv[..., 1] >= 120) & (hsv[..., 2] >= 120))
    return g.mean() >= CHECK_MIN


def _read_row(img, ay, index, ocr_fn):
    h, w = img.shape[:2]
    y0, y1 = max(0, int(ay - 0.02 * h)), min(h, int(ay + 0.09 * h))
    x0, x1 = int(0.05 * w), int(0.97 * w)
    crop = cv2.resize(img[y0:y1, x0:x1], None, fx=ZOOM, fy=ZOOM,
                      interpolation=cv2.INTER_CUBIC)
    ch, cw = crop.shape[:2]
    items = ocr_fn(crop)

    status, timer, repair_at = "unknown", None, None
    for text, cx, cy, conf in items:
        t = re.sub(r"\s+", "", text)
        fx, fy = cx / cw, cy / ch
        if fy > 0.45:                       # 只看上半部（下半部是英雄頭像）
            continue
        gx = int(x0 + cx / ZOOM)
        gy = int(y0 + cy / ZOOM)
        if "維修" in t or "维修" in t:
            if fx > 0.84:                   # 按鈕在最右邊
                repair_at = (gx, gy)
            continue
        if fx < 0.68 or fx > 0.88:          # 狀態格大約在 0.79
            continue
        if "空閒" in t or "空間" in t or "空闲" in t:
            status = "idle"
        elif "駐防" in t or "驻防" in t:
            status = "garrison"
        elif "交戰" in t or "交战" in t:
            status = "battle"
        else:
            m = TIMER_RE.search(t)
            if m:
                status, timer = "timer", int(m.group(1)) * 60 + int(m.group(2))

    return Fleet(
        index=index, anchor_y=int(ay), status=status, timer=timer,
        repair_at=repair_at, bar=_bar_fill(img, ay),
        selected=_checked(img, ay),
        tap_at=(int(0.16 * w), int(ay + 0.035 * h)),
        raw=[i[0] for i in items])


# --------------------------------------------------------------- 整個畫面
@dataclass
class SiegeScreen:
    kind: str                     # fleets / city / map / unknown
    fleets: list = field(default_factory=list)
    send_at: tuple | None = None  # 「出征」
    close_at: tuple | None = None
    city: str | None = None       # 彈窗標題「城市：堡壘F2」裡的名稱
    buttons: dict = field(default_factory=dict)   # 城市彈窗的四顆鈕
    targets: dict = field(default_factory=dict)   # 左側清單：名稱 -> 位置
    toast: str | None = None      # 例如「未選擇任何艦隊」


def _find(items, *keys):
    for text, cx, cy, conf in items:
        t = re.sub(r"\s+", "", text)
        if any(k in t for k in keys):
            return (text, cx, cy, conf)
    return None


def read(img, items=None, ocr_fn=ocr):
    """判讀城戰相關畫面。items 是整張 OCR 結果（已經讀過就傳進來省一次）。"""
    h, w = img.shape[:2]
    items = items if items is not None else ocr_fn(img)

    toast = _find(items, "未選擇任何艦隊", "未选择任何舰队")

    # ---- 選擇艦隊視窗
    if _find(items, "選擇艦隊", "选择舰队"):
        anchors = sorted(y for t, x, y, c in items
                         if ("遠征" in t or "远征" in t) and 0.15 < y / h < 0.75)
        # 同一列可能被讀成兩段，距離太近的合併
        rows = []
        for y in anchors:
            if not rows or y - rows[-1] > 0.05 * h:
                rows.append(y)
        fleets = [_read_row(img, y, i + 1, ocr_fn) for i, y in enumerate(rows)]
        send = _find(items, "出征")
        return SiegeScreen(
            kind="fleets", fleets=fleets,
            send_at=(send[1], send[2]) if send else None,
            toast=toast[0] if toast else None)

    # ---- 城市彈窗
    title = _find(items, "城市：", "城市:")
    if title:
        name = re.split(r"[：:]", title[0], maxsplit=1)[-1].strip()
        buttons = {}
        for key in ("集結", "徵募", "守軍", "前往"):
            hit = _find([i for i in items if i[2] / h > 0.55], key)
            if hit:
                buttons[key] = (hit[1], hit[2])
        return SiegeScreen(kind="city", city=name, buttons=buttons)

    # ---- 地圖：讀左側目標清單
    # 整張讀會漏字：實測「防守堡壘E1」被讀成「防守堡壘E」，代號整個不見。
    # 把左邊那一條裁出來放大三倍重讀就正確了，所以清單一律放大讀。
    if not (_find(items, "城戰進行中", "城战进行中")
            or any(cx / w < 0.2 and split_target(t) for t, cx, cy, c in items)):
        return SiegeScreen(kind="unknown")
    return SiegeScreen(kind="map", targets=_read_target_list(img, ocr_fn))


# 同一塊清單用幾種不同的裁切寬度與放大倍率各讀一次。
# 實測五種組合裡有一種會把「E1」讀成「E」，換一種就讀對；
# 單一組合調不穩，所以多讀幾次互相補。
LIST_VARIANTS = ((0.17, 3), (0.22, 4), (0.22, 2))


def _read_target_list(img, ocr_fn):
    """讀左側目標清單，回傳 {名稱: 位置}。

    每個位置收集各次讀到的代號：
      * 讀到完整代號的採用，被截斷的（只有「E」）丟掉
      * 同一個位置讀出兩種不同的完整代號 = 不確定，整個位置不採用
    """
    h, w = img.shape[:2]
    y0, y1 = int(0.18 * h), int(0.75 * h)
    spots = []                                   # [[y, x, {名稱: 次數}]]
    for xr, z in LIST_VARIANTS:
        strip = cv2.resize(img[y0:y1, 0:int(xr * w)], None, fx=z, fy=z,
                           interpolation=cv2.INTER_CUBIC)
        for text, cx, cy, conf in ocr_fn(strip):
            t = split_target(text)
            if not t or len(t[2]) < 2:           # 代號被截斷就不算
                continue
            gx, gy = int(cx / z), int(y0 + cy / z)
            for s in spots:
                if abs(s[0] - gy) < 0.02 * h:
                    s[2][t] = s[2].get(t, 0) + 1
                    break
            else:
                spots.append([gy, gx, {t: 1}])

    targets = {}
    for gy, gx, seen in spots:
        codes = {t[1:] for t in seen}            # (類型, 代號)
        if len(codes) != 1:
            continue                             # 讀出互相矛盾的代號，不採用
        side, kind, code = max(seen, key=seen.get)
        targets[f"{side or ''}{kind}{code}"] = (gx, gy)
    return targets


# --------------------------------------------------------------- 決策
# 出現這些字代表畫面要花錢或加速。城戰模式一律不碰，遇到就停下來。
COST_WORDS = ("鑽石", "钻石", "加速", "花費", "花费", "購買", "购买", "立即完成")

SEND_BUTTON = "前往"      # 城市彈窗上派艦隊出去的那顆（使用者確認過）


@dataclass
class Action:
    kind: str                     # tap / wait / stop / reset
    at: tuple | None = None       # tap 的位置（截圖像素）
    seconds: float = 0.0          # wait 多久
    why: str = ""


def plan(screen, target, items=()):
    """看目前畫面，決定**下一個**動作。一次只回一個，做完要重新看畫面。

    原則：
      * 只點這幾種東西：清單上的目標、標題吻合的城市彈窗的「前往」、
        「維修」、艦隊列（勾選或取消勾選）、「出征」。其餘一律不點。
      * 維修只按「維修」，從不加速、不花鑽石。
      * 只有完好（空閒＋沒有維修鈕＋耐久條滿）的艦隊會被派出去。
    """
    for text, *_ in items:
        if any(w in text for w in COST_WORDS):
            return Action("stop", why=f"畫面出現「{text.strip()}」，可能要花錢，停下來")

    if screen.kind == "fleets":
        for f in screen.fleets:
            if f.needs_repair:
                return Action("tap", f.repair_at, why=f"第 {f.index} 支受損，按維修")
        # 已勾選但沒準備好的先取消，免得按出征時把它一起送出去
        for f in screen.fleets:
            if f.selected and not f.ready:
                return Action("tap", f.tap_at,
                              why=f"第 {f.index} 支還沒準備好卻被勾著，取消勾選")
        for f in screen.fleets:
            if f.ready and not f.selected:
                return Action("tap", f.tap_at,
                              why=f"第 {f.index} 支完好空閒（耐久 {f.bar:.2f}），勾選")
        if any(f.ready and f.selected for f in screen.fleets) and screen.send_at:
            n = sum(f.ready and f.selected for f in screen.fleets)
            return Action("tap", screen.send_at, why=f"出征（{n} 支）")
        timers = [f.timer for f in screen.fleets if f.timer]
        wait = min(max(min(timers) - 1, 1), 5) if timers else 3
        return Action("wait", seconds=wait, why="沒有可出征的艦隊，等倒數")

    if screen.kind == "city":
        if not same_target(screen.city, target):
            return Action("reset", why=f"開到的是「{screen.city}」，不是「{target}」")
        if SEND_BUTTON in screen.buttons:
            return Action("tap", screen.buttons[SEND_BUTTON],
                          why=f"城市是「{screen.city}」，按{SEND_BUTTON}")
        return Action("wait", seconds=1, why="城市彈窗還沒完全出現")

    if screen.kind == "map":
        hit = find_target(screen, target)
        if hit:
            return Action("tap", hit[1], why=f"點左側目標「{hit[0]}」")
        return Action("wait", seconds=2, why=f"左側清單找不到「{target}」")

    return Action("wait", seconds=1, why="看不懂這個畫面（載入中或其他頁面）")


def find_target(screen, wanted):
    """在左側清單裡找使用者設定的目標，回傳 (讀到的名稱, 位置) 或 None。"""
    want = split_target(wanted)
    if not want:
        return None
    for name, pos in screen.targets.items():
        got = split_target(name)
        if got and got == want:
            return name, pos
    return None
