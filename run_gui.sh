#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"

PYTHON_EXE="${PYTHON_EXE:-python3}"
"$PYTHON_EXE" tools/xray_release.py --if-missing
exec "$PYTHON_EXE" -m proxy_tester.gui
