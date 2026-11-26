#!/bin/bash
# 雙擊開始城戰自動派兵（台灣時間 19:00–20:00）。
cd "$(dirname "$0")" || exit 1
BOLD=$'\033[1m'; OFF=$'\033[0m'

if [ ! -x waterbot/.venv/bin/python ]; then
    echo "還沒安裝。請先雙擊 install.command。"
    echo; echo "按 Enter 關閉視窗。"; read -r; exit 1
fi

LAST_FILE="waterbot/out/citywar_target.txt"
LAST=""
[ -f "$LAST_FILE" ] && LAST="$(cat "$LAST_FILE")"

clear
echo "${BOLD}瘋狂水世界 城戰自動派兵${OFF}"
echo
echo "請先打開遊戲，停在城戰地圖（左邊看得到目標清單的那個畫面）。"
echo "目標名稱照左邊清單上的寫，例如：防守堡壘F2"
echo
if [ -n "$LAST" ]; then
    read -r -p "要派兵到哪裡？（直接按 Enter = 上次的「$LAST」）：" T
    T="${T:-$LAST}"
else
    read -r -p "要派兵到哪裡？：" T
fi
if [ -z "$T" ]; then
    echo "沒有輸入目標。"; echo; echo "按 Enter 關閉視窗。"; read -r; exit 1
fi
mkdir -p waterbot/out && printf '%s' "$T" > "$LAST_FILE"

echo
echo "只派耐久滿的艦隊；受損的會按維修等它修好，不加速、不花鑽石。"
echo "按 空白鍵 暫停／繼續，按 q 結束。20:00 自動收工。"
echo
./waterbot/.venv/bin/python waterbot/siege_bot.py --target "$T"

echo
echo "按 Enter 關閉視窗。"
read -r
