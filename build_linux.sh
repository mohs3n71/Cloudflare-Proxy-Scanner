#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"

PYTHON_EXE="${PYTHON_EXE:-python3}"
XRAY_VERSION="${XRAY_VERSION:-latest}"

if [ "$#" -gt 0 ]; then
    exec "$PYTHON_EXE" tools/build_release.py --os linux --arch "$1" --xray-version "$XRAY_VERSION"
fi

exec "$PYTHON_EXE" tools/build_release.py --os linux --xray-version "$XRAY_VERSION"
