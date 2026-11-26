#!/usr/bin/env python3
"""城戰自動派兵：一直把完好的艦隊派到指定目標，受損的先維修。

    python3 siege_bot.py --target 防守堡壘F2
    python3 siege_bot.py --target 防守堡壘F2 --dry-run    # 只說它想做什麼

流程（每次只做一個動作，做完重新看畫面確認，再決定下一步）：
    地圖  → 點左側清單的目標 → 城市彈窗
    彈窗  → 核對標題是不是目標 → 按「前往」→ 選擇艦隊
    艦隊  → 受損的按「維修」、完好空閒的勾選 → 出征
           → 都在忙就留在視窗裡等倒數

只派完好的艦隊、維修只等不加速、不碰任何要花鑽石的東西。
跟刷關程式（bot.py）完全分開，互不影響。
"""
import argparse
import os
import signal
import sys
import time
from datetime import datetime

import siege
from bot import (APP_HINTS, keep_awake, notify, pick_window)
from keys import Keys
from ocr import ocr
from runlog import RunLog
from winio import click_bg, click_front, covered_by, grab, img_scale

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
STOP_FILE = os.path.join(HERE, "STOP")

SETTLE = 0.6            # 點完等畫面動畫跑完再看（彈窗、視窗切換比刷關慢）
SAME_BEFORE_FRONT = 3   # 同一個動作重複幾次畫面都沒變，改用前景點擊
SAME_BEFORE_WARN = 8    # 重複幾次就跳通知
MAX_TAPS_PER_MIN = 40
GO_WITHOUT_DIALOG = 4   # 連按幾次「前往」都沒出現艦隊視窗，就判定流程卡住
WRONG_CITY_CONFIRM = 2  # 連續幾次讀到同一個「錯的城市」才算數（實測 F 會被讀成 P）
UNCLEAR_TITLE_MAX = 6   # 標題連續幾次讀不清楚，就退回去重點清單

running = True


def on_sigint(*_):
    global running
    running = False


def parse_until(s):
    h, m = (int(x) for x in s.split(":"))
    now = datetime.now()
    return now.replace(hour=h, minute=m, second=0, microsecond=0)


def main():
    ap = argparse.ArgumentParser(description="城戰自動派兵")
    ap.add_argument("--target", required=True,
                    help="左側清單上的目標名稱，例如 防守堡壘F2")
    ap.add_argument("--until", default="20:00",
                    help="幾點自動收工（預設 20:00，台灣時間城戰結束）")
    ap.add_argument("--app", default=",".join(APP_HINTS))
    ap.add_argument("--dry-run", action="store_true", help="只說它想做什麼，不點")
    args = ap.parse_args()

    if not siege.split_target(args.target):
        print(f"看不懂目標「{args.target}」。請照左側清單上的寫法，例如：防守堡壘F2")
        return 1
    until = parse_until(args.until)
    if datetime.now() >= until:
        print(f"現在已經過了 {args.until}，城戰應該結束了。"
              f"如果要繼續，用 --until 指定別的時間。")
        return 1

    signal.signal(signal.SIGINT, on_sigint)
    os.makedirs(OUT, exist_ok=True)
    if os.path.exists(STOP_FILE):
        os.remove(STOP_FILE)
    log = RunLog(OUT)
    log.line(f"城戰模式 參數: {vars(args)}")

    win = pick_window(args.app)
    if not win:
        log.say("找不到遊戲視窗。請確認遊戲開著、而且停在城戰地圖。")
        log.finish({}, "找不到遊戲視窗")
        return 1

    kb = Keys()
    keep_awake()
    log.say(f"城戰派兵：目標「{args.target}」，{args.until} 自動收工")
    log.say("只派耐久滿的艦隊；受損的按維修等它修好（不加速、不花鑽石）")
    if kb.ok:
        log.say("按 空白鍵 暫停／繼續，按 q 結束")
    if args.dry_run:
        log.say("** 乾跑模式：只說它想做什麼，不會真的點 **")

    paused = False
    last_why, same = None, 0
    warned = False
    taps, sends, repairs = [], 0, 0
    camera_on_city = False   # 鏡頭是否已經停在目標城市上
    center_tries = 0         # 點正中央叫彈窗試了幾次
    go_presses = 0           # 按了幾次前往還沒看到艦隊視窗
    wrong_city = (None, 0)   # (讀到的錯誤城市, 連續次數)
    unclear_title = 0        # 標題連續讀不清楚幾次
    reason = "正常結束"

    while running:
        if os.path.exists(STOP_FILE):
            reason = "看到 STOP 檔"
            break
        if datetime.now() >= until:
            reason = f"到 {args.until} 了，城戰結束"
            break
        k = kb.get()
        if k == "q":
            reason = "按了 q"
            break
        if k in (" ", "p"):
            paused = not paused
            log.say("⏸  已暫停，按空白鍵繼續" if paused else "▶️  繼續")
        if paused:
            time.sleep(0.1)
            continue

        win = pick_window(args.app)
        if win is None:
            reason = "遊戲視窗不見了"
            break
        img = grab(win)
        scale = img_scale(win, img)
        h, w = img.shape[:2]
        items = ocr(img)
        screen = siege.read(img, items)
        # 只拿畫面中間的字去檢查「要花錢嗎」：最上面的跑馬燈和
        # 最下面的聊天室常有別人在講鑽石，不能因此停下來
        middle = [i for i in items
                  if 0.12 * h < i[2] < 0.84 * h and "系統" not in i[0]]
        if screen.kind == "fleets":
            center_tries, go_presses = 0, 0
        elif screen.kind == "city" and siege.same_target(screen.city, args.target):
            center_tries = 0     # 點正中央叫出了正確的彈窗，這招有效
        act = siege.plan(screen, args.target, middle,
                         camera_on_city=camera_on_city,
                         center_tries=center_tries)

        # 標題讀成別的城市：先確認不是讀錯字。實測「堡壘F2」被讀成「堡壘P2」
        if act.kind == "reset":
            name = screen.city
            n = wrong_city[1] + 1 if wrong_city[0] == name else 1
            wrong_city = (name, n)
            if n < WRONG_CITY_CONFIRM:
                act = siege.Action("wait", seconds=0.3,
                                   why=f"標題讀到「{name}」，再確認一次")
        else:
            wrong_city = (None, 0)
        if act.why == "城市標題沒讀清楚，再看一次":
            unclear_title += 1
            if unclear_title >= UNCLEAR_TITLE_MAX:
                unclear_title = 0
                act = siege.Action("reset", why="標題一直讀不清楚，回去重點目標")
        else:
            unclear_title = 0

        if act.kind == "reset":
            hit = siege.find_target(
                siege.SiegeScreen("map", targets=siege._read_target_list(img, ocr)),
                args.target)
            log.say(act.why)
            act = (siege.Action("tap", hit[1], why=f"改點左側目標「{hit[0]}」")
                   if hit else siege.Action("wait", seconds=2, why="清單找不到目標"))

        if act.kind == "stop":
            log.say(act.why)
            log.snapshot(img, "siege_stop", items, act.why)
            notify("城戰派兵", act.why)
            reason = act.why
            break

        # 同一個動作一直重複 = 點了沒生效
        if act.why == last_why and act.kind == "tap":
            same += 1
        else:
            same = 0
            warned = False
        if act.why != last_why:
            log.say(act.why)
        last_why = act.why

        if act.kind == "wait":
            time.sleep(act.seconds)
            continue

        # ---- 點下去 ----
        if covered_by(win, act.at[0], act.at[1], scale):
            log.line(f"「{act.why}」的位置被別的視窗蓋住，先不點")
            time.sleep(1)
            continue
        taps = [t for t in taps if time.time() - t < 60]
        if len(taps) >= MAX_TAPS_PER_MIN:
            log.say("一分鐘內點太多下都沒進展，先緩 30 秒")
            notify("城戰派兵", "點很多次都沒進展，可能要看一下")
            time.sleep(30)
            taps = []
            continue
        if same >= SAME_BEFORE_WARN and not warned:
            log.snapshot(img, "siege_stuck", items, f"重複 {same} 次：{act.why}")
            notify("城戰派兵", f"一直在做「{act.why}」但畫面沒變")
            warned = True

        if args.dry_run:
            log.line(f"（乾跑）想點 {act.at}：{act.why}")
            time.sleep(1.5)
            continue
        if same >= SAME_BEFORE_FRONT:
            click_front(win, act.at[0], act.at[1], scale)
        else:
            click_bg(win, act.at[0], act.at[1], scale)
        taps.append(time.time())
        log.action("城戰", None, act.why, act.at, "")
        if act.why.startswith("出征"):
            sends += sum(f.ready and f.selected for f in screen.fleets)
            camera_on_city = True          # 出征完鏡頭還停在城市上
        elif "維修" in act.why:
            repairs += 1
        elif "按前往" in act.why:
            # 鏡頭沒對準時，前往只會把鏡頭移過去；下一步改點正中央的城市
            camera_on_city = True
            go_presses += 1
            if go_presses > GO_WITHOUT_DIALOG:
                log.say(f"連按 {go_presses} 次前往都沒出現艦隊視窗，先停下來")
                log.snapshot(img, "siege_go_loop", items, "前往一直沒開出艦隊視窗")
                notify("城戰派兵", "按前往一直沒出現出征畫面，需要看一下")
                reason = "前往一直沒開出艦隊視窗"
                break
        elif act.why.startswith("鏡頭已經在城市上"):
            center_tries += 1
        elif act.why.startswith("點左側目標") or act.why.startswith("改點左側目標"):
            camera_on_city, center_tries = False, 0
        time.sleep(SETTLE)

    kb.restore()
    log.say(f"收工：{reason}")
    log.say(f"這次共派出 {sends} 支艦隊、維修 {repairs} 次")
    log.finish({"出征": sends, "維修": repairs}, reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
