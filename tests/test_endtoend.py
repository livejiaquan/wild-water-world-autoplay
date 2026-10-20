"""端對端煙霧測試：餵一串假畫面給真正的主迴圈，確認通關紀錄真的寫得出來。

不碰遊戲、不碰螢幕、不真的點擊，但跑的是 bot.main() 本人，
所以截圖、判讀、點擊、計數、寫檔這整條路徑都會被走過一次。
重構之後最該怕的是「程式碼看起來對，但那條路徑已經接不起來」。

    ./waterbot/.venv/bin/python tests/test_endtoend.py
"""
import os
import shutil
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "waterbot"))

import bot   # noqa: E402

W, H = 900, 1600
FAKE_WIN = {"pid": 1, "wid": 1, "owner": "水世界", "title": "水世界",
            "x": 0, "y": 0, "w": W, "h": H}


def battle(stage, secs=1):
    return [(f"{secs}秒後可跳過戰鬥", 200, int(H * 0.90), 1.0),
            (f"第{stage}關", 450, int(H * 0.04), 1.0)]


def skippable(stage):
    return [("跳過", 650, int(H * 0.93), 1.0),
            (f"第{stage}關", 450, int(H * 0.04), 1.0)]


def defeat(stage):
    return [("再戰一次", 450, int(H * 0.79), 1.0),
            (f"第{stage}關", 450, int(H * 0.04), 1.0)]


def victory():
    return [("返回", 350, int(H * 0.79), 1.0),
            ("下一關", 650, int(H * 0.79), 1.0)]


# 一段完整劇情：876 關打輸兩次、第三次過關，接著 877 關一次就過
SCRIPT = (
    [battle(876)] * 2 + [skippable(876)] + [defeat(876)] +
    [battle(876)] * 2 + [skippable(876)] + [defeat(876)] +
    [battle(876)] * 2 + [skippable(876)] + [victory()] * 2 +
    [battle(877)] * 3 + [skippable(877)] + [victory()] * 2 +
    [battle(878)] * 4
)

clicks = []
step = {"i": 0}


def fake_ocr(img, langs=None, fast=False):
    i = min(step["i"], len(SCRIPT) - 1)
    step["i"] += 1
    return SCRIPT[i]


def fake_grab(win):
    return np.zeros((H, W, 3), np.uint8)


def fake_click(win, px, py, scale=1.0, restore_cursor=True):
    clicks.append((px, py))
    return px, py


tmp = tempfile.mkdtemp()
rc = 1
try:
    bot.OUT = tmp
    bot.BAND_TOP = 0.0          # 讓假座標不被裁切偏移影響
    bot.ocr = fake_ocr
    bot.grab = fake_grab
    bot.click_bg = fake_click
    bot.covered_by = lambda *a, **k: []
    bot.find_windows = lambda **k: [FAKE_WIN]
    bot.STOP_FILE = os.path.join(tmp, "STOP")

    sys.argv = ["bot.py", "--interval", "0.01", "--stop-after-stage", "878"]
    rc = bot.main()

    print(f"\n主迴圈結束，離開碼 {rc}，共點擊 {len(clicks)} 次\n")

    path = os.path.join(tmp, "通關紀錄.txt")
    if not os.path.exists(path):
        print("FAIL: 沒有產生通關紀錄.txt")
        sys.exit(1)

    body = open(path, encoding="utf-8").read()
    print("=== 產生的通關紀錄.txt ===")
    print(body)

    rows = [l for l in body.splitlines() if l.strip()][2:]
    fails = []
    if len(rows) != 2:
        fails.append(f"應該有 2 筆通關紀錄，實際 {len(rows)}")
    else:
        if not rows[0].startswith("876"):
            fails.append(f"第一筆應該是 876 關：{rows[0]}")
        if "2 次" not in rows[0]:
            fails.append(f"876 關應該記錄試了 2 次：{rows[0]}")
        if not rows[1].startswith("877"):
            fails.append(f"第二筆應該是 877 關：{rows[1]}")
        if "0 次" not in rows[1]:
            fails.append(f"877 關應該記錄試了 0 次：{rows[1]}")

    if fails:
        print("失敗：")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("通關紀錄內容正確。")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
