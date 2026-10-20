"""關卡進度判定：餵一串假的畫面狀態，確認通關紀錄寫出來的內容正確。

這裡不碰遊戲也不碰螢幕，只測「什麼時候該算通過一關」這個邏輯，
因為它決定紀錄檔的正確性，而那是使用者唯一會看的東西。

    ./waterbot/.venv/bin/python tests/test_progress.py
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "waterbot"))

from runlog import RunLog   # noqa: E402

fails = []


def track(sequence):
    """把 bot.py 裡的進度判定抽出來跑一遍。

    sequence 是 (關卡編號或None, 是否為一次失敗重試) 的串列。
    回傳 [(通過的關卡, 嘗試次數), ...]
    """
    stage_seen, attempts, out = None, 0, []
    for stage, is_retry in sequence:
        if is_retry:
            attempts += 1
            continue
        if stage and stage != stage_seen:
            if stage_seen is not None and stage > stage_seen:
                out.append((stage_seen, attempts))
            stage_seen = stage
            attempts = 0
    return out


def check(name, got, want):
    ok = got == want
    print(f"[{'ok  ' if ok else 'FAIL'}] {name}")
    print(f"        得到 {got}")
    if not ok:
        print(f"        預期 {want}")
        fails.append(name)


print("── 什麼時候算通過一關 ──")

check("輸兩次才過，記 2 次嘗試",
      track([(876, False), (None, True), (None, True), (877, False)]),
      [(876, 2)])

check("連過三關",
      track([(876, False), (None, True), (877, False),
             (None, True), (None, True), (878, False)]),
      [(876, 1), (877, 2)])

check("第一次看到關卡不該算通過",
      track([(876, False)]),
      [])

check("關卡編號沒變不算通過",
      track([(876, False), (876, False), (876, False)]),
      [])

check("編號變小（退出重進）不算通過",
      track([(877, False), (876, False)]),
      [])

check("讀不到編號的幀不影響判定",
      track([(876, False), (None, False), (None, True),
             (None, False), (877, False)]),
      [(876, 1)])

check("跳號（一次過好幾關）仍記一筆",
      track([(876, False), (880, False)]),
      [(876, 0)])

print("\n── 寫出來的檔案長什麼樣 ──")
tmp = tempfile.mkdtemp()
try:
    log = RunLog(tmp)
    for stage, secs, tries in ((876, 252, 18), (877, 390, 27), (878, 45, 0)):
        log.clear(stage, secs, tries)
    print(open(os.path.join(tmp, "通關紀錄.txt"), encoding="utf-8").read())
finally:
    shutil.rmtree(tmp, ignore_errors=True)

if fails:
    print(f"{len(fails)} 個失敗：", fails)
    sys.exit(1)
print("全部通過。")
