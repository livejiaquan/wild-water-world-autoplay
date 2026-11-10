"""遮擋判定的規則測試。

通知出現時，macOS 把 Notification Center 的範圍報成整個螢幕，但實際上
只有右上角那塊橫幅會接走點擊。實測對照過：

    沒有通知   covered_by 說沒被擋   點擊生效
    通知跳出   covered_by 說被擋     點擊仍然生效   <- 誤判

這裡用假造的視窗清單驗規則本身，重點在**放行通知的同時，真正的遮擋
不能跟著被放行** —— 那才是這個修改的風險所在。

    ./waterbot/.venv/bin/python tests/test_occlusion_rules.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "waterbot"))

from winio import BANNER_H, BANNER_W, passes_through   # noqa: E402

SCREEN = {"x": 0, "y": 0, "w": 1920, "h": 1080}

fails = []


def win(owner, **kw):
    return {**SCREEN, **kw, "owner": owner, "title": owner,
            "wid": 99, "pid": 99}


def check(name, got, want):
    ok = got == want
    print(f"[{'ok  ' if ok else 'FAIL'}] {name}: 穿透={got}")
    if not ok:
        print(f"        預期 穿透={want}")
        fails.append(name)


print("── 通知：只有右上角橫幅才算真的擋住 ──")
noti = win("Notification Center")
check("畫面正中央 -> 穿透", passes_through(noti, 960, 540), True)
check("左下角（闖關鈕的位置）-> 穿透", passes_through(noti, 90, 1060), True)
check("下方中央（再戰一次的位置）-> 穿透", passes_through(noti, 960, 860), True)
check("右下角（跳過鈕的位置）-> 穿透", passes_through(noti, 1700, 1010), True)
check("右上角橫幅正中 -> 不穿透",
      passes_through(noti, 1920 - BANNER_W // 2, BANNER_H // 2), False)
check("剛好在橫幅邊界內 -> 不穿透",
      passes_through(noti, 1920 - BANNER_W + 5, BANNER_H - 5), False)
check("橫幅左邊一點點 -> 穿透",
      passes_through(noti, 1920 - BANNER_W - 5, BANNER_H // 2), True)
check("橫幅下面一點點 -> 穿透",
      passes_through(noti, 1920 - BANNER_W // 2, BANNER_H + 5), True)

print("\n── 真正會攔截輸入的覆蓋層，不能跟著被放行 ──")
# Cmd+Shift+5 的截圖工具：一樣是全螢幕覆蓋層，但它真的吃掉所有滑鼠輸入
check("截圖工具 Screenshot -> 不穿透",
      passes_through(win("Screenshot"), 960, 540), False)
check("一般 App 視窗 -> 不穿透",
      passes_through(win("Google Chrome"), 960, 540), False)
check("Control Center -> 不穿透",
      passes_through(win("Control Center"), 960, 540), False)
check("選單列 Window Server -> 不穿透",
      passes_through(win("Window Server"), 960, 15), False)

print("\n── 多螢幕：橫幅是以該視窗自己的右上角為準 ──")
second = win("Notification Center", x=1920, y=0, w=1440, h=900)
check("第二螢幕的正中央 -> 穿透", passes_through(second, 2640, 450), True)
check("第二螢幕的右上角 -> 不穿透",
      passes_through(second, 3360 - BANNER_W // 2, BANNER_H // 2), False)

print()
if fails:
    print(f"{len(fails)} 個失敗：", fails)
    sys.exit(1)
print("全部通過。")
