#!/bin/bash
# 雙擊開始城戰自動派兵（台灣時間 19:00–20:00）。
cd "$(dirname "$0")" || exit 1
BOLD=$'\033[1m'; OFF=$'\033[0m'

if [ ! -x waterbot/.venv/bin/python ]; then
    echo "還沒安裝。請先雙擊 install.command。"
    echo; echo "按 Enter 關閉視窗。"; read -r; exit 1
fi

clear
echo "${BOLD}瘋狂水世界 城戰自動派兵${OFF}"
echo
echo "開始前，先在遊戲裡把鏡頭移到要打的城市上："
echo "  1. 點左邊清單上的目標，跳出城市小視窗"
echo "  2. 按「前往」，畫面會移到那座城市"
echo "  3. 確認城市停在畫面正中央（看到「選擇艦隊」的話直接關掉也可以）"
echo
echo "之後程式會一直點畫面正中央的城市 → 前往 → 派兵。"
echo "只派耐久滿的艦隊；受損的會按維修等它修好，不加速、不花鑽石。"
echo "按 空白鍵 暫停／繼續，按 q 結束。20:00 自動收工。"
echo
read -r -p "鏡頭移好了就按 Enter 開始："
echo
./waterbot/.venv/bin/python waterbot/siege_bot.py

echo
echo "按 Enter 關閉視窗。"
read -r
