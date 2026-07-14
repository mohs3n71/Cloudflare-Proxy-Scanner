#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"

APP_NAME="cloudflare-proxy-tester"
PYTHON_EXE="${PYTHON_EXE:-python3}"

if [ ! -x "bin/xray/xray" ]; then
    echo "Missing executable bin/xray/xray"
    echo "Put the Linux Xray binary there and run: chmod +x bin/xray/xray"
    exit 1
fi

if ! "$PYTHON_EXE" -m PyInstaller --version >/dev/null 2>&1; then
    echo "PyInstaller is not installed for $PYTHON_EXE."
    echo "Install it with: $PYTHON_EXE -m pip install pyinstaller"
    exit 1
fi

"$PYTHON_EXE" -m PyInstaller \
    --noconfirm \
    --clean \
    --onefile \
    --name "$APP_NAME" \
    --add-data "bin/xray:bin/xray" \
    proxy_tester/gui_entry.py

echo
echo "Built dist/$APP_NAME"
