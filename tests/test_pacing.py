"""輪詢節奏的測試，重點是「跳過鍵一出現要多久才被發現」。

這裡防的是一個實際發生過的回歸：原本想用「睡到倒數結束」省 OCR，
但畫面上的秒數是整數 —— 顯示「1 秒」時真實剩餘是 0 到 1 秒之間，
睡下去最壞比跳過鍵晚 0.75 秒才發現，比固定輪詢還慢。

    ./waterbot/.venv/bin/python tests/test_pacing.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "waterbot"))

from bot import FAST_POLL, MAX_NAP, next_wait   # noqa: E402
from detect import Screen                        # noqa: E402

OCR_BAND = 0.084      # 實測只掃下方條的耗時
OCR_FULL = 0.128      # 實測掃全張的耗時

fails = []


def check(name, got, want):
    ok = got == want
    print(f"[{'ok  ' if ok else 'FAIL'}] {name}: {got}")
    if not ok:
        print(f"        預期 {want}")
        fails.append(name)


print("── 等多久、下一圈掃哪裡 ──")
check("倒數 10 秒：睡到上限，醒來仍在倒數中要掃全張",
      next_wait(Screen("BATTLE", countdown=10), 0.5), (MAX_NAP, False))
check("倒數 4 秒：睡 3 秒，醒來剩約 1 秒，準備找跳過",
      next_wait(Screen("BATTLE", countdown=4), 0.5), (3.0, True))
check("倒數 2 秒：睡 1 秒",
      next_wait(Screen("BATTLE", countdown=2), 0.5), (1.0, True))
check("倒數 1 秒：不睡，密集輪詢",
      next_wait(Screen("BATTLE", countdown=1), 0.5), (FAST_POLL, True))
check("沒有倒數的畫面用一般間隔",
      next_wait(Screen("UNKNOWN"), 0.5), (0.5, False))
check("關卡畫面也用一般間隔",
      next_wait(Screen("STAGE_SELECT", (1, 2)), 0.5), (0.5, False))


print("\n── 跳過鍵出現後，最壞要多久才發現 ──")


def worst_lag(strategy):
    """真實剩餘時間在 0~1 秒之間，取最壞的那個。"""
    worst = 0.0
    for real in [i / 100 for i in range(1, 101)]:
        if strategy == "睡到倒數結束(舊)":
            lag = max(0.0, (1 - 0.25) - real) + OCR_BAND
        elif strategy == "固定 0.5s 輪詢":
            # 最壞是剛輪詢完才出現
            lag = 0.5 + OCR_FULL
        else:                                   # 現在的做法
            lag = FAST_POLL + OCR_BAND
        worst = max(worst, lag)
    return round(worst, 3)


results = {}
for name in ("睡到倒數結束(舊)", "固定 0.5s 輪詢", "最後一秒密集輪詢(現在)"):
    results[name] = worst_lag(name)
    print(f"  {name:<24} 最壞遲到 {results[name]:.3f}s")

now = results["最後一秒密集輪詢(現在)"]
check("現在的做法要比睡到倒數結束快",
      now < results["睡到倒數結束(舊)"], True)
check("也要比固定 0.5s 輪詢快",
      now < results["固定 0.5s 輪詢"], True)


print("\n── 一次 10 秒倒數要做幾次 OCR ──")


def ocr_count(countdown=10):
    n, remaining = 0, float(countdown)
    while remaining > 1.0:
        wait, _ = next_wait(Screen("BATTLE", countdown=int(remaining)), 0.5)
        remaining -= wait
        n += 1
    n += int(1.0 / (FAST_POLL + OCR_BAND))      # 最後一秒的密集輪詢
    return n


got = ocr_count()
fixed = int(10 / 0.5)
print(f"  現在的做法 {got} 次   固定 0.5s 輪詢 {fixed} 次")
check("仍然比固定輪詢省", got < fixed, True)

print()
if fails:
    print(f"{len(fails)} 個失敗：", fails)
    sys.exit(1)
print("全部通過。")
