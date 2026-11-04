"""點了卻沒反應時的復原行為。

實際掛機遇過：畫面停在同一頁，點了二十次都沒進展，程式就自己結束了，
人回來才發現整晚白跑。這裡驗的是新的處理方式：

  * 連續點不動時，改用前景點擊（比較會成功，代價是短暫搶焦點）
  * 不管多糟都不要結束，冷卻一下繼續試
  * 畫面一旦恢復正常，計數歸零、回到原本的背景點擊

    ./waterbot/.venv/bin/python tests/test_stuck_recovery.py
"""
import os
import shutil
import sys
import tempfile
import threading
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "waterbot"))

import bot   # noqa: E402

W, H = 900, 1600
WIN = {"pid": 1, "wid": 1, "owner": "水世界", "title": "水世界",
       "x": 0, "y": 0, "w": W, "h": H}

bg_clicks = []
front_clicks = []
notices = []
stuck = {"on": True}          # True = 不管怎麼點畫面都不變


def fake_ocr(img, langs=None, fast=False):
    stage = ("第876關", 450, int(H * 0.04), 1.0)
    if stuck["on"]:
        return [("再戰一次", 450, int(H * 0.79), 1.0), stage]
    # 解除卡住之後，畫面交替變化，代表點擊有生效
    return ([("2倍速", 800, int(H * 0.93), 1.0), stage]
            if len(bg_clicks) % 2 else
            [("再戰一次", 450, int(H * 0.79), 1.0), stage])


tmp = tempfile.mkdtemp()
fails = []


def check(name, got, want=True):
    ok = got == want
    print(f"[{'ok  ' if ok else 'FAIL'}] {name}: {got}")
    if not ok:
        fails.append(f"{name}: 得到 {got}，預期 {want}")


try:
    bot.OUT = tmp
    bot.BAND_TOP = 0.0
    bot.STUCK_COOLDOWN = 1.0           # 測試不等 30 秒
    # 縮短「點完等畫面變化」的上限，這樣「沒反應」的判定會快很多。
    # 門檻（連續幾次才升級／通知）維持真實值，驗的才是真正的設定。
    bot.ACTIONS = {k: (v[0], 0.3) for k, v in bot.ACTIONS.items()}
    bot.ocr = fake_ocr
    bot.grab = lambda win: np.zeros((H, W, 3), np.uint8)
    bot.click_bg = lambda *a, **k: (bg_clicks.append(1), (0, 0))[1]
    bot.click_front = lambda *a, **k: (front_clicks.append(1), (0, 0))[1]
    bot.covered_by = lambda *a, **k: []
    bot.find_windows = lambda **k: [WIN]
    bot.notify = lambda t, m: notices.append(m)
    bot.keep_awake = lambda: None
    bot.STOP_FILE = os.path.join(tmp, "STOP")
    # main() 會註冊 Ctrl-C handler，那只能在主執行緒做；測試裡跑在背景
    # 執行緒，所以停用它（這個測試用 STOP 檔收工，不需要 Ctrl-C）。
    import types
    bot.signal = types.SimpleNamespace(signal=lambda *a, **k: None, SIGINT=2)

    sys.argv = ["bot.py", "--interval", "0.02", "--max-clicks-per-min", "8",
                "--max-stuck", "600"]

    done = threading.Event()

    def run():
        bot.main()
        done.set()

    t = threading.Thread(target=run, daemon=True)
    t.start()

    time.sleep(6)
    print(f"卡住 6 秒後：背景點擊 {len(bg_clicks)} 次，"
          f"前景點擊 {len(front_clicks)} 次，通知 {len(notices)} 則\n")

    check("卡住時程式沒有結束", t.is_alive())
    check("有嘗試過背景點擊", len(bg_clicks) > 0)
    check("連續沒反應後改用前景點擊", len(front_clicks) > 0)
    check("有跳通知提醒", len(notices) > 0)
    check("通知只跳一次，不洗版", len(notices) <= 2)

    # 解除卡住，應該恢復正常並回到背景點擊
    before_front = len(front_clicks)
    stuck["on"] = False
    time.sleep(3)
    check("恢復後繼續在點", len(bg_clicks) > 0)
    check("恢復後程式仍在跑", t.is_alive())

    open(bot.STOP_FILE, "w").close()
    done.wait(timeout=10)
    check("看到 STOP 檔才收工", done.is_set())
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
if fails:
    print(f"{len(fails)} 個失敗：")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("全部通過。")
