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
    check("876 這筆寫了耗時", "4分12秒" in lines[2], True)
    check("876 這筆寫了次數", "18 次" in lines[2], True)
    check("877 這筆寫了耗時", "6分30秒" in lines[3], True)

    # 再開一次不該重複寫表頭
    log2 = RunLog(tmp)
    log2.clear(878, 61, 3)
    lines2 = [l for l in open(path, encoding="utf-8").read().splitlines()
              if l.strip()]
    check("續寫不重複表頭", len(lines2), 5)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
if fails:
    print(f"{len(fails)} 個失敗：")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("全部通過。")
