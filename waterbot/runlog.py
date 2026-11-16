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


def _width(s):
    """字串在等寬終端機裡佔幾格。中日文字是兩格，不是一格。"""
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def pad(s, cols):
    """補空白到指定格數，中文字算兩格，表格才對得齊。"""
    return s + " " * max(0, cols - _width(s))


def human_time(seconds):
    """把秒數寫成人看得懂的樣子：90 -> 1分30秒。"""
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds}秒"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m}分{s}秒" if s else f"{m}分"
    h, m = divmod(m, 60)
    return f"{h}小時{m}分" if m else f"{h}小時"


CLEARS_NAME = "通關紀錄.txt"
HEADER_LINES = 2          # 表頭一行 + 分隔線一行


def _header():
    return [pad("關卡", 8) + pad("通過時間", 20) + pad("花了多久", 12)
            + "試了幾次\n", "─" * 24 + "\n"]


def _read_rows(path):
    """讀出既有的紀錄列（不含表頭）。檔案不存在就回空的。"""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    return [l for l in lines[HEADER_LINES:] if l.strip()]


def _write_rows(path, rows):
    """整份重寫。先寫暫存檔再換名，寫到一半被中斷也不會弄壞原檔。"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.writelines(_header() + rows)
    os.replace(tmp, path)


class RunLog:
    def __init__(self, outdir, clears_path=None):
        self.dir = outdir
        # 通關紀錄是給人看的，預設放在 outdir；主程式會把它放到主目錄，
        # 也就是使用者雙擊 start.command 的那個資料夾，不用再往下找。
        self.clears_path = clears_path or os.path.join(outdir, CLEARS_NAME)
        self._migrate_clears()
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

    # ---- 通關紀錄（給人看的，不是給程式看的）-----------------------
    def _migrate_clears(self):
        """把舊位置（out 資料夾裡）的紀錄搬到新位置，並改成最新在上。

        舊版是一筆一筆往下加，所以檔案裡的順序就是時間順序，
        整個倒過來就是最新在上。只在新位置還沒有檔案時做，做過就不會再做。
        """
        old = os.path.join(self.dir, CLEARS_NAME)
        new = self.clears_path
        if os.path.abspath(old) == os.path.abspath(new):
            return
        if os.path.exists(new) or not os.path.exists(old):
            return
        rows = _read_rows(old)
        _write_rows(new, list(reversed(rows)))
        os.remove(old)

    def clear(self, stage, seconds, attempts):
        """記下一關通過了，連同花多久、試了幾次。

        單獨寫一個檔案，格式排整齊、用詞白話，讓不看 log 的人
        也能一眼知道卡在哪一關、哪一關是什麼時候過的。

        **最新的放最上面**：使用者回饋每次打開都要往下拉才看得到
        最近的進度。紀錄一天也就幾十筆，整份重寫的成本可以忽略。
        """
        row = (pad(str(stage), 8)
               + pad(f"{datetime.now():%m/%d %H:%M:%S}", 20)
               + pad(human_time(seconds), 12)
               + f"{attempts} 次\n")
        rows = _read_rows(self.clears_path)
        _write_rows(self.clears_path, [row] + rows)
        self.line(f"[通關] 第{stage}關 耗時{human_time(seconds)} "
                  f"嘗試{attempts}次")
        return self.clears_path

    # ---- 收尾 -----------------------------------------------------
    def finish(self, stats, reason):
        self.line(f"結束：{reason}")
        self.line("統計： " + "  ".join(f"{k}×{v}" for k, v in
                                      sorted(stats.items(), key=lambda x: -x[1])))
        self.line("=" * 60)
        self._log.close()
        self._csvf.close()
