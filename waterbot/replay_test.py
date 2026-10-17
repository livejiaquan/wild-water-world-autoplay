"""離線回放測試：拿錄影當輸入，每 N 秒取一幀餵進狀態機，印出狀態時間軸。

用法: replay_test.py <影片> [取樣間隔秒]
"""
import sys, time
import cv2
from ocr import ocr
from detect import classify

path = sys.argv[1]
step = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0

cap = cv2.VideoCapture(path)
fps = cap.get(cv2.CAP_PROP_FPS)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
print(f"影片 {w}x{h} {fps:.0f}fps {total/fps:.1f}s，每 {step}s 取一幀\n")

prev = None
counts = {}
durations = []
t = 0.0
ocr_ms = []
while t < total / fps:
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
    ok, frame = cap.read()
    if not ok:
        break
    t0 = time.perf_counter()
    items = ocr(frame, fast=False)
    ocr_ms.append((time.perf_counter() - t0) * 1000)
    s = classify(items, w, h)
    counts[s.state] = counts.get(s.state, 0) + 1
    if s.state != prev:
        click = f" -> 點 {s.click}" if s.click else ""
        stage = f" [第{s.stage}關]" if s.stage else ""
        print(f"{t:6.1f}s  {s.state:<13}{stage}{click}  {s.note}")
        prev = s.state
    t += step

cap.release()
print(f"\n--- 統計 ---")
for k, v in sorted(counts.items(), key=lambda x: -x[1]):
    print(f"  {k:<13} {v:3d} 幀")
import statistics
print(f"  OCR(accurate) 中位數 {statistics.median(ocr_ms):.0f}ms  "
      f"最慢 {max(ocr_ms):.0f}ms")
