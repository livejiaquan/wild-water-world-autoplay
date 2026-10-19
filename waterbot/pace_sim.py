"""用真實錄影模擬主迴圈的節奏，比較「固定間隔」與「依畫面調整」的差別。

量兩件事：
  * 要做幾次 OCR（等於 CPU 負擔）
  * 反應延遲：該動作的畫面出現後，過多久才會被看到

用法: pace_sim.py <錄影檔>
"""
import sys

import cv2

from detect import classify
from ocr import ocr

import bot as B

ACTIONABLE = set(B.ACTIONS)


def timeline(path, step=0.25):
    """先把整支影片以細間隔判讀一次，當作「真實狀態時間軸」。"""
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    dur = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / fps
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    out, t = [], 0.0
    while t < dur:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            break
        s = classify(ocr(frame), w, h)
        out.append((round(t, 2), s.state, s.countdown))
        t += step
    cap.release()
    return out, step, dur


def at(tl, step, t):
    i = min(int(t / step), len(tl) - 1)
    return tl[i][1], tl[i][2]


def simulate(tl, step, dur, adaptive, base=0.5):
    """跑一遍迴圈，回傳 (OCR次數, [每次動作的延遲秒數])。"""
    t, looks, lags = 0.0, 0, []
    seen_since = {}
    # 每個「可動作畫面」第一次出現的時間
    prev = None
    starts = []
    for ts, st, _ in tl:
        if st != prev:
            if st in ACTIONABLE:
                starts.append([ts, None])    # [出現時間, 被看到的時間]
            prev = st
    si = 0

    while t < dur:
        st, cd = at(tl, step, t)
        looks += 1
        # 記錄這次「看」有沒有抓到某個尚未被發現的動作畫面
        while si < len(starts) and starts[si][0] < t and starts[si][1] is None:
            s_t, _ = starts[si]
            cur, _ = at(tl, step, t)
            if cur == at(tl, step, s_t)[0]:
                starts[si][1] = t
                si += 1
            else:
                si += 1            # 畫面已經過去了，算漏掉
            break

        if st in ACTIONABLE:
            t += B.MIN_SETTLE if adaptive else 0.3
            t += 0.15              # 點擊本身耗時
            continue
        if adaptive and st == "BATTLE" and cd:
            t += min(B.MAX_NAP, max(B.FAST_POLL, cd - B.COUNTDOWN_MARGIN))
        else:
            t += base
    for s_t, seen in starts:
        if seen is not None:
            lags.append(seen - s_t)
    return looks, lags


def main():
    path = sys.argv[1]
    print("先建立真實狀態時間軸（這步比較久）...")
    tl, step, dur = timeline(path)
    states = {}
    for _, st, _ in tl:
        states[st] = states.get(st, 0) + 1
    print(f"影片 {dur:.0f}s，取樣 {len(tl)} 點：", dict(states), "\n")

    configs = [("固定 0.5s（目前）", False, 0.5),
               ("依畫面調整 base0.5", True, 0.5),
               ("依畫面調整 base0.35", True, 0.35),
               ("依畫面調整 base0.25", True, 0.25)]
    for name, adaptive, base in configs:
        looks, lags = simulate(tl, step, dur, adaptive, base)
        avg = sum(lags) / len(lags) if lags else 0
        print(f"{name:<22} OCR {looks:4d} 次   "
              f"平均延遲 {avg:.2f}s   最久 {max(lags) if lags else 0:.2f}s")


if __name__ == "__main__":
    main()
