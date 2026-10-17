#!/usr/bin/env python3
"""瘋狂水世界 自動刷關。

每隔一段時間截一次遊戲視窗 → OCR 讀出畫面上的字 → 判斷是哪個畫面
→ 只在認得的畫面上點已知的按鈕。游標會瞬移過去點一下再立刻回來，
鍵盤焦點不會被搶走。

    python3 bot.py --check      先檢查環境與權限
    python3 bot.py --list       列出目前所有視窗
    python3 bot.py --dry-run    只看它想點哪裡，不真的點
    python3 bot.py              開跑
停止：Ctrl-C，或在這個資料夾 touch STOP

刻意的取捨：看不懂的畫面一律不點，只存圖與 log。這遊戲有儲值介面，
寧可停下來等人，也不要在不認得的彈窗上亂點。
"""
import argparse
import os
import signal
import sys
import time

from detect import classify
from ocr import ocr
from runlog import RunLog
from winio import find_windows, grab, click_bg, img_scale, covered_by

HERE = os.path.dirname(os.path.abspath(__file__))
STOP_FILE = os.path.join(HERE, "STOP")
OUT = os.path.join(HERE, "out")

# 哪些狀態要點、點完等多久（秒）才值得再看一次
ACTIONS = {
    "DEFEAT":       ("再戰一次", 2.5),
    "VICTORY":      ("下一關",   2.5),
    "SKIPPABLE":    ("跳過",     1.5),
    "STAGE_SELECT": ("開戰",     3.0),
}

running = True


def on_sigint(*_):
    global running
    running = False
    print("\n收到中斷，收工。")


def pick_window(name_hint, verbose=False):
    wins = find_windows(min_size=300)
    if verbose:
        print("目前畫面上夠大的視窗：")
        for w in wins:
            print(f"  [{w['owner']}] {w['title']}  {w['w']}x{w['h']} "
                  f"@({w['x']},{w['y']})  pid={w['pid']}")
    cand = [w for w in wins
            if name_hint.lower() in (w["owner"] + " " + w["title"]).lower()]
    if not cand:
        return None
    cand.sort(key=lambda w: (w["h"] <= w["w"], -w["w"] * w["h"]))  # 直式優先
    return cand[0]


def build_parser():
    ap = argparse.ArgumentParser(
        description="瘋狂水世界 自動刷關",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--app", default="水世界", help="遊戲視窗名稱關鍵字")
    ap.add_argument("--interval", type=float, default=1.2, help="每幾秒看一次")
    ap.add_argument("--dry-run", action="store_true", help="只印不點")
    ap.add_argument("--list", action="store_true", help="列出所有視窗後結束")
    ap.add_argument("--check", action="store_true", help="檢查環境與權限後結束")
    ap.add_argument("--max-stuck", type=float, default=300,
                    help="同一個畫面卡住幾秒就停（預設 300）")
    ap.add_argument("--max-clicks-per-min", type=int, default=20,
                    help="每分鐘最多點幾下，超過視為失控（預設 20）")
    ap.add_argument("--stop-after-stage", type=int, default=None,
                    help="打到第幾關就收工")
    return ap


def main():
    args = build_parser().parse_args()

    if args.list:
        pick_window("", verbose=True)
        return 0
    if args.check:
        import preflight
        return preflight.main(args.app)

    signal.signal(signal.SIGINT, on_sigint)
    os.makedirs(OUT, exist_ok=True)
    if os.path.exists(STOP_FILE):
        os.remove(STOP_FILE)

    log = RunLog(OUT)
    log.line(f"參數: {vars(args)}")

    win = pick_window(args.app)
    if not win:
        log.say(f"找不到包含「{args.app}」的視窗。")
        log.say("請確認遊戲開著、沒有縮到最小，或用 --list 看它實際叫什麼名字。")
        log.finish({}, "找不到遊戲視窗")
        return 1

    log.say(f"盯著：[{win['owner']}] {win['title']} "
            f"{win['w']}x{win['h']} @({win['x']},{win['y']})")
    log.say(f"每 {args.interval}s 看一次。停止：Ctrl-C 或 touch STOP")
    if args.dry_run:
        log.say("** 乾跑模式：只會說它想點哪裡，不會真的點 **")
    log.say(f"紀錄寫在 {OUT}/run.log")

    last_state, last_change = None, time.time()
    click_times, stage_seen, stats = [], None, {}
    reason = "正常結束"
    last_shot = {}        # 狀態 -> 上次存圖時間，避免同一種狀況狂存

    def maybe_snapshot(tag, img, items, note, every=60.0):
        """同一種狀況最多每 every 秒留一張圖。

        不限制的話，一段長時間看不懂的畫面會每 1.2 秒寫一張 PNG，
        整晚跑下來足以塞爆硬碟。
        """
        now = time.time()
        if now - last_shot.get(tag, 0) < every:
            return False
        last_shot[tag] = now
        log.snapshot(img, tag, items, note)
        return True

    try:
        while running:
            if os.path.exists(STOP_FILE):
                reason = "看到 STOP 檔"
                log.say("收工。")
                break

            win = pick_window(args.app)   # 視窗可能被移動或縮放，每圈重抓
            if win is None:
                reason = "遊戲視窗消失"
                log.say("遊戲視窗不見了（關掉或最小化？），停止。")
                break

            try:
                img = grab(win)
            except RuntimeError as e:
                reason = f"截圖失敗: {e}"
                log.say(f"截圖失敗：{e}")
                break

            scale = img_scale(win, img)
            h, w = img.shape[:2]
            items = ocr(img)
            s = classify(items, w, h)
            stats[s.state] = stats.get(s.state, 0) + 1

            if s.stage and s.stage != stage_seen:
                stage_seen = s.stage
                log.say(f"── 目前第 {s.stage} 關 ──")
                if args.stop_after_stage and s.stage >= args.stop_after_stage:
                    reason = f"已達第 {s.stage} 關"
                    log.say(f"達成目標，收工。")
                    break

            if s.state != last_state:
                last_state, last_change = s.state, time.time()
            elif time.time() - last_change > args.max_stuck:
                reason = f"卡在 {s.state} 超過 {args.max_stuck:.0f} 秒"
                log.say(f"卡在 {s.state} 太久，停下來讓人看看。")
                log.snapshot(img, "stuck", items, f"卡在 {s.state}")
                break

            # ---- 認得畫面，但關鍵按鈕讀不到 ----
            # 不立刻收工：實測看過劇情對話框暫時蓋住「再戰一次」，
            # 十秒後就恢復正常。這裡只等待與記錄，真的卡住的話
            # 交給上面的 max-stuck 逾時處理。
            if s.state == "NEEDS_HUMAN":
                if maybe_snapshot("needs_human", img, items, s.note):
                    log.say(f"暫時讀不到按鈕，先等一下：{s.note}")
                    log.action(s.state, s.stage, "（等待）", "", s.note)
                time.sleep(args.interval)
                continue

            # ---- 要點的畫面 ----
            if s.state in ACTIONS and s.click:
                label, wait = ACTIONS[s.state]

                blockers = covered_by(win, s.click[0], s.click[1], scale)
                if blockers:
                    log.say(f"{s.state}：「{label}」被 {blockers[0]} 蓋住，這次不點")
                    log.action(s.state, s.stage, "（被遮擋跳過）", s.click,
                               ",".join(blockers))
                    time.sleep(args.interval)
                    continue

                click_times = [t for t in click_times if time.time() - t < 60]
                if len(click_times) >= args.max_clicks_per_min:
                    reason = f"一分鐘內點了 {len(click_times)} 下，不正常"
                    log.say(reason + "，停止。")
                    log.snapshot(img, "runaway", items, reason)
                    break

                if args.dry_run:
                    log.say(f"{s.state:<13} 想點「{label}」@{s.click}")
                    log.action(s.state, s.stage, f"（乾跑）{label}", s.click)
                else:
                    gx, gy = click_bg(win, s.click[0], s.click[1], scale)
                    click_times.append(time.time())
                    log.say(f"{s.state:<13} 點了「{label}」@螢幕({gx},{gy})")
                    log.action(s.state, s.stage, label, (gx, gy), s.note)
                time.sleep(wait)
                continue

            # ---- 看不懂的畫面：不動作，但留證據 ----
            if s.state == "UNKNOWN":
                if maybe_snapshot("unknown", img, items, "無法判斷的畫面"):
                    log.say("看不懂這個畫面，沒動作（細節寫進 log 了）")
                    log.action(s.state, s.stage, "（不動作）", "", "")

            time.sleep(args.interval)

    except Exception as e:                      # noqa: BLE001
        reason = f"程式出錯: {type(e).__name__}: {e}"
        log.say(f"程式出錯了：{e}")
        log.say(f"詳細堆疊寫在 {OUT}/run.log")
        log.exception("主迴圈", e)
        log.finish(stats, reason)
        return 2

    log.say("統計： " + "  ".join(f"{k}×{v}" for k, v in
                                sorted(stats.items(), key=lambda x: -x[1])))
    log.say(f"完整紀錄：{OUT}/run.log")
    log.finish(stats, reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
