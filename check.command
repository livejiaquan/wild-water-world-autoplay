#!/bin/bash
# 雙擊檢查環境與權限。
cd "$(dirname "$0")" || exit 1
if [ ! -x waterbot/.venv/bin/python ]; then
    echo "還沒安裝。請先雙擊 install.command。"
    echo; echo "按 Enter 關閉視窗。"; read -r; exit 1
fi
clear
./waterbot/.venv/bin/python waterbot/preflight.py
echo
echo "按 Enter 關閉視窗。"
read -r
