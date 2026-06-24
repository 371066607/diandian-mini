#!/bin/sh
# 打包完整 macOS 安装包并发布到 GitHub release（同时更新热更新补丁）。
#
# Usage:
#   ./scripts/publish-full-release.sh                    # changelog 默认 "新版本发布"
#   ./scripts/publish-full-release.sh "首次发布，支持 xxx"
#
# 前置要求: gh (GitHub CLI) 已登录、pyinstaller 已安装
# 产物:
#   dist/CatchRadar.dmg          → GitHub release vYYYY.MM.DD  (首次安装用)
#   GitHub release tag=code        → 热更新补丁同步更新

set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

CHANGELOG="${1:-新版本发布}"
PYTHON="${PYTHON:-python3}"

# ── 1. 生成 code_version.txt（commit 时间戳）─────────────────────────────────
if git rev-parse HEAD >/dev/null 2>&1; then
  CODEVER=$(git show -s --format=%ct HEAD)
else
  CODEVER=$(date +%s)
fi
echo "$CODEVER" > code_version.txt
echo "▶ codever = $CODEVER"

# ── 2. PyInstaller 打包 ───────────────────────────────────────────────────────
echo "▶ 正在 PyInstaller 打包…"
"$PYTHON" -m PyInstaller --noconfirm --clean CatchRadar.spec
echo "   打包完成: dist/CatchRadar.app"

# ── 3. 打 DMG ─────────────────────────────────────────────────────────────────
DMG_PATH="dist/CatchRadar.dmg"
rm -f "$DMG_PATH"
echo "▶ 正在制作 DMG…"
hdiutil create \
  -volname "CatchRadar" \
  -srcfolder "dist/CatchRadar.app" \
  -ov -format UDZO \
  "$DMG_PATH"
DMG_MB=$(du -m "$DMG_PATH" | cut -f1)
echo "   DMG 大小: ${DMG_MB} MB  ($DMG_PATH)"

# ── 4. 发布带版本号的 GitHub release（完整包）────────────────────────────────
VERSION_TAG="v$(date -r "$CODEVER" '+%Y.%m.%d' 2>/dev/null || date '+%Y.%m.%d')"
echo "▶ 正在发布 GitHub release $VERSION_TAG…"

# 若同名 tag 已存在则先删除
gh release delete "$VERSION_TAG" --yes 2>/dev/null || true
gh release create "$VERSION_TAG" \
  --repo "371066607/catch-radar" \
  --title "CatchRadar $VERSION_TAG" \
  --notes "$(printf 'codever:%s\nchangelog:%s\n\n首次使用请下载 CatchRadar.dmg 安装。已安装用户会通过热更新自动升级，无需重新下载。' "$CODEVER" "$CHANGELOG")" \
  "${DMG_PATH}#CatchRadar.dmg"

echo "   ✅ 完整包 release: https://github.com/371066607/catch-radar/releases/tag/$VERSION_TAG"

# ── 5. 同步热更新补丁（code release）────────────────────────────────────────
echo "▶ 同步热更新补丁…"
sh "$(dirname "$0")/publish-code-patch.sh" "$CHANGELOG"

echo ""
echo "✅ 发布完成"
echo "   完整包 : https://github.com/371066607/catch-radar/releases/tag/$VERSION_TAG"
echo "   热更新 : https://github.com/371066607/catch-radar/releases/tag/code"
