"""城戰派兵的完整流程測試：用一個假的遊戲跑真正的 siege_bot.main()。

假遊戲照影片裡觀察到的行為反應點擊：
  * 地圖點左側目標 → 城市彈窗
  * 彈窗按「前往」→ 選擇艦隊
  * 按「維修」→ 變成倒數，幾輪後修好、勾選被清掉
  * 點艦隊那一列 → 切換勾選
  * 按「出征」→ 勾選的艦隊出發、視窗關掉回到地圖

要驗的是整條路徑接得起來，以及兩條紅線：
  **受損的艦隊絕不能被派出去；駐防中的艦隊不能被動到。**

    ./waterbot/.venv/bin/python tests/test_siege_flow.py
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

import siege        # noqa: E402
import siege_bot    # noqa: E402
from siege import Fleet, SiegeScreen   # noqa: E402

TARGET_AT, GO_AT, SEND_AT = (40, 400), (480, 900), (470, 1050)
ROW_Y = (300, 500, 700)


class FakeGame:
    def __init__(self):
        self.kind = "map"
        # 第一支：空閒但受損；第二支：空閒完好；第三支：駐防中
        self.f = [dict(status="idle", bar=0.60, sel=True, repair=0, sent=0),
                  dict(status="idle", bar=0.99, sel=False, repair=0, sent=0),
                  dict(status="garrison", bar=0.99, sel=False, repair=0, sent=0)]
        self.log = []
        self.lock = threading.Lock()

    def screen(self):
        with self.lock:
            # 維修中的倒數：每看一次畫面少一點，歸零就修好
            for x in self.f:
                if x["repair"] > 0:
                    x["repair"] -= 1
                    if x["repair"] == 0:
                        x.update(status="idle", bar=0.99)
            if self.kind == "map":
                return SiegeScreen("map", targets={"防守堡壘F2": TARGET_AT})
            if self.kind == "city":
                return SiegeScreen("city", city="堡壘F2",
                                   buttons={"前往": GO_AT, "守軍": (300, 900)})
            fleets = []
            for i, x in enumerate(self.f):
                damaged = x["status"] == "idle" and x["bar"] < 0.97
                fleets.append(Fleet(
                    index=i + 1, anchor_y=ROW_Y[i],
                    status="timer" if x["repair"] else x["status"],
                    timer=x["repair"] or None,
                    repair_at=(620, ROW_Y[i]) if damaged else None,
                    bar=x["bar"], selected=x["sel"], tap_at=(100, ROW_Y[i])))
            return SiegeScreen("fleets", fleets=fleets, send_at=SEND_AT)

    def tap(self, at):
        with self.lock:
            self.log.append((self.kind, at))
            if self.kind == "map" and at == TARGET_AT:
                self.kind = "city"
            elif self.kind == "city" and at == GO_AT:
                self.kind = "fleets"
            elif self.kind == "fleets":
                for i, y in enumerate(ROW_Y):
                    x = self.f[i]
                    if at == (620, y):                     # 維修
                        x.update(repair=3, sel=False)
                    elif at == (100, y):                   # 勾選／取消
                        x["sel"] = not x["sel"]
                if at == SEND_AT:
                    for x in self.f:
                        if x["sel"]:
                            x.update(sent=x["sent"] + 1, sel=False,
                                     status="marching", damaged_when_sent=x["bar"] < 0.97)
                    self.kind = "map"


game = FakeGame()
tmp = tempfile.mkdtemp()
fails = []


def check(name, got, want):
    ok = got == want
    print(f"[{'ok  ' if ok else 'FAIL'}] {name}: {got}")
    if not ok:
        print(f"        預期 {want}")
        fails.append(name)


try:
    siege_bot.OUT = tmp
    siege_bot.STOP_FILE = os.path.join(tmp, "STOP")
    siege_bot.SETTLE = 0.02
    siege_bot.signal = types.SimpleNamespace(signal=lambda *a, **k: None, SIGINT=2)
    siege_bot.pick_window = lambda app: {"pid": 1, "wid": 1, "owner": "水世界",
                                         "title": "", "x": 0, "y": 0,
                                         "w": 900, "h": 1600}
    siege_bot.grab = lambda win: np.zeros((1600, 900, 3), np.uint8)
    siege_bot.img_scale = lambda win, img: 1.0
    siege_bot.ocr = lambda img, *a, **k: []
    siege_bot.covered_by = lambda *a, **k: []
    siege_bot.keep_awake = lambda: None
    siege_bot.notify = lambda *a: None
    siege_bot.click_bg = lambda win, x, y, s=1.0, **k: game.tap((x, y)) or (x, y)
    siege_bot.click_front = siege_bot.click_bg
    siege.read = lambda img, items=None, ocr_fn=None: game.screen()

    # 等待改短，測試不必真的等倒數
    real_plan = siege.plan

    def fast_plan(*a, **k):
        act = real_plan(*a, **k)
        if act.kind == "wait":
            act.seconds = 0.02
        return act
    siege.plan = fast_plan

    sys.argv = ["siege_bot.py", "--target", "防守堡壘F2", "--until", "23:59"]
    done = threading.Event()
    t = threading.Thread(target=lambda: (siege_bot.main(), done.set()), daemon=True)
    t.start()
    time.sleep(3)
    open(siege_bot.STOP_FILE, "w").close()
    done.wait(timeout=10)

    f1, f2, f3 = game.f
    print(f"\n點了 {len(game.log)} 下")
    check("程式有收工", done.is_set(), True)
    check("第二支（一開始就完好）被派出去", f2["sent"] >= 1, True)
    check("第一支（受損）先修好再被派出去", f1["sent"] >= 1, True)
    check("第一支被派出去時已經修好",
          not f1.get("damaged_when_sent", False), True)
    check("駐防中的第三支從沒被點過",
          any(at in ((100, ROW_Y[2]), (620, ROW_Y[2])) for _, at in game.log), False)
    check("沒有任何一支在受損狀態被派出",
          any(x.get("damaged_when_sent") for x in game.f), False)
    first_send = next(i for i, (k, at) in enumerate(game.log) if at == SEND_AT)
    check("第一次出征前，受損又被勾著的第一支已經取消或送修",
          any(at in ((620, ROW_Y[0]), (100, ROW_Y[0]))
              for _, at in game.log[:first_send]), True)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
if fails:
    print(f"{len(fails)} 個失敗：", fails)
    print("點擊順序：", game.log)
    sys.exit(1)
print("全部通過。")
