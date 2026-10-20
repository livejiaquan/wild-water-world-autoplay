"""在一批影片裡找出含有指定文字的畫面，並把那幾幀存下來。

用途：要新增一個畫面的支援時，先確認手上的素材裡到底有沒有拍到它。

用法: find_text.py <影片資料夾> <關鍵字,關鍵字,...> [取樣間隔秒]
輸出: out/found/<關鍵字>_<影片>_<秒>.png
"""
import glob
import os
import sys

import cv2

from ocr import ocr

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out", "found")


def main():
    folder = sys.argv[1]
    keys = [k.strip() for k in sys.argv[2].split(",") if k.strip()]
    step = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0
    os.makedirs(OUT, exist_ok=True)

    vids = sorted(sum((glob.glob(os.path.join(folder, f"*.{e}"))
                       for e in ("mp4", "mkv", "webm")), []))
    print(f"在 {len(vids)} 支影片裡找 {keys}，每 {step}s 取一幀\n")

    hits = 0
    for v in vids:
        cap = cv2.VideoCapture(v)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        dur = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / fps
        name = os.path.splitext(os.path.basename(v))[0]
        print(f"--- {name}  {dur/60:.1f} 分")
        t = 0.0
        while t < dur:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, frame = cap.read()
            if not ok:
                break
            for text, cx, cy, conf in ocr(frame):
                for k in keys:
                    if k in text:
                        p = os.path.join(OUT, f"{k}_{name}_{t:.0f}s.png")
                        cv2.imwrite(p, frame)
                        print(f"    @{t:6.0f}s  「{text}」({cx},{cy}) "
                              f"conf={conf:.2f}  -> {os.path.basename(p)}")
                        hits += 1
                        break
            t += step
        cap.release()

    print(f"\n共命中 {hits} 次，圖存在 {OUT}")


if __name__ == "__main__":
    main()
