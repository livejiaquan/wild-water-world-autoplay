"""回歸測試：每一張測試圖都是從真實遊戲畫面擷取的，不是合成的。

    ./waterbot/.venv/bin/python tests/test_detect.py

每個案例後面的註解說明它在防什麼。這些都是實測踩過的坑，
改 detect.py 之後請務必重跑。
"""
import os
import sys

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "waterbot"))

from detect import classify          # noqa: E402
from ocr import ocr                  # noqa: E402

FIX = os.path.join(HERE, "fixtures")

# (檔名, 預期狀態, 預期點擊位置, 這個案例在防什麼)
CASES = [
    ("stage_select.jpg", "STAGE_SELECT", None,
     "關卡畫面要認得出「開戰」"),
    ("battle_countdown.jpg", "BATTLE", None,
     "戰鬥中、跳過鍵還在倒數時要乖乖等，不能亂點"),
    ("skippable.jpg", "SKIPPABLE", (675, 1512),
     "倒數結束、跳過鍵出現就要點它，省掉整場戰鬥"),
    ("defeat.jpg", "DEFEAT", (479, 1284),
     "戰鬥失敗要點「再戰一次」"),
    ("victory_clean.jpg", "VICTORY", (711, 511),
     "勝利要點「下一關」(711)，不能點左邊的「返回」(568)"),
    ("victory_btn_countdown.jpg", "VICTORY", (712, 512),
     "按鈕文字是「下一關(4)」帶倒數，尾端數字不能害比對失敗"),
    ("victory_garbled_banner.jpg", "VICTORY", (723, 531),
     "橫幅被 OCR 讀成「挑郫膀朻」時，仍要靠按鈕認出這是勝利畫面"),
]

TOL = 12   # 座標容許誤差（像素）


def run():
    fails = []
    for name, want_state, want_click, why in CASES:
        path = os.path.join(FIX, name)
        img = cv2.imread(path)
        if img is None:
            fails.append(f"{name}: 讀不到測試圖")
            continue
        h, w = img.shape[:2]
        s = classify(ocr(img), w, h)

        bad = []
        if s.state != want_state:
            bad.append(f"狀態 {s.state} != 預期 {want_state}")
        if want_click is not None:
            if s.click is None:
                bad.append("沒給點擊座標")
            else:
                dx = abs(s.click[0] - want_click[0])
                dy = abs(s.click[1] - want_click[1])
                if dx > TOL or dy > TOL:
                    bad.append(f"座標 {s.click} 偏離預期 {want_click}")

        mark = "FAIL" if bad else "ok  "
        print(f"[{mark}] {name:<30} {s.state:<13} {s.click}")
        print(f"        ({why})")
        if bad:
            for b in bad:
                print(f"        !! {b}")
            fails.append(f"{name}: " + "; ".join(bad))

    print()
    if fails:
        print(f"{len(fails)} 個案例失敗：")
        for f in fails:
            print("  -", f)
        return 1
    print(f"全部 {len(CASES)} 個案例通過。")
    return 0


if __name__ == "__main__":
    sys.exit(run())
