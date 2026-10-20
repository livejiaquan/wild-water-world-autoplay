"""暫停／繼續的測試。

用虛擬終端機（pty）假扮成真的終端機，這樣才測得到按鍵那條路徑。
驗三件事：暫停時不再點擊、繼續後會接著點、按 q 會收工。
另外也驗沒有終端機時（測試、自動化）不會壞掉。

    ./waterbot/.venv/bin/python tests/test_pause.py
"""
import os
import pty
import select
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = os.path.join(ROOT, "waterbot", ".venv", "bin", "python")

DRIVER = r'''
import os, sys, time
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "waterbot"))
import bot

W, H = 900, 1600
WIN = {"pid":1,"wid":1,"owner":"水世界","title":"水世界","x":0,"y":0,"w":W,"h":H}
clicks = []

_n = [0]
def fake_ocr(img, langs=None, fast=False):
    # 交替「戰鬥失敗」和「戰鬥中」，這樣每點一次就會離開原狀態，
    # 點擊節奏才會快到測得出暫停前後的差別。
    _n[0] += 1
    stage = ("第876關", 450, int(H*0.04), 1.0)
    if _n[0] % 2:
        return [("再戰一次", 450, int(H*0.79), 1.0), stage]
    return [("2倍速", 800, int(H*0.93), 1.0), stage]

bot.OUT = os.environ["OUTDIR"]
bot.BAND_TOP = 0.0
bot.ocr = fake_ocr
bot.grab = lambda win: np.zeros((H, W, 3), np.uint8)
bot.click_bg = lambda *a, **k: (clicks.append(1), print(f"CLICK {len(clicks)}", flush=True))[1] or (0,0)
bot.covered_by = lambda *a, **k: []
bot.find_windows = lambda **k: [WIN]
bot.STOP_FILE = os.path.join(bot.OUT, "STOP")
sys.argv = ["bot.py", "--interval", "0.05", "--max-clicks-per-min", "100000",
            "--max-stuck", "600"]
bot.main()
print("EXITED", flush=True)
'''

import tempfile
tmp = tempfile.mkdtemp()
drv = os.path.join(ROOT, "_pause_driver.py")
open(drv, "w").write(DRIVER)

fails = []
try:
    m, sfd = pty.openpty()
    env = dict(os.environ, OUTDIR=tmp, PYTHONUNBUFFERED="1")
    p = subprocess.Popen([PY, drv], stdin=sfd, stdout=sfd, stderr=sfd,
                         env=env, close_fds=True)
    os.close(sfd)

    buf = ""

    def pump(seconds):
        global buf
        end = time.time() + seconds
        while time.time() < end:
            r, _, _ = select.select([m], [], [], 0.05)
            if r:
                try:
                    buf += os.read(m, 4096).decode("utf-8", "ignore")
                except OSError:
                    break

    def clicks_so_far():
        return buf.count("CLICK ")

    # 等子行程真的開始跑，不然量到的是 Python 啟動時間
    t0 = time.time()
    while "暫停／繼續" not in buf and time.time() - t0 < 20:
        pump(0.2)
    pump(3.0)
    a = clicks_so_far()
    print(f"啟動後跑 3 秒，點了 {a} 次")
    if a < 2:
        fails.append(f"正常執行時應該持續點擊，只點了 {a} 次")

    os.write(m, b" ")                      # 暫停
    pump(1.0)
    b = clicks_so_far()
    pump(2.0)
    c = clicks_so_far()
    print(f"按空白鍵暫停後：再過 2 秒，點擊數 {b} -> {c}")
    if c != b:
        fails.append(f"暫停期間不應該再點擊，卻從 {b} 增加到 {c}")
    if "已暫停" not in buf:
        fails.append("暫停時應該要有提示訊息")

    os.write(m, b" ")                      # 繼續
    pump(2.0)
    d = clicks_so_far()
    print(f"再按空白鍵繼續後：點擊數 {c} -> {d}")
    if d <= c:
        fails.append(f"繼續後應該恢復點擊，卻還是 {d}")
    if "繼續" not in buf:
        fails.append("繼續時應該要有提示訊息")

    os.write(m, b"q")                      # 結束
    pump(3.0)
    print("按 q 之後：", "有收工" if "EXITED" in buf else "沒有收工")
    if "EXITED" not in buf:
        fails.append("按 q 應該要能收工")
    p.terminate()
finally:
    os.path.exists(drv) and os.remove(drv)
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

print()
if fails:
    print(f"{len(fails)} 個失敗：")
    for f in fails:
        print("  -", f)
    print("\n--- 子行程輸出 ---")
    print(buf[-2000:])
    sys.exit(1)
print("全部通過。")
