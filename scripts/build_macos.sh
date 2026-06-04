#!/bin/sh
# Build a standalone macOS app bundle with PyInstaller -> dist/DiandianMini.app
set -eu

cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

PYTHON="${PYTHON:-python3}"

"$PYTHON" -m pip install --quiet --upgrade pyinstaller
"$PYTHON" -m pip install --quiet -r requirements.txt

"$PYTHON" -m PyInstaller --noconfirm --clean --windowed \
  --name DiandianMini \
  --osx-bundle-identifier com.diandian.mini \
  main.py

echo ""
echo "✅ 打包完成: dist/DiandianMini.app"
echo "   运行: open dist/DiandianMini.app"
