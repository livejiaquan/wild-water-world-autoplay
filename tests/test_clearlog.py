"""通關紀錄的測試：時間格式、檔案內容、以及「關卡變大才算通過」的判定。

    ./waterbot/.venv/bin/python tests/test_clearlog.py
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "waterbot"))

from runlog import RunLog, human_time   # noqa: E402

fails = []


def check(name, got, want):
    ok = got == want
    print(f"[{'ok  ' if ok else 'FAIL'}] {name}: {got!r}")
    if not ok:
        fails.append(f"{name}: 得到 {got!r}，預期 {want!r}")


print("── 時間寫法要讓人看得懂 ──")
check("45 秒", human_time(45), "45秒")
check("90 秒", human_time(90), "1分30秒")
check("120 秒", human_time(120), "2分")
check("3661 秒", human_time(3661), "1小時1分")
check("7200 秒", human_time(7200), "2小時")

print("\n── 通關紀錄檔 ──")
tmp = tempfile.mkdtemp()
try:
    log = RunLog(tmp)
    log.clear(876, 252, 18)
    log.clear(877, 390, 27)
    path = os.path.join(tmp, "通關紀錄.txt")
    body = open(path, encoding="utf-8").read()
    print(body.rstrip())

    lines = [l for l in body.splitlines() if l.strip()]
    check("有表頭加兩筆紀錄", len(lines), 4)
    check("表頭還在最上面", lines[0].startswith("關卡"), True)
    check("最新的 877 排第一", lines[2].startswith("877"), True)
    check("877 這筆寫了耗時", "6分30秒" in lines[2], True)
    check("較舊的 876 排第二", lines[3].startswith("876"), True)
    check("876 這筆寫了耗時", "4分12秒" in lines[3], True)
    check("876 這筆寫了次數", "18 次" in lines[3], True)

    # 再開一次不該重複寫表頭
    log2 = RunLog(tmp)
    log2.clear(878, 61, 3)
    lines2 = [l for l in open(path, encoding="utf-8").read().splitlines()
              if l.strip()]
    check("續寫不重複表頭", len(lines2), 5)
    check("再開一次寫的 878 也在最上面", lines2[2].startswith("878"), True)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n── 舊版紀錄搬到主目錄，並改成最新在上 ──")
tmp = tempfile.mkdtemp()
try:
    out = os.path.join(tmp, "waterbot", "out")
    os.makedirs(out)
    old_path = os.path.join(out, "通關紀錄.txt")
    # 舊版的格式：表頭兩行，紀錄依時間往下加（舊的在上）
    with open(old_path, "w", encoding="utf-8") as f:
        f.write("關卡    通過時間            花了多久    試了幾次\n")
        f.write("─" * 24 + "\n")
        f.write("870     10/20 20:00:00      1分         3 次\n")
        f.write("871     10/20 20:05:00      2分         5 次\n")
        f.write("872     10/20 20:10:00      3分         7 次\n")

    new_path = os.path.join(tmp, "通關紀錄.txt")
    RunLog(out, clears_path=new_path)
    check("舊檔已經搬走", os.path.exists(old_path), False)
    check("主目錄出現新檔", os.path.exists(new_path), True)
    moved = [l for l in open(new_path, encoding="utf-8").read().splitlines()
             if l.strip()]
    check("三筆都還在", len(moved) - 2, 3)
    check("搬過來後最新的 872 在最上面", moved[2].startswith("872"), True)
    check("最舊的 870 在最下面", moved[-1].startswith("870"), True)

    # 已經搬過就不能再動：再開一次不可以把順序又倒回去
    RunLog(out, clears_path=new_path)
    again = [l for l in open(new_path, encoding="utf-8").read().splitlines()
             if l.strip()]
    check("重複啟動不會再倒一次", again == moved, True)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
if fails:
    print(f"{len(fails)} 個失敗：")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("全部通過。")
