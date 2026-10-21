#!/bin/bash
# 雙擊開始刷關。
cd "$(dirname "$0")" || exit 1
BOLD=$'\033[1m'; OFF=$'\033[0m'

if [ ! -x waterbot/.venv/bin/python ]; then
    echo "還沒安裝。請先雙擊 install.command。"
    echo; echo "按 Enter 關閉視窗。"; read -r; exit 1
fi

clear
echo "${BOLD}瘋狂水世界 自動刷關${OFF}"
echo "按 空白鍵 暫停／繼續，按 q 結束。"
echo

./waterbot/.venv/bin/python waterbot/bot.py "$@"

echo
echo "紀錄在 waterbot/out/run.log"
echo "按 Enter 關閉視窗。"
read -r
