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

from detect import classify, _close  # noqa: E402
from ocr import ocr                  # noqa: E402

# 文字比對規則。大部分來自實際踩過的誤判。
# (OCR讀到的字, 關鍵字, 應不應該算命中, 這條在防什麼)
MATCH_CASES = [
    ("開戰", "開戰", True,  "正常命中"),
    ("下一關4", "下一關", True,  "按鈕帶倒數「下一關(4)」，尾端數字要忽略"),
    ("下一闕", "下一闕", True,  "關→闕 誤認，靠清單裡的變體比對，不靠模糊"),
    ("再戟一次", "再戟一次", True,  "戰→戟 誤認，同樣走變體清單"),
    ("下一闕", "下一關", False, "不做模糊比對：變體必須明確列出才算"),
    ("下一页", "下一關", False, "真實詞彙，只差最後一字，絕不能當成過關鍵"),
    ("下一级", "下一關", False, "同上，出現在別款遊戲畫面上"),
    ("城战", "开战", False, "兩字關鍵字不得放寬：實測誤判成開戰"),
    ("甙战", "开战", False, "同上，出現在 648 元儲值畫面上"),
    ("提战", "开战", False, "同上，也在儲值畫面上"),
    ("挑戰", "開戰", False, "兩字關鍵字不得放寬"),
    ("那開戰進來", "開戰", False, "影片字幕整句話不得算成按鈕"),
]

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

    # 以下三張都曾被誤判成「該點」的畫面，必須維持在不動作的狀態。
    ("notclick_purchase.jpg", "UNKNOWN", None,
     "648 元儲值畫面：「甙战」曾被當成「开战」按鈕"),
    ("notclick_promo_nextpage.jpg", "UNKNOWN", None,
     "活動彈窗：「下一页」曾被當成「下一關」按鈕"),
    ("notclick_siege.jpg", "UNKNOWN", None,
     "攻城介面：「城战」曾被當成「开战」按鈕"),
]

TOL = 12   # 座標容許誤差（像素）


def run():
    fails = []

    print("── 文字比對規則 ──")
    for text, key, want, why in MATCH_CASES:
        got = _close(text, key, 1)
        mark = "ok  " if got == want else "FAIL"
        print(f"[{mark}] 「{text}」vs「{key}」-> {got}")
        print(f"        ({why})")
        if got != want:
            fails.append(f"比對「{text}」vs「{key}」: 得到 {got}，預期 {want}")

    print("\n── 真實畫面判讀 ──")
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
    print(f"全部 {len(CASES) + len(MATCH_CASES)} 個案例通過。")
    return 0


if __name__ == "__main__":
    sys.exit(run())
