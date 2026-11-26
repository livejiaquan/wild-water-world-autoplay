"""城戰派兵的完整流程測試：用一個假的遊戲跑真正的 siege_bot.main()。

假遊戲照影片裡觀察到的行為反應點擊：
  * 地圖點左側目標 → 城市彈窗（但鏡頭只是大致移過去）
  * 鏡頭還沒對準城市時按「前往」→ 只把鏡頭對準、彈窗關掉，**不會**出征畫面
    （影片 IMG_8927：5.8 秒按前往只移鏡頭，10.8 秒才出現選擇艦隊）
  * 鏡頭對準後，點畫面正中央的城市 → 彈窗；再按「前往」→ 選擇艦隊
  * 按「維修」→ 變成倒數，幾輪後修好、勾選被清掉
  * 點艦隊那一列 → 切換勾選
  * 按「出征」→ 勾選的艦隊出發、視窗關掉回到地圖（鏡頭仍在城市上）

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

W, H = 900, 1600
TARGET_AT, GO_AT, SEND_AT = (40, 400), (480, 900), (470, 1050)
CENTER_AT = (int(siege.CITY_CENTER[0] * W), int(siege.CITY_CENTER[1] * H))
ROW_Y = (300, 500, 700)


class FakeGame:
    def __init__(self, go_ever_opens=True):
        self.kind = "map"
        self.centred = False          # 鏡頭是否精準對準城市
        self.go_ever_opens = go_ever_opens
        # 第一支：空閒但受損、還被勾著；第二支：空閒完好；第三支：駐防中
        self.f = [dict(status="idle", bar=0.60, sel=True, repair=0, sent=0),
                  dict(status="idle", bar=0.99, sel=False, repair=0, sent=0),
                  dict(status="garrison", bar=0.99, sel=False, repair=0, sent=0)]
        self.log = []
        self.lock = threading.Lock()

    def screen(self):
        with self.lock:
            for x in self.f:                       # 維修倒數，歸零就修好
                if x["repair"] > 0:
                    x["repair"] -= 1
                    if x["repair"] == 0:
                        x.update(status="idle", bar=0.99)
            if self.kind == "map":
                return SiegeScreen("map", targets={"防守堡壘F2": TARGET_AT},
                                   size=(W, H))
            if self.kind == "city":
                return SiegeScreen("city", city="堡壘F2",
                                   buttons={"前往": GO_AT, "守軍": (300, 900)},
                                   size=(W, H))
            fleets = []
            for i, x in enumerate(self.f):
                damaged = x["status"] == "idle" and x["bar"] < 0.97
                fleets.append(Fleet(
                    index=i + 1, anchor_y=ROW_Y[i],
                    status="timer" if x["repair"] else x["status"],
                    timer=x["repair"] or None,
                    repair_at=(620, ROW_Y[i]) if damaged else None,
                    bar=x["bar"], selected=x["sel"], tap_at=(100, ROW_Y[i])))
            return SiegeScreen("fleets", fleets=fleets, send_at=SEND_AT,
                               size=(W, H))

    def tap(self, at):
        with self.lock:
            self.log.append((self.kind, at))
            if self.kind == "map" and at == TARGET_AT:
                self.kind, self.centred = "city", False
            elif self.kind == "map" and at == CENTER_AT and self.centred:
                self.kind = "city"
            elif self.kind == "city" and at == GO_AT:
                if self.centred and self.go_ever_opens:
                    self.kind = "fleets"
                else:                                # 只把鏡頭對準
                    self.kind, self.centred = "map", True
            elif self.kind == "fleets":
                for i, y in enumerate(ROW_Y):
                    x = self.f[i]
                    if at == (620, y):
                        x.update(repair=3, sel=False)
                    elif at == (100, y):
                        x["sel"] = not x["sel"]
                if at == SEND_AT:
                    for x in self.f:
                        if x["sel"]:
                            x.update(sent=x["sent"] + 1, sel=False,
                                     status="marching",
                                     damaged_when_sent=x["bar"] < 0.97)
                    self.kind = "map"                # 鏡頭仍在城市上


REAL_PLAN = siege.plan


def run(game, seconds=3.0):
    """用假遊戲跑真正的 main()。回傳 (是否收工, 印出來的訊息)。"""
    tmp = tempfile.mkdtemp()
    said = []
    try:
        siege_bot.OUT = tmp
        siege_bot.STOP_FILE = os.path.join(tmp, "STOP")
        siege_bot.SETTLE = 0.02
        siege_bot.signal = types.SimpleNamespace(signal=lambda *a, **k: None,
                                                 SIGINT=2)
        siege_bot.pick_window = lambda app: {"pid": 1, "wid": 1, "owner": "水世界",
                                             "title": "", "x": 0, "y": 0,
                                             "w": W, "h": H}
        siege_bot.grab = lambda win: np.zeros((H, W, 3), np.uint8)
        siege_bot.img_scale = lambda win, img: 1.0
        siege_bot.ocr = lambda img, *a, **k: []
        siege_bot.covered_by = lambda *a, **k: []
        siege_bot.keep_awake = lambda: None
        siege_bot.notify = lambda *a: said.append(("通知",) + a)
        siege_bot.click_bg = lambda win, x, y, s=1.0, **k: game.tap((x, y)) or (x, y)
        siege_bot.click_front = siege_bot.click_bg
        siege.read = lambda img, items=None, ocr_fn=None: game.screen()

        def fast_plan(*a, **k):                    # 等待縮短，不必真的等倒數
            act = REAL_PLAN(*a, **k)
            if act.kind == "wait":
                act.seconds = 0.02
            return act
        siege.plan = fast_plan

        sys.argv = ["siege_bot.py", "--target", "防守堡壘F2", "--until", "23:59"]
        done = threading.Event()
        t = threading.Thread(target=lambda: (siege_bot.main(), done.set()),
                             daemon=True)
        t.start()
        done.wait(timeout=seconds)
        if not done.is_set():
            open(siege_bot.STOP_FILE, "w").close()
            done.wait(timeout=10)
        return done.is_set(), said
    finally:
        siege.plan = REAL_PLAN
        shutil.rmtree(tmp, ignore_errors=True)


fails = []


def check(name, got, want):
    ok = got == want
    print(f"[{'ok  ' if ok else 'FAIL'}] {name}: {got}")
    if not ok:
        print(f"        預期 {want}")
        fails.append(name)


print("── 正常情況：第一次前往只移鏡頭，點正中央再前往才出征 ──")
game = FakeGame()
finished, _ = run(game)
f1, f2, f3 = game.f
print(f"點了 {len(game.log)} 下")
check("程式有收工", finished, True)
check("第二支（一開始就完好）被派出去", f2["sent"] >= 1, True)
check("第一支（受損）修好後也被派出去", f1["sent"] >= 1, True)
check("第一支被派出去時已經修好", f1.get("damaged_when_sent", False), False)
check("沒有任何一支在受損狀態被派出",
      any(x.get("damaged_when_sent") for x in game.f), False)
check("駐防中的第三支從沒被點過",
      any(at in ((100, ROW_Y[2]), (620, ROW_Y[2])) for _, at in game.log), False)
check("有點過正中央的城市（第二次叫出彈窗的方式）",
      any(at == CENTER_AT for _, at in game.log), True)
first_dialog = next(i for i, (k, _) in enumerate(game.log) if k == "fleets")
gos = sum(1 for k, at in game.log[:first_dialog] if at == GO_AT)
check("第一次進到出征畫面前按了兩次前往（跟影片一樣）", gos, 2)
first_send = next(i for i, (k, at) in enumerate(game.log) if at == SEND_AT)
check("第一次出征前，受損又被勾著的第一支已經送修或取消",
      any(at in ((620, ROW_Y[0]), (100, ROW_Y[0]))
          for _, at in game.log[:first_send]), True)

print("\n── 壞掉的情況：前往永遠只移鏡頭、不開出征畫面 ──")
game = FakeGame(go_ever_opens=False)
finished, said = run(game, seconds=5.0)
gos = sum(1 for _, at in game.log if at == GO_AT)
print(f"點了 {len(game.log)} 下，其中前往 {gos} 次")
check("不會無限繞圈，自己停下來", finished, True)
check("前往最多按幾次就放棄", gos <= siege_bot.GO_WITHOUT_DIALOG + 1, True)
check("有跳通知請人看", any(s[0] == "通知" for s in said), True)

print()
if fails:
    print(f"{len(fails)} 個失敗：", fails)
    print("點擊順序：", game.log)
    sys.exit(1)
print("全部通過。")
