#!/bin/bash
# 雙擊這個檔案就會更新到最新版。不需要 git。
# 只換程式碼，不會動到已經裝好的環境，也不會刪掉你的通關紀錄。
cd "$(dirname "$0")" || exit 1

REPO="livejiaquan/wild-water-world-autoplay"
URL="https://github.com/$REPO/archive/refs/heads/main.tar.gz"

BOLD=$'\033[1m'; RED=$'\033[31m'; GRN=$'\033[32m'; OFF=$'\033[0m'
ok()  { printf "${GRN}✅ %s${OFF}\n" "$*"; }
die() { printf "${RED}❌ %s${OFF}\n" "$*"; printf "\n按 Enter 關閉視窗。\n"; read -r; exit 1; }

clear
printf "${BOLD}瘋狂水世界 自動刷關 — 更新${OFF}\n\n"

TMP="$(mktemp -d)" || die "無法建立暫存資料夾。"
trap 'rm -rf "$TMP"' EXIT

echo "正在下載最新版..."
curl -fsSL "$URL" | tar xz -C "$TMP" || die "下載失敗，請確認網路連線。"

SRC="$TMP/$(ls "$TMP" | head -1)"
[ -d "$SRC/waterbot" ] || die "下載的內容不對，請回報。"

echo "正在更新程式..."
# 只覆蓋程式碼。waterbot/.venv（已裝好的環境）和 waterbot/out（你的紀錄）
# 都不在複製範圍內，所以不會被動到。
cp "$SRC"/*.command "$SRC"/*.md "$SRC"/LICENSE . 2>/dev/null
cp "$SRC"/waterbot/*.py waterbot/ 2>/dev/null
mkdir -p tests
cp -R "$SRC"/tests/. tests/ 2>/dev/null
chmod +x ./*.command 2>/dev/null

ok "更新完成"
echo
if [ -x waterbot/.venv/bin/python ]; then
    echo "環境還在，直接雙擊 ${BOLD}start.command${OFF} 就可以用。"
    if [ -f waterbot/out/通關紀錄.txt ]; then
        echo "你的通關紀錄也還在。"
    fi
else
    echo "還沒安裝過環境，請先雙擊 ${BOLD}install.command${OFF}。"
fi
echo
echo "按 Enter 關閉視窗。"
read -r
