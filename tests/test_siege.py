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
        check(f"{tag} 決定（修/派/等）", decision(f), dec)

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
a = siege.plan(s, None, camera_on_city=False, centre_only=True)
check("點中央模式：不管鏡頭狀態都點正中央", a.at, (int(0.50 * w), int(0.51 * h)))
s = siege.read(cv2.imread(os.path.join(FIX, "city_popup.jpg")))
a = siege.plan(s, None, centre_only=True)
check("沒指定目標：彈窗直接按前往", a.why.endswith("按前往"), True)
a = siege.plan(s, "防守堡壘E1", centre_only=True)
check("指定目標但彈窗是別的城：不按前往", a.kind, "reset")


print("\n── 低解析度實機錄影（IMG_8939，444x960）出問題的畫面 ──")
# 這些都是第一版判錯的畫面，每一個都對應一個修正
LOWRES = [
    ("lowres_send_one", "tap", "出征",
     "第 3 支空閒＋勾選＋耐久 1.00，該出征"),
    ("lowres_status_flicker", None, None,
     "第 3 支狀態讀成「空開中」。舊版當成讀不到、把它取消勾選；不能取消"),
    ("lowres_three_damaged", "tap", "第 1 支受損，按維修",
     "三支都受損；第 3 支狀態讀成「空開中」但看得到維修鈕，也要算受損"),
    ("lowres_all_ready", "tap", "第 2 支完好空閒",
     "三支都修好，這一幀只有第 1 支勾著。舊版把第 1 支（讀成「空開中」）"
     "誤判成沒準備好、連取消 5 次；正確是接著勾第 2 支"),
    ("lowres_reward", "tap", "獎勵畫面，點空白處關掉",
     "「恭喜獲得 鑽石×60」是拿到的；舊版看到鑽石就停止"),
    ("lowres_title_truncated", None, None,
     "標題讀成「堡壘F」。舊版當成開錯城市；應該再看一次，不能 reset"),
]
for name, kind, why, note in LOWRES:
    img = cv2.imread(os.path.join(FIX, name + ".jpg"))
    from ocr import ocr as _ocr
    items = _ocr(img)
    h = img.shape[0]
    mid = [i for i in items if 0.12 * h < i[2] < 0.84 * h and "系統" not in i[0]]
    a = siege.plan(siege.read(img, items), "防守堡壘F2", mid)
    print(f"   ({note})")
    if name == "lowres_status_flicker":
        check(name + " 不可以取消勾選", "取消勾選" in a.why, False)
        check(name + " 也不可以停止", a.kind == "stop", False)
    elif name == "lowres_title_truncated":
        check(name + " 不可以判成開錯城市", a.kind == "reset", False)
    else:
        check(name, (a.kind, a.why.startswith(why)), (kind, True))
    if name == "lowres_all_ready":
        s3 = siege.read(img, items)
        check("   三支都判成可以出征", [f.ready for f in s3.fleets], [True, True, True])
    if name == "lowres_three_damaged":
        s3 = siege.read(img, items)
        check("   三支都判成需要維修", [f.needs_repair for f in s3.fleets],
              [True, True, True])

print("\n── 清單前綴漏讀（實測「防守堡壘F2」被讀成「堡壘F2」）──")
s = siege.SiegeScreen("map", targets={"堡壘F2": (10, 10), "防守堡壘E1": (10, 50)})
check("「堡壘F2」仍找得到防守堡壘F2", bool(siege.find_target(s, "防守堡壘F2")), True)
s = siege.SiegeScreen("map", targets={"進攻堡壘F2": (10, 10)})
check("前綴讀到而且不同（進攻 vs 防守），不能算", siege.find_target(s, "防守堡壘F2"), None)

print("\n── 「鑽石」本身不等於要花錢 ──")
check("獎勵上的鑽石不停", siege.plan(siege.SiegeScreen("unknown"), "防守堡壘F2",
                                    [("鑽石", 1, 1, 1.0)]).kind == "stop", False)
check("「花費 50 鑽石」要停", siege.plan(siege.SiegeScreen("unknown"), "防守堡壘F2",
                                    [("花費50鑽石", 1, 1, 1.0)]).kind, "stop")
check("「加速」要停", siege.plan(siege.SiegeScreen("unknown"), "防守堡壘F2",
                                [("加速", 1, 1, 1.0)]).kind, "stop")

print("\n── 讀不到「維修」兩個字時，靠顏色也要找到維修鈕 ──")
# 使用者回報：畫面上明明有維修鈕，程式卻說「空閒・耐久沒滿」不去修。
# 這裡故意把 OCR 讀到的「修」字全部丟掉，模擬那台電腦的情況。
from ocr import ocr as _real_ocr


def blind_ocr(img, *a, **k):
    return [i for i in _real_ocr(img, *a, **k) if "修" not in i[0]]


# (畫面, 每一列是否應該判成要維修)
BLIND = {
    "fleets_repair_needed":  [True, False, False],
    "lowres_three_damaged":  [True, True, True],
    "fleets_idle_full":      [False, False, False],   # 第 2 支空閒、耐久滿、有勾選外框
    "fleets_selected_idle":  [False, False, False],   # 第 3 支同上
    "lowres_all_ready":      [False, False, False],
    "lowres_send_one":       [False, False, False],
    "fleets_all_timers":     [False, False, False],   # 倒數列有藍色 >> 鈕，絕不能當成維修
}
for name, want in BLIND.items():
    img = cv2.imread(os.path.join(FIX, name + ".jpg"))
    sc = siege.read(img, ocr_fn=blind_ocr)
    got = [f.needs_repair for f in sc.fleets]
    how = [f.repair_by or "-" for f in sc.fleets]
    check(f"{name} 要維修 {how}", got, want)

print("\n── 比較寬的視窗（使用者的 Mac 是 0.58，錄影是 0.46）──")
# 使用者回報滿耐久被判成「耐久沒滿」：位置是用視窗比例算的，寬視窗下全偏掉。
# 這裡把畫面左右補邊撐到 0.58，判斷、勾選、點擊位置都要跟原本一樣。
def pillar(img, aspect=0.578):
    h, w = img.shape[:2]
    pad = (int(h * aspect) - w) // 2
    return cv2.copyMakeBorder(img, 0, 0, pad, pad, cv2.BORDER_CONSTANT,
                              value=(20, 20, 20)), pad


def summary(sc):
    return [("修" if f.needs_repair else "派" if f.ready else "等", f.selected)
            for f in sc.fleets]


for name in ("fleets_repair_needed", "fleets_idle_full", "fleets_selected_idle",
             "lowres_all_ready", "lowres_three_damaged", "fleets_all_timers"):
    img = cv2.imread(os.path.join(FIX, name + ".jpg"))
    base = siege.read(img)
    wide_img, pad = pillar(img)
    wide = siege.read(wide_img)
    blind_wide = siege.read(wide_img, ocr_fn=blind_ocr)
    check(f"{name} 寬視窗判斷一樣", summary(wide), summary(base))
    check(f"{name} 寬視窗＋讀不到維修字也一樣", summary(blind_wide), summary(base))
    drift = max(abs(b.tap_at[0] - pad - a.tap_at[0]) + abs(b.tap_at[1] - a.tap_at[1])
                for a, b in zip(base.fleets, wide.fleets))
    check(f"{name} 點擊位置偏差 <= 4px", drift <= 4, True)

print("\n── 點中央模式的實機畫面（IMG_8939）──")
# 城市爭奪戰面板也寫著「城戰進行中」，舊版當成地圖、一直點正中央。
for name in ("lowres_war_panel", "lowres_war_panel2"):
    img = cv2.imread(os.path.join(FIX, name + ".jpg"))
    sc = siege.read(img, want_list=False)
    a = siege.plan(sc, None, centre_only=True)
    h, w = img.shape[:2]
    check(f"{name} 認成面板", sc.kind, "panel")
    # 右上角紅色 ✕ 目視在 (0.88, 0.20)
    check(f"{name} 點的是右上角 ✕",
          a.kind == "tap" and abs(a.at[0] / w - 0.88) < 0.03
          and abs(a.at[1] / h - 0.20) < 0.03, True)
# 鏡頭停在城市上：點的位置要落在「堡壘F2」標籤上（OCR 量到 0.49, 0.51）
img = cv2.imread(os.path.join(FIX, "lowres_map_on_city.jpg"))
sc = siege.read(img, want_list=False)
a = siege.plan(sc, None, centre_only=True)
h, w = img.shape[:2]
check("鏡頭在城市上：認成地圖", sc.kind, "map")
check("點的位置離城市標籤 < 3% 畫面",
      abs(a.at[0] / w - 0.49) < 0.03 and abs(a.at[1] / h - 0.51) < 0.03, True)
s2 = siege.SiegeScreen("city", city="堡壘F2", buttons={"進攻": (100, 900)})
check("敵城只有「進攻」鈕也會按", siege.plan(s2, None, centre_only=True).at, (100, 900))

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
