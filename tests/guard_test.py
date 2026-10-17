"""驗證 covered_by：目標視窗在最上層時要放行，被壓住時要回報擋住它的視窗。

只測判斷邏輯，不送點擊 —— 「被蓋住時點擊會跑到別的視窗」已由
occlusion_test.py 另外證實過。
"""
import time
import AppKit
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "waterbot"))
from winio import find_windows, grab, img_scale, covered_by
from ocr import ocr

win = find_windows("Calculator", min_size=100)[0]
img = grab(win)
sc = img_scale(win, img)
keys = {t.strip(): (x, y) for t, x, y, c in ocr(img) if t.strip().isdigit()}
if not keys:
    raise SystemExit("在計算機視窗裡找不到任何數字鍵；"
                     "請確認它沒有被縮到最小或移到螢幕外。")
label = next(k for k in ("9", "8", "7", "6", "5") if k in keys) \
    if any(k in keys for k in ("9", "8", "7", "6", "5")) else next(iter(keys))
px, py = keys[label]
print(f"測試點 =「{label}」鍵")
print(f"計算機 @({win['x']},{win['y']})")

ws = AppKit.NSWorkspace.sharedWorkspace()
calc = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(win["pid"])

calc.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)
time.sleep(1.2)
win = find_windows("Calculator", min_size=100)[0]
a = covered_by(win, px, py, sc)
print(f"[計算機在最上層] 前景={ws.frontmostApplication().localizedName():<12} "
      f"covered_by -> {a or '沒被擋 ✅'}")

# 找一個「有大視窗、而且剛好蓋到測試點」的其他 App 壓上來
gx = win["x"] + px / sc
gy = win["y"] + py / sc
blocker = None
for w in find_windows(min_size=400):
    if w["pid"] == win["pid"]:
        continue
    if w["x"] <= gx <= w["x"] + w["w"] and w["y"] <= gy <= w["y"] + w["h"]:
        blocker = AppKit.NSRunningApplication.\
            runningApplicationWithProcessIdentifier_(w["pid"])
        break

if blocker is None:
    print("\n找不到任何視窗蓋得到測試點，無法測「被擋住」這一半。")
    print("請把某個視窗（瀏覽器之類）移到計算機上面再跑一次。")
    raise SystemExit(0 if not a else 1)

blocker.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)
time.sleep(1.2)
win = find_windows("Calculator", min_size=100)[0]
b = covered_by(win, px, py, sc)
print(f"[被 {blocker.localizedName()} 壓住] "
      f"covered_by -> {b or '沒被擋'} {'✅' if b else '❌ 應該要擋'}")

print("\n結果:", "通過" if (not a and b) else "不符預期，要再看")
