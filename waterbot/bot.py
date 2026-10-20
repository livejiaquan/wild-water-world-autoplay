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
from collections import Counter, deque
import signal
import sys
import time

from detect import classify
from keys import Keys
from ocr import ocr
from runlog import RunLog, human_time
from winio import find_windows, grab, click_bg, img_scale, covered_by

HERE = os.path.dirname(os.path.abspath(__file__))
STOP_FILE = os.path.join(HERE, "STOP")
OUT = os.path.join(HERE, "out")

# 哪些狀態要點、點完最多等多久（秒）。這只是上限：點完會以 FAST_POLL 的
# 節奏快速複查，畫面一離開原狀態就立刻往下，不會傻等滿。
ACTIONS = {
    "DEFEAT":       ("再戰一次", 2.5),
    "VICTORY":      ("下一關",   2.5),
    "SKIPPABLE":    ("跳過",     1.2),
    "STAGE_SELECT": ("開戰",     3.0),
    "MAIN_MENU":    ("闖關",     3.0),
}

# 節奏是依畫面調整的，因為每種等待的性質不一樣：
#   * 剛點完「跳過」→ 結果不是勝利就是失敗，幾乎立刻出現，要盯緊。
#   * 戰鬥中還在倒數 → 還要幾秒是畫面上寫好的，沒必要一直看，
#     直接睡到快結束再醒來，省下大量 OCR。
FAST_POLL = 0.12      # 剛點完、等畫面轉場時的複查間隔
MIN_SETTLE = 0.15     # 點完至少先等這麼久再看，避免看到點擊前的殘影
NAP_CHUNK = 0.5          # 長時間等待切成小段，Ctrl-C 和 STOP 才會即時生效
MAX_NAP = 3.0            # 倒數再長也不會一次睡超過這麼久 —— 戰鬥有可能
                         # 在倒數結束前就分出勝負，睡滿會慢一拍

# 所有按鈕都在畫面下方這一段。剛點完、等結果出現的那幾百毫秒只掃這一條，
# 實測 OCR 從 112ms 降到 61ms，而且會觸發動作的判讀結果完全一致。
# 其餘時候仍掃全張，才讀得到關卡編號與結算橫幅。
BAND_TOP = 0.68

# 關卡編號要連續讀到同一個值幾次才採信。OCR 偶爾會把某一位數字認錯
# （實際遇過 885 被讀成 835），單次讀數不可靠，但誤讀是零星的，
# 正確值一定佔多數。用已經在做的那些幀投票，不需要額外 OCR，所以不會變慢。
STAGE_VOTES = 7          # 參考最近幾次讀數
STAGE_MIN_VOTES = 2      # 至少要有幾票才算數


def next_wait(screen, idle_interval):
    """決定下一次什麼時候看畫面，回傳 (要等幾秒, 下一圈是否只掃下方條)。

    戰鬥中畫面會寫「還要 N 秒才能跳過」，但那個 N 是整數：顯示「1 秒」時，
    真實剩餘落在 0 到 1 秒之間。所以**最後一秒不能用睡的** ——
    睡下去最壞會比跳過鍵晚 0.75 秒才發現，比固定輪詢還慢。
    改成還早時睡掉（省 OCR），剩最後一秒才密集盯著（搶反應）。
    """
    if screen.state == "BATTLE" and screen.countdown:
        if screen.countdown >= 2:
            wait = min(MAX_NAP, screen.countdown - 1.0)
            # 被 MAX_NAP 截斷代表醒來時還在倒數中，那一圈仍要掃全張
            return wait, (screen.countdown - 1.0) <= MAX_NAP
        return FAST_POLL, True          # 最後一秒，緊盯著跳過鍵
    return idle_interval, False


def confirmed_stage(votes):
    """從最近的讀數裡取多數，票數不足就回 None（寧可不知道也不要猜錯）。"""
    if not votes:
        return None
    val, n = Counter(votes).most_common(1)[0]
    return val if n >= STAGE_MIN_VOTES else None

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
    ap.add_argument("--interval", type=float, default=0.5, help="每幾秒看一次")
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
    kb = Keys()
    state = {"paused": False}

    log.say(f"每 {args.interval}s 看一次。")
    if kb.ok:
        log.say("按 空白鍵 暫停／繼續，按 q 結束。")
    else:
        log.say("停止：Ctrl-C 或 touch STOP")
    if args.dry_run:
        log.say("** 乾跑模式：只會說它想點哪裡，不會真的點 **")
    log.say(f"紀錄寫在 {OUT}/run.log")
    log.say(f"通關紀錄：{OUT}/通關紀錄.txt")

    last_state, last_change = None, time.time()
    click_times, stage_seen, stats = [], None, {}
    stage_started = time.time()   # 目前這一關是什麼時候開始的
    attempts = 0                  # 這一關失敗重試了幾次
    cleared = []                  # 這次執行通過了哪幾關
    stage_votes = deque(maxlen=STAGE_VOTES)   # 最近幾次讀到的關卡編號
    victory_pending = False       # 點了「下一關」，還在等畫面離開勝利頁
    victory_stage = None          # 點下去的當下，確認過的關卡編號
    waking_for_skip = False       # 這一圈是倒數睡醒的，直接找「跳過」
    reason = "正常結束"
    last_shot = {}        # 狀態 -> 上次存圖時間，避免同一種狀況狂存
    pending = None        # (剛點過的狀態, 等待截止時間)

    def read(img, band_only):
        """OCR 一張截圖。band_only 時只掃下方按鈕區，座標換算回整張。"""
        if not band_only:
            return ocr(img)
        y0 = int(img.shape[0] * BAND_TOP)
        return [(t, x, y + y0, c) for t, x, y, c in ocr(img[y0:])]

    def handle_keys():
        """處理按鍵。回傳 False 代表使用者要結束。"""
        k = kb.get()
        if k is None:
            return True
        if k == "q":
            log.say("按了 q，收工。")
            return False
        if k in (" ", "p"):
            state["paused"] = not state["paused"]
            if state["paused"]:
                log.say("⏸  已暫停。你可以自己操作遊戲，"
                        "按空白鍵繼續（按 q 結束）。")
            else:
                kb.drain()
                log.say("▶️  繼續。")
        return True

    def wait_while_paused():
        """暫停期間什麼都不做，只等按鍵。回傳 False 代表要結束。"""
        while state["paused"] and running:
            if os.path.exists(STOP_FILE):
                return False
            if not handle_keys():
                return False
            time.sleep(0.08)
        return True

    def nap(seconds):
        """睡一段時間，但切成小段，讓 Ctrl-C 和 STOP 檔能即時生效。"""
        end = time.time() + seconds
        while running and time.time() < end:
            if os.path.exists(STOP_FILE):
                return
            if not handle_keys() or state["paused"]:
                return          # 交給主迴圈處理暫停或結束
            time.sleep(min(0.1, max(0.0, end - time.time())))

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

            if not handle_keys():
                reason = "使用者按鍵結束"
                break
            if state["paused"]:
                paused_at = time.time()
                if not wait_while_paused():
                    reason = "使用者在暫停中結束"
                    break
                # 暫停的時間不算在「卡住」和「這一關花多久」裡面
                paused_for = time.time() - paused_at
                last_change += paused_for
                stage_started += paused_for
                continue

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
            # 只掃下方按鈕區的時機有兩個，都是「知道要找哪顆按鈕」的時候：
            #   * 剛點完，在等畫面轉場（結果鍵在下方）
            #   * 剛從倒數結束醒來，在等「跳過」出現（也在下方）
            # 兩者都省掉約 50ms 的 OCR。
            items = read(img, band_only=bool(pending) or waking_for_skip)
            waking_for_skip = False
            s = classify(items, w, h)
            stats[s.state] = stats.get(s.state, 0) + 1

            # ---- 通關事件：以「點了下一關」為準 ----
            # 不拿關卡編號當通關訊號。OCR 偶爾會把 885 讀成 835 這種
            # 一位數誤認，若靠編號變化判斷，一次誤讀就會記下一筆假的通關，
            # 甚至讓 --stop-after-stage 提早收工。
            # 點擊是我們自己做的事，不會被 OCR 誤判，所以用它當真憑據；
            # 而且要等勝利畫面真的消失才算數，避免點沒生效又點一次被重複計。
            if victory_pending and s.state != "VICTORY":
                victory_pending = False
                took = time.time() - stage_started
                label = victory_stage if victory_stage else "?"
                log.say(f"🎉 第 {label} 關通過！"
                        f"花了 {human_time(took)}，試了 {attempts} 次")
                log.clear(label, took, attempts)
                cleared.append(victory_stage)
                stage_started = time.time()
                attempts = 0
                stage_votes.clear()      # 換關了，舊的讀數不再參考

            # ---- 關卡編號：多數決才採信，單次誤讀不算 ----
            if s.stage:
                stage_votes.append(s.stage)
            cur = confirmed_stage(stage_votes)
            if cur and cur != stage_seen:
                if stage_seen is not None and cur != stage_seen + 1:
                    log.line(f"[注意] 關卡編號從 {stage_seen} 變成 {cur}，"
                             f"不是 +1。可能是辨識誤差或一次過了多關。")
                stage_seen = cur
                log.say(f"── 目前第 {cur} 關 ──")
                if args.stop_after_stage and cur >= args.stop_after_stage:
                    reason = f"已達第 {cur} 關"
                    log.say(f"達成目標，收工。")
                    break

            if s.state != last_state:
                last_state, last_change = s.state, time.time()
            elif time.time() - last_change > args.max_stuck:
                reason = f"卡在 {s.state} 超過 {args.max_stuck:.0f} 秒"
                log.say(f"卡在 {s.state} 太久，停下來讓人看看。")
                log.snapshot(img, "stuck", items, f"卡在 {s.state}")
                break

            # ---- 剛點過：畫面還沒離開原狀態就繼續快速等，不重複點 ----
            if pending:
                p_state, p_deadline = pending
                now = time.time()
                if s.state == p_state and now < p_deadline:
                    time.sleep(FAST_POLL)
                    continue
                pending = None

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
                    if s.state == "DEFEAT":
                        attempts += 1
                    elif s.state == "VICTORY":
                        victory_pending = True
                        victory_stage = stage_seen
                    log.say(f"{s.state:<13} 點了「{label}」@螢幕({gx},{gy})")
                    log.action(s.state, s.stage, label, (gx, gy), s.note)
                pending = (s.state, time.time() + wait)
                time.sleep(MIN_SETTLE)
                continue

            # ---- 看不懂的畫面：不動作，但留證據 ----
            if s.state == "UNKNOWN":
                if maybe_snapshot("unknown", img, items, "無法判斷的畫面"):
                    log.say("看不懂這個畫面，沒動作（細節寫進 log 了）")
                    log.action(s.state, s.stage, "（不動作）", "", "")

            # ---- 依畫面決定下一次什麼時候看 ----
            # 戰鬥中且畫面寫著還要幾秒才能跳過：那幾秒是固定的，
            # 直接睡到快結束，省掉中間每一次 OCR。
            wait_for, waking_for_skip = next_wait(s, args.interval)
            if wait_for > NAP_CHUNK:
                nap(wait_for)
            else:
                time.sleep(wait_for)

    except Exception as e:                      # noqa: BLE001
        reason = f"程式出錯: {type(e).__name__}: {e}"
        log.say(f"程式出錯了：{e}")
        log.say(f"詳細堆疊寫在 {OUT}/run.log")
        log.exception("主迴圈", e)
        kb.restore()
        log.finish(stats, reason)
        return 2

    if cleared:
        known = [c for c in cleared if c]
        if known:
            log.say(f"這次通過 {len(cleared)} 關："
                    f"第 {known[0]} 關 → 第 {known[-1]} 關")
        else:
            log.say(f"這次通過 {len(cleared)} 關（關卡編號沒讀到）")
        log.say(f"明細看 {OUT}/通關紀錄.txt")
    else:
        log.say("這次沒有通過新的關卡。")
    log.say("統計： " + "  ".join(f"{k}×{v}" for k, v in
                                sorted(stats.items(), key=lambda x: -x[1])))
    log.say(f"完整紀錄：{OUT}/run.log")
    kb.restore()
    log.finish(stats, reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
