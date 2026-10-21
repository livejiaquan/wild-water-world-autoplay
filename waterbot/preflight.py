"""開跑前的自我檢查，用白話告訴使用者缺什麼、怎麼補。

設計給完全不懂程式的人看：每一項都講「現在是什麼狀況」「要做什麼」，
而且能直接幫忙把系統設定的正確頁面打開。
"""
import subprocess
import sys

OK = "✅"
NO = "❌"
WARN = "⚠️ "

SCREEN_PANE = ("x-apple.systempreferences:com.apple.preference.security"
               "?Privacy_ScreenCapture")
AX_PANE = ("x-apple.systempreferences:com.apple.preference.security"
           "?Privacy_Accessibility")


def check_screen_recording():
    """能不能看到視窗標題 —— 沒給螢幕錄影權限時，標題一律是空的。"""
    try:
        import Quartz
    except ImportError:
        return None, "Python 套件還沒裝好"
    wins = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly
        | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID) or []
    named = [w for w in wins if w.get("kCGWindowName")]
    others = [w for w in wins
              if w.get("kCGWindowOwnerName") not in (None, "Window Server")]
    if named:
        return True, f"看得到 {len(named)} 個視窗的名稱"
    if others:
        return False, "看得到視窗但讀不到名稱，通常就是權限沒給"
    return False, "完全看不到其他視窗"


def check_accessibility():
    try:
        import HIServices
    except ImportError:
        return None, "Python 套件還沒裝好"
    return bool(HIServices.AXIsProcessTrusted()), ""


def check_packages():
    missing = []
    for mod, pkg in (("cv2", "opencv-python-headless"),
                     ("numpy", "numpy"),
                     ("Vision", "pyobjc-framework-Vision"),
                     ("Quartz", "pyobjc-framework-Quartz"),
                     ("HIServices", "pyobjc-framework-ApplicationServices")):
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    return (not missing), ("缺少: " + ", ".join(missing) if missing else "都裝好了")


def check_ocr():
    """真的跑一次 OCR，確認中文辨識可用。"""
    try:
        import numpy as np
        import cv2
        from ocr import ocr
    except Exception as e:
        return None, f"載入失敗: {e}"
    img = np.full((120, 420, 3), 255, np.uint8)
    cv2.putText(img, "TEST 123", (20, 80), cv2.FONT_HERSHEY_SIMPLEX,
                1.6, (0, 0, 0), 4)
    try:
        got = " ".join(t for t, *_ in ocr(img))
    except Exception as e:
        return False, f"OCR 執行失敗: {e}"
    return ("TEST" in got.upper()), f"讀到「{got.strip() or '(空)'}」"


def find_game(hint=None):
    try:
        from winio import find_windows
    except Exception:
        return None, "套件還沒裝好"
    from bot import APP_HINTS
    hints = [h.strip().lower()
             for h in (hint or ",".join(APP_HINTS)).split(",") if h.strip()]
    wins = find_windows(min_size=300)
    hit = [w for w in wins
           if any(h in (w["owner"] + " " + w["title"]).lower() for h in hints)]
    if hit:
        w = hit[0]
        return True, f"[{w['owner']}] {w['title']} {w['w']}x{w['h']}"
    tall = [w for w in wins if w["h"] > w["w"] * 1.3]
    if tall:
        names = "、".join(f"{w['owner']}" for w in tall[:3])
        return False, f"沒認出遊戲，但有直式視窗: {names}"
    return False, "沒找到遊戲視窗"


def main(game_hint=None, open_settings=True):
    print("=" * 56)
    print(" 開跑前檢查")
    print("=" * 56)
    problems = []

    ok, msg = check_packages()
    print(f"\n{OK if ok else NO} Python 套件      {msg}")
    if not ok:
        print("   → 請先執行 install.command")
        problems.append("packages")
        print("\n套件沒裝好，後面的檢查先跳過。")
        return 1

    ok, msg = check_ocr()
    print(f"{OK if ok else NO} 文字辨識         {msg}")
    if not ok:
        problems.append("ocr")

    ok, msg = check_screen_recording()
    print(f"{OK if ok else NO} 螢幕錄影權限     {msg}")
    if not ok:
        problems.append("screen")
        print("   → 這個權限讓程式「看得到」遊戲畫面。沒有它就完全不能用。")
        print("      系統設定 → 隱私權與安全性 → 螢幕錄影與系統錄音")
        print("      把「終端機」打勾")
        if open_settings:
            subprocess.run(["open", SCREEN_PANE], capture_output=True)
            print("      （已幫你打開那一頁）")

    ok, msg = check_accessibility()
    print(f"{OK if ok else NO} 輔助使用權限     {msg or ('已授權' if ok else '未授權')}")
    if not ok:
        problems.append("ax")
        print("   → 這個權限讓程式「點得下去」。沒有它只能看不能點。")
        print("      系統設定 → 隱私權與安全性 → 輔助使用")
        print("      把「終端機」打勾")
        if open_settings:
            subprocess.run(["open", AX_PANE], capture_output=True)
            print("      （已幫你打開那一頁）")

    ok, msg = find_game(game_hint)
    print(f"{OK if ok else WARN} 遊戲視窗         {msg}")
    if not ok:
        print("   → 請先把遊戲打開，並確認視窗沒有被縮到最小。")

    print("\n" + "=" * 56)
    if "screen" in problems or "ax" in problems:
        print("權限給完之後，請把「終端機」整個關掉再重開，")
        print("權限才會生效，然後再執行一次這個檢查。")
        return 1
    if problems:
        print("還有問題要處理，看上面的說明。")
        return 1
    print("一切就緒。")
    return 0


if __name__ == "__main__":
    hint = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(main(hint))
