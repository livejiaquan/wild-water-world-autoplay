"""控制頁的測試：真的開伺服器、真的發 HTTP 請求，確認能讀狀態也能停住主迴圈。

    ./waterbot/.venv/bin/python tests/test_webui.py
"""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "waterbot"))

import webui   # noqa: E402

fails = []


def check(name, got, want=True):
    ok = got == want
    print(f"[{'ok  ' if ok else 'FAIL'}] {name}: {got}")
    if not ok:
        fails.append(f"{name}: 得到 {got}，預期 {want}")


def get(url, path, headers=None):
    req = urllib.request.Request(url + path, headers=headers or {})
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, r.read().decode("utf-8")


def post(url, path, headers=None):
    req = urllib.request.Request(url + path, data=b"", method="POST",
                                 headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


ctl = webui.Control()
url, srv = webui.start(ctl, port=8899)
if not url:
    print("FAIL: 伺服器起不來")
    sys.exit(1)
print(f"伺服器在 {url}\n")

H = {"X-Waterbot": "1"}

print("── 基本讀取 ──")
code, body = get(url, "/")
check("首頁回 200", code, 200)
check("首頁是控制頁", "瘋狂水世界" in body)

code, body = get(url, "/api/state")
st = json.loads(body)
check("狀態是 JSON 且預設沒暫停", st["paused"], False)

print("\n── 擋掉跨站請求 ──")
check("沒帶標頭的 POST 被擋", post(url, "/api/pause"), 403)
check("被擋之後仍然沒暫停", ctl.snapshot()["paused"], False)

print("\n── 控制主迴圈 ──")
# 模擬主迴圈：只要沒暫停就一直累加
ticks = {"n": 0}
stop = threading.Event()


def fake_loop():
    while not stop.is_set():
        if ctl.stop_requested:
            break
        if not ctl.paused:
            ticks["n"] += 1
        time.sleep(0.02)


t = threading.Thread(target=fake_loop, daemon=True)
t.start()
time.sleep(0.4)
a = ticks["n"]
check("迴圈有在跑", a > 5)

check("按暫停回 200", post(url, "/api/pause", H), 200)
time.sleep(0.1)
b = ticks["n"]
time.sleep(0.4)
c = ticks["n"]
check("暫停後迴圈停住", c == b)
check("狀態頁顯示已暫停", json.loads(get(url, "/api/state")[1])["paused"], True)

check("按繼續回 200", post(url, "/api/resume", H), 200)
time.sleep(0.4)
d = ticks["n"]
check("繼續後迴圈恢復", d > c)

check("按結束回 200", post(url, "/api/stop", H), 200)
time.sleep(0.2)
check("迴圈收到結束而退出", not t.is_alive())

print("\n── 頁面上的按鈕要送對指令 ──")
# 實際踩過的 bug：按鈕判斷寫反，沒暫停時按下去送出的是 resume，
# 結果什麼都沒發生。API 本身沒錯，錯在頁面的 JS，所以要單獨驗。
page = get(url, "/")[1]
import re
m = re.search(r"toggle'\)\.onclick=\(\)=>send\(([^;]+)\);", page)
check("找得到按鈕的處理邏輯", bool(m))
if m:
    expr = m.group(1)
    # dataset.on === '1' 代表「目前沒有暫停」，這時候按下去必須送 pause
    i1, i2 = expr.find("'pause'"), expr.find("'resume'")
    check("沒暫停時按下去要送 pause（不能寫反）", i1 < i2)

print("\n── 通關紀錄會出現在狀態裡 ──")
ctl.add_clear(876, 252, 18)
snap = json.loads(get(url, "/api/state")[1])
check("紀錄有一筆", len(snap["cleared"]), 1)
check("關卡對", snap["cleared"][0]["stage"], 876)
check("次數對", snap["cleared"][0]["attempts"], 18)

stop.set()
srv.shutdown()

print()
if fails:
    print(f"{len(fails)} 個失敗：")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("全部通過。")
