#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"

PYTHON_EXE="${PYTHON_EXE:-python3}"
exec "$PYTHON_EXE" -m proxy_tester.launcher
