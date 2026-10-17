"""視窗 I/O：找視窗、截背景視窗的圖、對背景視窗送點擊（游標不動、視窗不跳前景）。"""
import time
import numpy as np
import Quartz


def find_windows(owner_substr=None, min_size=200):
    out = []
    wins = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly
        | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID) or []
    for w in wins:
        b = w["kCGWindowBounds"]
        if b["Width"] < min_size or b["Height"] < min_size:
            continue
        owner = w.get("kCGWindowOwnerName", "") or ""
        if owner_substr and owner_substr.lower() not in owner.lower():
            continue
        out.append({
            "pid": w["kCGWindowOwnerPID"],
            "wid": w["kCGWindowNumber"],
            "owner": owner,
            "title": w.get("kCGWindowName", "") or "",
            "x": int(b["X"]), "y": int(b["Y"]),
            "w": int(b["Width"]), "h": int(b["Height"]),
        })
    return out


def grab(win) -> np.ndarray:
    """只截這一個視窗，不需要它在前景。回傳 BGR numpy 影像。

    取 Retina 原生解析度：實測降到一半解析度時 OCR 就會漏判「跳過」，
    所以寧可多花十幾毫秒。影像像素數可能是視窗點數的 2 倍，
    座標換算交給 img_scale()。
    """
    img = Quartz.CGWindowListCreateImage(
        Quartz.CGRectNull,
        Quartz.kCGWindowListOptionIncludingWindow,
        win["wid"],
        Quartz.kCGWindowImageBoundsIgnoreFraming
        | Quartz.kCGWindowImageBestResolution,
    )
    if img is None:
        raise RuntimeError("截圖失敗：視窗可能被最小化，或沒給螢幕錄影權限")
    w = Quartz.CGImageGetWidth(img)
    h = Quartz.CGImageGetHeight(img)
    bpr = Quartz.CGImageGetBytesPerRow(img)
    data = Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(img))
    buf = np.frombuffer(data, dtype=np.uint8)
    buf = buf[: h * bpr].reshape(h, bpr // 4, 4)[:, :w, :]
    return np.ascontiguousarray(buf[:, :, :3])   # BGRA -> BGR


def img_scale(win, img) -> float:
    """截圖像素 ÷ 視窗點數。Retina 上是 2.0。"""
    return img.shape[1] / float(win["w"])


def cursor_pos():
    return Quartz.CGEventGetLocation(Quartz.CGEventCreate(None))


def covered_by(win, px, py, scale=1.0):
    """檢查視窗內的 (px, py)（截圖像素座標）有沒有被別的視窗蓋住。

    為什麼需要這個：截圖和點擊走的是兩套機制。截圖跟 WindowServer 要
    某一個視窗的圖層，被蓋住也照樣看得到；但點擊送的是「螢幕上某個座標」，
    會被最上層的視窗接走。實測確認過：目標被蓋住時，腳本看得到按鈕，
    點擊卻跑去蓋在上面的那個 App。所以每次點之前都要檢查。

    回傳擋住的視窗描述（list），空的代表沒被擋、可以安全點。
    """
    gx = win["x"] + px / scale
    gy = win["y"] + py / scale
    blockers = []
    for w in find_windows(min_size=50):      # 由上而下排序
        if w["wid"] == win["wid"]:
            break                            # 到自己了，上面的都檢查完了
        if w["x"] <= gx <= w["x"] + w["w"] and w["y"] <= gy <= w["y"] + w["h"]:
            blockers.append(f"{w['owner']}/{w['title'] or '(無標題)'}")
    return blockers


def click_bg(win, px, py, scale=1.0, restore_cursor=True):
    """點視窗內的某個位置。(px, py) 是『截圖像素』座標。

    實測結論（見 README）：
      * CGEventPostToPid 對滑鼠事件完全無效，前景背景都一樣，不能用。
      * 全域 CGEventPost 可以點中背景視窗，而且**不會把它拉到前景**，
        鍵盤焦點留在使用者正在用的 App。唯一代價是游標會瞬移過去，
        所以點完立刻把游標移回原位，整個過程約 150ms。
    """
    before = cursor_pos() if restore_cursor else None
    gx = win["x"] + px / scale
    gy = win["y"] + py / scale
    pos = Quartz.CGPointMake(gx, gy)
    for kind in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
        ev = Quartz.CGEventCreateMouseEvent(
            None, kind, pos, Quartz.kCGMouseButtonLeft)
        Quartz.CGEventSetIntegerValueField(ev, Quartz.kCGMouseEventClickState, 1)
        Quartz.CGEventPost(Quartz.kCGSessionEventTap, ev)
        time.sleep(0.03)
    if before is not None:
        Quartz.CGWarpMouseCursorPosition(before)
    return int(gx), int(gy)
