"""掃描一批遊戲影片，找出狀態機還不認得的畫面。

目的不是驗證準確率（那是 replay_test.py 的事），而是「找新東西」：
把每一幀的 OCR 結果收集起來，列出哪些文字反覆出現但程式沒在處理，
特別是戰鬥結算類的字（勝利 / 通關 / 下一關 / 領取 / 確定 ...）。

用法: scan_videos.py <影片資料夾> [取樣間隔秒]
"""
import sys, os, glob, collections, json, re
import cv2
from ocr import ocr
from detect import classify

# 這些字一出現就值得人看一眼：多半是結算畫面或需要點掉的彈窗
INTERESTING = [
    "勝利", "胜利", "成功", "通關", "通关", "下一關", "下一关", "繼續", "继续",
    "獲得", "获得", "領取", "领取", "確定", "确定", "確認", "确认", "關閉", "关闭",
    "挑戰", "挑战", "失敗", "失败", "再戰", "再战", "開戰", "开战", "跳過", "跳过",
    "恭喜", "獎勵", "奖励", "升級", "升级", "解鎖", "解锁", "取消", "返回",
]

folder = sys.argv[1]
step = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0

seen = collections.Counter()          # 有趣的字 -> 出現次數
examples = {}                         # 有趣的字 -> (影片, 時間, 當時判成什麼)
state_count = collections.Counter()

vids = sorted(glob.glob(os.path.join(folder, "*.mp4")) +
              glob.glob(os.path.join(folder, "*.mkv")) +
              glob.glob(os.path.join(folder, "*.webm")))
print(f"要掃 {len(vids)} 支影片，每 {step}s 取一幀\n")

for v in vids:
    cap = cv2.VideoCapture(v)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    dur = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / fps
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"--- {os.path.basename(v)}  {w}x{h}  {dur/60:.1f}分 ---")
    t, hits = 0.0, 0
    while t < dur:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            break
        items = ocr(frame)
        s = classify(items, w, h)
        state_count[s.state] += 1
        for text, cx, cy, conf in items:
            for kw in INTERESTING:
                if kw in text:
                    seen[kw] += 1
                    hits += 1
                    key = (kw, s.state)
                    if key not in examples:
                        examples[key] = (os.path.basename(v), round(t, 1),
                                         text.strip(), cx, cy)
        t += step
    cap.release()
    print(f"    命中關鍵字 {hits} 次")

print("\n=== 關鍵字出現次數 ===")
for kw, n in seen.most_common():
    print(f"  {kw:<6} {n}")

print("\n=== 每個關鍵字第一次出現時，程式判成什麼狀態 ===")
for (kw, state), (v, t, text, cx, cy) in sorted(examples.items()):
    flag = "  <-- 沒在處理" if state in ("UNKNOWN", "BATTLE", "LOADING") else ""
    print(f"  {kw:<6} state={state:<13} {v} @{t}s  「{text}」({cx},{cy}){flag}")

print("\n=== 狀態分佈 ===")
for st, n in state_count.most_common():
    print(f"  {st:<13} {n}")

json.dump({f"{k[0]}|{k[1]}": v for k, v in examples.items()},
          open("out/scan_examples.json", "w"), ensure_ascii=False, indent=1)
print("\n細節寫到 out/scan_examples.json")
