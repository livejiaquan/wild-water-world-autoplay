"""關卡編號的抗雜訊測試。

實際使用時回報過 885 被 OCR 讀成 835。這種一位數誤認如果直接拿來當
「通關了」的訊號，一次誤讀就會寫下一筆假紀錄，也可能讓 --stop-after-stage
提早收工。所以：

  * 編號採「最近幾次讀數的多數決」，票數不足就當作不知道
  * 通關與否不看編號，看我們有沒有真的點下「下一關」

    ./waterbot/.venv/bin/python tests/test_stage_noise.py
"""
import os
import sys
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "waterbot"))

from bot import STAGE_VOTES, confirmed_stage   # noqa: E402

fails = []


def check(name, got, want):
    ok = got == want
    print(f"[{'ok  ' if ok else 'FAIL'}] {name}: {got}")
    if not ok:
        print(f"        預期 {want}")
        fails.append(name)


def feed(readings):
    """把一串讀數餵進投票器，回傳每一步確認出來的編號。"""
    votes = deque(maxlen=STAGE_VOTES)
    out = []
    for r in readings:
        if r is not None:
            votes.append(r)
        out.append(confirmed_stage(votes))
    return out


print("── 多數決擋掉零星誤讀 ──")

check("單次 885->835 誤讀不該被採信",
      feed([885, 885, 835, 885, 885])[-1], 885)

check("誤讀出現在最前面也不該被採信",
      feed([835, 885, 885, 885])[-1], 885)

check("只讀到一次還不算數（寧可不知道）",
      feed([885])[-1], None)

check("讀到兩次才確認",
      feed([885, 885])[-1], 885)

check("兩種誤讀夾雜，正確值仍勝出",
      feed([885, 835, 885, 385, 885])[-1], 885)

check("真的換關後會跟上",
      feed([885, 885, 886, 886, 886, 886, 886])[-1], 886)

print("\n── 通關紀錄不靠編號，靠「點了下一關」 ──")


def run(events):
    """模擬主迴圈：events 是 (畫面狀態, 讀到的編號) 的串列。

    回傳 (記下來的通關清單, 最後確認的編號)。
    """
    votes = deque(maxlen=STAGE_VOTES)
    stage_seen = None
    victory_pending = False
    victory_stage = None
    cleared = []
    for state, reading in events:
        if victory_pending and state != "VICTORY":
            victory_pending = False
            cleared.append(victory_stage)
            votes.clear()
        if reading is not None:
            votes.append(reading)
        cur = confirmed_stage(votes)
        if cur and cur != stage_seen:
            stage_seen = cur
        if state == "VICTORY":          # 代表這一輪我們點了下一關
            if not victory_pending:
                victory_pending = True
                victory_stage = stage_seen
    return cleared, stage_seen


# 一次誤讀讓編號看起來「變大又變回來」，不可以因此記下通關
cleared, _ = run([("BATTLE", 885), ("BATTLE", 885), ("BATTLE", 935),
                  ("BATTLE", 885), ("BATTLE", 885)])
check("編號亂跳但沒點下一關 -> 不記通關", cleared, [])

# 正常通關：打輸幾次，然後勝利並點擊，畫面離開勝利頁
cleared, _ = run([("BATTLE", 885), ("BATTLE", 885), ("DEFEAT", 885),
                  ("BATTLE", 885), ("VICTORY", None), ("BATTLE", 886)])
check("真的點了下一關 -> 記一筆，標籤是通關前的編號", cleared, [885])

# 勝利畫面停留多個輪次（點擊沒立刻生效），不可以重複計
cleared, _ = run([("BATTLE", 885), ("BATTLE", 885),
                  ("VICTORY", None), ("VICTORY", None), ("VICTORY", None),
                  ("BATTLE", 886)])
check("勝利畫面停留多輪 -> 只記一筆", cleared, [885])

# 連過兩關
cleared, _ = run([("BATTLE", 885), ("BATTLE", 885), ("VICTORY", None),
                  ("BATTLE", 886), ("BATTLE", 886), ("VICTORY", None),
                  ("BATTLE", 887)])
check("連過兩關 -> 記兩筆", cleared, [885, 886])

# 整段都讀不到編號，仍然要記下通關（只是標籤不明）
cleared, _ = run([("BATTLE", None), ("VICTORY", None), ("BATTLE", None)])
check("完全讀不到編號 -> 仍記一筆，標籤為 None", cleared, [None])

print()
if fails:
    print(f"{len(fails)} 個失敗：", fails)
    sys.exit(1)
print("全部通過。")
