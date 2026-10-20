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
echo "控制頁會自動在瀏覽器打開，可以在那裡暫停／繼續／看通關紀錄。"
echo "也可以在這個視窗按 空白鍵 暫停、按 q 結束。"
echo

# 等程式把伺服器起來，再把控制頁打開
( for i in $(seq 1 40); do
    if curl -s -o /dev/null "http://127.0.0.1:8777/" 2>/dev/null; then
        open "http://127.0.0.1:8777/"; break
    fi
    sleep 0.5
  done ) &

./waterbot/.venv/bin/python waterbot/bot.py "$@"

echo
echo "紀錄在 waterbot/out/run.log"
echo "按 Enter 關閉視窗。"
read -r
