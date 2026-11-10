"""按鈕被別的視窗蓋住時的處理。

預設是禮讓：使用者可能正在用那個視窗，把遊戲搶到前面會打斷他。
但人要是走開了，一直禮讓就等於整晚停擺，所以連續被擋夠久、而且確定
沒人在動電腦，就把遊戲拉到前景點一下再把焦點還回去。

這裡驗兩個方向都對：人在時不吵、人不在時會突破。

    ./waterbot/.venv/bin/python tests/test_breakthrough.py
"""
import os
import shutil
import sys
import tempfile
import threading
import time
import types

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "waterbot"))

import bot   # noqa: E402

W, H = 900, 1600
WIN = {"pid": 1, "wid": 1, "owner": "水世界", "title": "水世界",
       "x": 0, "y": 0, "w": W, "h": H}

fails = []


def check(name, got, want=True):
    ok = got == want
    print(f"[{'ok  ' if ok else 'FAIL'}] {name}: {got}")
    if not ok:
        fails.append(f"{name}: 得到 {got}，預期 {want}")


def run_case(tag, idle_seconds, seconds=5.0):
    """一直回報被遮擋，看程式會不會突破。回傳 (背景點擊, 前景點擊)。"""
    bg, front = [], []
    tmp = tempfile.mkdtemp()
    try:
        bot.OUT = tmp
        bot.BAND_TOP = 0.0
        bot.BLOCKED_BEFORE_BREAK = 1.0      # 測試不等 10 秒
        bot.IDLE_BEFORE_BREAK = 30.0        # 門檻維持真實值
        bot.ocr = lambda img, langs=None, fast=False: [
            ("再戰一次", 450, int(H * 0.79), 1.0),
            ("第876關", 450, int(H * 0.04), 1.0)]
        bot.grab = lambda win: np.zeros((H, W, 3), np.uint8)
        bot.click_bg = lambda *a, **k: (bg.append(1), (0, 0))[1]
        bot.click_front = lambda *a, **k: (front.append(1), (0, 0))[1]
        bot.covered_by = lambda *a, **k: ["某個視窗/擋住了"]   # 永遠被擋
        bot.user_idle = lambda: idle_seconds
        bot.find_windows = lambda **k: [WIN]
        bot.notify = lambda t, m: None
        bot.keep_awake = lambda: None
        bot.STOP_FILE = os.path.join(tmp, "STOP")
        bot.signal = types.SimpleNamespace(signal=lambda *a, **k: None,
                                           SIGINT=2)
        sys.argv = ["bot.py", "--interval", "0.05",
                    "--max-clicks-per-min", "99999", "--max-stuck", "600"]

        done = threading.Event()
        t = threading.Thread(target=lambda: (bot.main(), done.set()),
                             daemon=True)
        t.start()
        time.sleep(seconds)
        open(bot.STOP_FILE, "w").close()
        done.wait(timeout=10)
        print(f"  {tag}：背景點擊 {len(bg)} 次，前景點擊 {len(front)} 次")
        return len(bg), len(front)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


print("── 人正在用電腦（剛剛才動過）──")
bg, front = run_case("禮讓", idle_seconds=2.0)
check("不把遊戲搶到前面", front, 0)
check("也不硬點背景", bg, 0)

print("\n── 人已經走開（很久沒動）──")
bg, front = run_case("突破", idle_seconds=120.0)
check("改用前景點擊突破遮擋", front > 0)

print()
if fails:
    print(f"{len(fails)} 個失敗：")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("全部通過。")
