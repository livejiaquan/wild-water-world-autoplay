"""把一批 PNG 丟進 Vision OCR，印出每張讀到的文字與位置，用來設計狀態判斷。"""
import sys, time, glob, os
import cv2
from ocr import ocr

for path in sorted(glob.glob(sys.argv[1])):
    img = cv2.imread(path)
    h, w = img.shape[:2]
    t0 = time.perf_counter()
    res = ocr(img)
    dt = (time.perf_counter() - t0) * 1000
    print(f"\n=== {os.path.basename(path)}  {w}x{h}  OCR {dt:.0f}ms ===")
    for text, cx, cy, conf in sorted(res, key=lambda r: r[2]):
        print(f"  ({cx:4d},{cy:4d}) conf={conf:.2f}  {text}")
