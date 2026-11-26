"""城戰畫面判讀的測試。所有測試圖都是從實際遊戲錄影擷取的。

預期答案是放大畫面逐列目視核對過的，不是程式自己說了算。
最重要的是最後一欄：**只有真的完好的艦隊才能被判成可以出征**。

    ./waterbot/.venv/bin/python tests/test_siege.py
"""
import os
import sys

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "waterbot"))

import siege   # noqa: E402

FIX = os.path.join(HERE, "fixtures", "siege")
fails = []


def check(name, got, want):
    ok = got == want
    print(f"[{'ok  ' if ok else 'FAIL'}] {name}: {got}")
    if not ok:
        print(f"        預期 {want}")
        fails.append(name)


def decision(f):
    if f.needs_repair:
        return "修"
    if f.ready:
        return "派"
    return "等"


# 檔名 -> 每一列 (狀態, 倒數秒數, 是否已勾選, 決定)
FLEETS = {
    # 第一支剛回來受損（耐久一半、有維修鈕）；第二支行軍中；第三支駐防
    "fleets_repair_needed": [("idle", None, True, "修"),
                             ("timer", 20, False, "等"),
                             ("garrison", None, False, "等")],
    # 第一支維修中（扳手倒數）；第二支修好空閒、耐久滿；第三支行軍中
    "fleets_idle_full":     [("timer", 100, False, "等"),
                             ("idle", None, True, "派"),
                             ("timer", 33, False, "等")],
    # 第三支空閒且耐久滿、已勾選 —— 影片裡這一支接著就被派出去了
    "fleets_selected_idle": [("timer", 34, False, "等"),
                             ("garrison", None, False, "等"),
                             ("idle", None, True, "派")],
    "fleets_all_timers":    [("timer", 18, False, "等"),
                             ("timer", 38, False, "等"),
                             ("timer", 17, False, "等")],
    "fleets_in_battle":     [("timer", None, False, "等"),
                             ("timer", None, False, "等"),
                             ("battle", None, False, "等")],
    # 維修後勾選被清掉，按出征跳「未選擇任何艦隊」
    "fleets_none_selected": [("timer", 51, False, "等"),
                             ("garrison", None, False, "等"),
                             ("timer", 40, False, "等")],
}

for name, rows in FLEETS.items():
    print(f"\n── {name} ──")
    s = siege.read(cv2.imread(os.path.join(FIX, name + ".jpg")))
    check("畫面種類", s.kind, "fleets")
    check("讀到三支艦隊", len(s.fleets), 3)
    check("找到出征鈕", s.send_at is not None, True)
    for f, (st, timer, sel, dec) in zip(s.fleets, rows):
        tag = f"#{f.index}"
        check(f"{tag} 狀態", f.status, st)
        if timer is not None:
            check(f"{tag} 倒數秒數", f.timer, timer)
        check(f"{tag} 已勾選", f.selected, sel)
        check(f"{tag} 決定（修/派/等），耐久 {f.bar:.2f}", decision(f), dec)

s = siege.read(cv2.imread(os.path.join(FIX, "fleets_none_selected.jpg")))
check("\n讀到「未選擇任何艦隊」提示", bool(s.toast), True)

print("\n── 城市彈窗 ──")
s = siege.read(cv2.imread(os.path.join(FIX, "city_popup.jpg")))
check("畫面種類", s.kind, "city")
check("標題是堡壘F2", siege.same_target(s.city, "防守堡壘F2"), True)
check("四顆鈕都找到", sorted(s.buttons), sorted(["集結", "徵募", "守軍", "前往"]))

print("\n── 地圖左側目標清單 ──")
s = siege.read(cv2.imread(os.path.join(FIX, "map_target_list.jpg")))
check("畫面種類", s.kind, "map")
for want in ("防守堡壘F2", "防守堡壘E1", "防守營地E0", "進攻營地F0"):
    hit = siege.find_target(s, want)
    check(f"找得到「{want}」", bool(hit), True)
check("不會把 F2 當成 E1", siege.find_target(s, "防守堡壘F2")[0] != "防守堡壘EI", True)

print("\n── 鏡頭已經在城市上時，點正中央而不是清單 ──")
s = siege.read(cv2.imread(os.path.join(FIX, "map_target_list.jpg")))
a = siege.plan(s, "防守堡壘F2", camera_on_city=True, center_tries=0)
w, h = s.size
check("點正中央", (a.kind, a.at), ("tap", (int(0.50 * w), int(0.51 * h))))
a = siege.plan(s, "防守堡壘F2", camera_on_city=True, center_tries=siege.CENTER_TRIES)
check("正中央試太多次就退回點清單", a.why.startswith("點左側目標"), True)
a = siege.plan(s, "防守堡壘F2", camera_on_city=False)
check("鏡頭不在城市上時點清單", a.why.startswith("點左側目標"), True)

print("\n── 代號正規化（OCR 會把 1 讀成 I、0 讀成 O）──")
check("EI = E1", siege.same_target("防守堡壘EI", "防守堡壘E1"), True)
check("FO = F0", siege.same_target("進攻營地FO", "進攻營地F0"), True)
check("堡量 = 堡壘（形近字）", siege.same_target("堡量F2", "防守堡壘F2"), True)
check("F2 ≠ E2", siege.same_target("防守堡壘F2", "防守堡壘E2"), False)
check("堡壘 ≠ 營地", siege.same_target("防守堡壘F2", "防守營地F2"), False)

print()
if fails:
    print(f"{len(fails)} 個失敗：")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("全部通過。")
