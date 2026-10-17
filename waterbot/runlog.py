"""紀錄。目標是出事之後，光看檔案就能查出原因，不必在場。

寫三種東西到 out/：
  run.log            人看的流水帳，含錯誤與當下的 OCR 內容
  run.csv            每個動作一列，方便用 Numbers / Excel 開
  shots/*.png        看不懂或卡住的畫面，存圖佐證
"""
import csv
import os
import sys
import traceback
from datetime import datetime

import cv2


class RunLog:
    def __init__(self, outdir):
        self.dir = outdir
        self.shots = os.path.join(outdir, "shots")
        os.makedirs(self.shots, exist_ok=True)
        self.logpath = os.path.join(outdir, "run.log")
        self.csvpath = os.path.join(outdir, "run.csv")
        self._log = open(self.logpath, "a", encoding="utf-8")
        new = not os.path.exists(self.csvpath) or os.path.getsize(self.csvpath) == 0
        self._csvf = open(self.csvpath, "a", newline="", encoding="utf-8")
        self._csv = csv.writer(self._csvf)
        if new:
            self._csv.writerow(["時間", "狀態", "關卡", "動作", "座標", "備註"])
        self.line("=" * 60)
        self.line(f"開始執行  {datetime.now():%Y-%m-%d %H:%M:%S}")
        self.line(f"Python {sys.version.split()[0]}  於 {os.uname().sysname} "
                  f"{os.uname().release}")

    # ---- 基本輸出 -------------------------------------------------
    def line(self, msg, echo=False):
        stamp = f"{datetime.now():%H:%M:%S}"
        self._log.write(f"{stamp}  {msg}\n")
        self._log.flush()
        if echo:
            print(f"{stamp}  {msg}")

    def say(self, msg):
        """同時印到畫面和寫進 log。"""
        self.line(msg, echo=True)

    def action(self, state, stage, action, coord, note=""):
        self._csv.writerow([f"{datetime.now():%H:%M:%S}", state, stage,
                            action, coord, note])
        self._csvf.flush()

    # ---- 出事時留證據 ---------------------------------------------
    def snapshot(self, img, tag, ocr_items=None, note=""):
        """存下畫面，並把當時 OCR 讀到的每一行寫進 log。

        卡住的原因九成是「遊戲出現了沒看過的畫面」或「字被認錯」，
        這兩種都只有把原始 OCR 內容記下來才查得出來。
        """
        name = f"{tag}_{datetime.now():%Y%m%d_%H%M%S}.png"
        path = os.path.join(self.shots, name)
        try:
            cv2.imwrite(path, img)
        except Exception as e:
            self.line(f"[存圖失敗] {e}")
            path = "(存圖失敗)"
        self.line(f"[{tag}] {note}  -> {name}")
        if ocr_items is not None:
            if ocr_items:
                self.line(f"    當時畫面上讀到 {len(ocr_items)} 段文字：")
                for text, cx, cy, conf in sorted(ocr_items, key=lambda r: r[2]):
                    self.line(f"      ({cx:5d},{cy:5d}) conf={conf:.2f}  "
                              f"{text!r}")
            else:
                self.line("    當時畫面上一個字都沒讀到"
                          "（遊戲可能在載入，或截到的是空白視窗）")
        return path

    def exception(self, where, exc):
        self.line(f"[例外] 在 {where}: {type(exc).__name__}: {exc}")
        for ln in traceback.format_exc().rstrip().splitlines():
            self.line(f"    {ln}")

    # ---- 收尾 -----------------------------------------------------
    def finish(self, stats, reason):
        self.line(f"結束：{reason}")
        self.line("統計： " + "  ".join(f"{k}×{v}" for k, v in
                                      sorted(stats.items(), key=lambda x: -x[1])))
        self.line("=" * 60)
        self._log.close()
        self._csvf.close()
