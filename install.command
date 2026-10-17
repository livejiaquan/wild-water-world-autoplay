#!/bin/bash
# 雙擊這個檔案就會自動安裝。預設這台 Mac 什麼開發工具都沒裝過。
cd "$(dirname "$0")" || exit 1

BOLD=$'\033[1m'; RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; OFF=$'\033[0m'

say()  { printf "%s\n" "$*"; }
head2() { printf "\n${BOLD}%s${OFF}\n" "$*"; }
ok()   { printf "${GRN}✅ %s${OFF}\n" "$*"; }
warn() { printf "${YEL}⚠️  %s${OFF}\n" "$*"; }
die()  { printf "${RED}❌ %s${OFF}\n" "$*"; printf "\n按 Enter 關閉視窗。\n"; read -r; exit 1; }

clear
say "${BOLD}瘋狂水世界 自動刷關 — 安裝${OFF}"
say "這會花幾分鐘，中途不用管它。"

# ---------------------------------------------------------------
head2 "1/4 檢查 Python"

PY=""
# 先找找看有沒有堪用的 Python（3.9 以上，而且 venv 能動）
for cand in python3.13 python3.12 python3.11 python3.10 python3; do
    p="$(command -v "$cand" 2>/dev/null)" || continue
    # macOS 的 /usr/bin/python3 是個殼，沒裝 Xcode 工具時會跳視窗，先排除
    "$p" -c 'import sys,venv; sys.exit(0 if sys.version_info>=(3,9) else 1)' \
        >/dev/null 2>&1 || continue
    PY="$p"; break
done

if [ -n "$PY" ]; then
    ok "找到可用的 Python：$("$PY" --version 2>&1)"
else
    warn "這台電腦沒有可用的 Python，幫你裝一份獨立的（不會影響系統）"
    # uv 會自己下載一份乾淨的 Python，不需要 Xcode 工具、不需要管理員密碼
    if ! command -v uv >/dev/null 2>&1; then
        say "   正在下載安裝工具 uv ..."
        curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1 \
            || die "下載失敗。請確認網路連線後再試一次。"
    fi
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    command -v uv >/dev/null 2>&1 || die "uv 安裝失敗，請把這個畫面截圖回報。"
    say "   正在準備 Python ..."
    uv python install 3.12 >/dev/null 2>&1 || die "Python 安裝失敗。"
    PY="$(uv python find 3.12 2>/dev/null)"
    [ -n "$PY" ] || die "找不到剛裝好的 Python。"
    ok "已裝好獨立的 Python：$("$PY" --version 2>&1)"
fi

# ---------------------------------------------------------------
head2 "2/4 建立執行環境"
rm -rf waterbot/.venv
"$PY" -m venv waterbot/.venv >/dev/null 2>&1 || die "建立環境失敗。"
ok "建好了"

# ---------------------------------------------------------------
head2 "3/4 下載必要套件（這步最久，請耐心等）"
./waterbot/.venv/bin/python -m pip install -q --upgrade pip >/dev/null 2>&1
if ! ./waterbot/.venv/bin/python -m pip install -q \
        opencv-python-headless numpy \
        pyobjc-framework-Vision pyobjc-framework-Quartz \
        pyobjc-framework-ApplicationServices 2>/tmp/waterbot_pip_err.txt; then
    say ""
    say "安裝套件時出錯，錯誤訊息："
    tail -20 /tmp/waterbot_pip_err.txt
    die "請把上面的訊息截圖回報。"
fi
ok "套件裝好了"

# ---------------------------------------------------------------
head2 "4/4 檢查權限"
chmod +x start.command check.command 2>/dev/null
./waterbot/.venv/bin/python waterbot/preflight.py
RC=$?

say ""
say "${BOLD}────────────────────────────────────────${OFF}"
if [ $RC -eq 0 ]; then
    ok "安裝完成，可以用了"
    say ""
    say "接下來：把遊戲打開，然後雙擊 ${BOLD}start.command${OFF} 開始刷關。"
else
    warn "程式本身裝好了，但還缺權限（看上面的說明）"
    say ""
    say "給完權限後，請${BOLD}把這個終端機視窗整個關掉${OFF}，"
    say "再雙擊 ${BOLD}check.command${OFF} 確認一次。"
fi
say ""
say "按 Enter 關閉視窗。"
read -r
