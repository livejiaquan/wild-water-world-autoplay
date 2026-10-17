"""實測：目標視窗被別的視窗蓋住時，截圖與點擊分別會發生什麼事。

截圖走 WindowServer 的個別視窗圖層，點擊走螢幕全域座標 —— 兩者機制不同，
這支腳本就是要確認這個不對稱會不會造成「看得到卻點到別人」。
"""
import time, subprocess
import AppKit
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "waterbot"))
from winio import find_windows, grab, click_bg, img_scale
from ocr import ocr

win = find_windows("Calculator", min_size=100)[0]
img = grab(win)
sc = img_scale(win, img)
print(f"計算機 @({win['x']},{win['y']}) {win['w']}x{win['h']}"
      f" / 截圖 {img.shape[1]}x{img.shape[0]} scale={sc}")

keys = {t: (x, y) for t, x, y, c in ocr(img)}


def disp():
    r = ocr(grab(win)[int(55 * sc):int(135 * sc), :])
    return "|".join(t for t, *_ in r) or "(空)"


print("顯示:", disp(), "| 按鍵 9 的截圖座標:", keys.get("9"))

subprocess.run(["osascript", "-e", f'''
tell application "Finder"
  activate
  set w to make new Finder window
  set bounds of w to {{{win["x"] - 20}, {win["y"] - 20},
                       {win["x"] + win["w"] + 20}, {win["y"] + win["h"] + 20}}}
end tell'''], capture_output=True)
time.sleep(1.5)

front = AppKit.NSWorkspace.sharedWorkspace().frontmostApplication().localizedName()
print(f"\n前景: {front}")

# 真的確認有東西蓋在「9」這顆按鍵的螢幕位置上，而且疊得比計算機高
gx = win["x"] + keys["9"][0] / sc
gy = win["y"] + keys["9"][1] / sc
stack = find_windows(min_size=50)
over = []
for w in stack:
    if w["wid"] == win["wid"]:
        break           # find_windows 由上而下，碰到計算機就停
    if w["x"] <= gx <= w["x"] + w["w"] and w["y"] <= gy <= w["y"] + w["h"]:
        over.append(f"{w['owner']}/{w['title'] or '(無標題)'}")
print(f"『9』在螢幕 ({gx:.0f},{gy:.0f})，壓在它上面的視窗: {over or '沒有'}")

visible = sorted({t for t, *_ in ocr(grab(win)) if t.isdigit()})
print("被蓋住後，截圖裡仍看得到的數字鍵:", visible)

before = disp()
click_bg(win, keys["9"][0], keys["9"][1], sc)
time.sleep(0.9)
after = disp()
print(f"\n點『9』: {before} -> {after}")
print("結論:", "✅ 點擊穿透，計算機收到了"
      if after != before else "❌ 點擊被上層視窗吃掉，計算機沒收到")
