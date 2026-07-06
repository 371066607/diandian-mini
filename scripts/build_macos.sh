#!/bin/sh
# Build a standalone macOS app bundle with PyInstaller -> dist/CatchRadar.app
set -eu

cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

PYTHON="${PYTHON:-python3}"

# Stamp the current code version (commit timestamp) so the app knows its own version.
if git rev-parse HEAD >/dev/null 2>&1; then
  git show -s --format=%ct HEAD > code_version.txt
else
  date +%s > code_version.txt
fi

"$PYTHON" -m pip install --quiet --upgrade pyinstaller
"$PYTHON" -m pip install --quiet -r requirements.txt

"$PYTHON" -m PyInstaller --noconfirm --clean CatchRadar.spec

echo ""
echo "✅ 打包完成: dist/CatchRadar.app"
echo "   运行: open dist/CatchRadar.app"
