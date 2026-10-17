"""盲審工具：跑一遍偵測器，然後把結果做成貼了標籤的拼圖讓人親自核對。

程式說自己準不準不算數。這支腳本的用途是產生「可以用眼睛驗」的證據：

  1. 每隔 N 秒取一幀，記下偵測器的判斷
  2. 依狀態分組，每組抽樣做成一張貼了標籤的拼圖
  3. 人看拼圖，逐格對照標籤說的對不對

用法: audit.py <影片資料夾> [取樣間隔秒] [每組抽幾張]
輸出: out/audit/<狀態>_NN.jpg 與 out/audit/verdicts.csv
"""
import csv
import glob
import os
import random
import sys

import cv2
import numpy as np

from detect import classify
from ocr import ocr

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out", "audit")

CELL_W, CELL_H = 300, 420      # 每格縮圖大小
COLS = 5
BAR = 46                       # 標籤列高度


def label_cell(img, lines):
    """把一幀縮成固定大小，上方加一條標籤。"""
    h, w = img.shape[:2]
    s = min(CELL_W / w, CELL_H / h)
    thumb = cv2.resize(img, (max(1, int(w * s)), max(1, int(h * s))),
                       interpolation=cv2.INTER_AREA)
    cell = np.full((CELL_H + BAR, CELL_W, 3), 30, np.uint8)
    y0 = BAR + (CELL_H - thumb.shape[0]) // 2
    x0 = (CELL_W - thumb.shape[1]) // 2
    cell[y0:y0 + thumb.shape[0], x0:x0 + thumb.shape[1]] = thumb
    for i, text in enumerate(lines[:2]):
        cv2.putText(cell, text, (6, 18 + i * 20), cv2.FONT_HERSHEY_SIMPLEX,
                    0.45, (255, 255, 255), 1, cv2.LINE_AA)
    return cell


def sheet(cells):
    rows = []
    for i in range(0, len(cells), COLS):
        chunk = cells[i:i + COLS]
        while len(chunk) < COLS:
            chunk.append(np.full_like(cells[0], 30))
        rows.append(np.hstack(chunk))
    return np.vstack(rows)


def main():
    folder = sys.argv[1]
    step = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
    per_state = int(sys.argv[3]) if len(sys.argv) > 3 else 15
    os.makedirs(OUT, exist_ok=True)
    random.seed(0)

    vids = sorted(sum((glob.glob(os.path.join(folder, f"*.{e}"))
                       for e in ("mp4", "mkv", "webm")), []))
    print(f"要審 {len(vids)} 支影片，每 {step}s 取一幀\n")

    rows = []          # (影片, 秒, 狀態, 點擊, 關卡, 備註)
    buckets = {}       # 狀態 -> [(frame, 說明)]

    for v in vids:
        cap = cv2.VideoCapture(v)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        dur = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / fps
        name = os.path.basename(v)
        print(f"--- {name}  {dur/60:.1f} 分")
        t = 0.0
        while t < dur:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, frame = cap.read()
            if not ok:
                break
            h, w = frame.shape[:2]
            s = classify(ocr(frame), w, h)
            rows.append((name, round(t, 1), s.state,
                         s.click or "", s.stage or "", s.note))
            shot = frame.copy()
            if s.click:
                cv2.circle(shot, s.click, 26, (0, 0, 255), 4)
                cv2.drawMarker(shot, s.click, (0, 0, 255),
                               cv2.MARKER_CROSS, 40, 2)
            buckets.setdefault(s.state, []).append(
                (shot, f"{name[:14]} @{t:.0f}s", f"{s.state} {s.click or ''}"))
            t += step
        cap.release()

    with open(os.path.join(OUT, "verdicts.csv"), "w", newline="",
              encoding="utf-8") as f:
        wtr = csv.writer(f)
        wtr.writerow(["影片", "秒", "狀態", "點擊", "關卡", "備註"])
        wtr.writerows(rows)

    print("\n=== 判斷分佈 ===")
    for st, items in sorted(buckets.items(), key=lambda x: -len(x[1])):
        print(f"  {st:<13} {len(items):4d} 幀")

    print("\n=== 產生核對拼圖 ===")
    for st, items in buckets.items():
        pick = random.sample(items, min(per_state, len(items)))
        cells = [label_cell(img, [l1, l2]) for img, l1, l2 in pick]
        path = os.path.join(OUT, f"{st}.jpg")
        cv2.imwrite(path, sheet(cells), [cv2.IMWRITE_JPEG_QUALITY, 80])
        print(f"  {st:<13} 抽 {len(pick):2d} 張 -> {os.path.basename(path)}")

    print(f"\n共 {len(rows)} 幀，明細在 {OUT}/verdicts.csv")
    print("紅圈處是程式打算點的位置。")


if __name__ == "__main__":
    main()
