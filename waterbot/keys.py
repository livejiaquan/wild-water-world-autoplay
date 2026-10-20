"""讀終端機的按鍵，不會卡住程式。

用途是讓人在不關掉視窗的情況下暫停、繼續、結束。
只用標準函式庫，不需要安裝任何東西。

沒有終端機可讀時（例如被程式呼叫、輸出導向檔案）會自動停用，
所有操作都變成不做事，這樣測試和自動化不會被影響。
"""
import os
import sys


class Keys:
    def __init__(self, enabled=True):
        self.ok = False
        self._saved = None
        if not enabled or not sys.stdin.isatty():
            return
        try:
            import termios
            import tty
            self._termios = termios
            self._fd = sys.stdin.fileno()
            self._saved = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)       # 按鍵立刻可讀，不用等 Enter
            self.ok = True
        except Exception:                 # noqa: BLE001 — 沒終端機就算了
            self._saved = None

    def get(self):
        """回傳剛按下的那個鍵（小寫），沒有就回 None。不會等待。"""
        if not self.ok:
            return None
        import select
        try:
            r, _, _ = select.select([sys.stdin], [], [], 0)
            if not r:
                return None
            ch = os.read(self._fd, 1).decode("utf-8", "ignore")
            return ch.lower() if ch else None
        except Exception:                 # noqa: BLE001
            return None

    def drain(self):
        """把累積的按鍵清掉，避免暫停期間亂按的鍵在繼續後一次湧出。"""
        while self.get() is not None:
            pass

    def restore(self):
        if self._saved is not None:
            try:
                self._termios.tcsetattr(self._fd, self._termios.TCSADRAIN,
                                        self._saved)
            except Exception:             # noqa: BLE001
                pass
            self._saved = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.restore()
        return False
