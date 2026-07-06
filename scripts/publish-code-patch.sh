#!/bin/sh
# Publish a hot-patch code update to GitHub 'code' release.
#
# Usage:
#   ./scripts/publish-code-patch.sh                    # changelog 默认 "代码更新"
#   ./scripts/publish-code-patch.sh "修复某某 bug"
#
# 前置要求: gh (GitHub CLI) 已登录、git 仓库干净
# 产物: GitHub release tag=code 的资产 app-code.zip (~几百 KB)
# 客户端行为: UpdateService._check_patch() 读到 codever 更大 → 提示更新 →
#             download_and_apply_patch() 下载解压到 app_override/ → 重启生效

set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

CHANGELOG="${1:-代码更新}"
CODEVER=$(git show -s --format=%ct HEAD)
TMPDIR_PATCH=$(mktemp -d)
ZIP_PATH="$TMPDIR_PATCH/app-code.zip"

echo "▶ 正在打包热更新补丁 (codever=$CODEVER)…"

# 写版本文件
echo "$CODEVER" > "$TMPDIR_PATCH/code_version.txt"

# 把 app/ 复制进临时目录，再用 Python 打 zip（排除 __pycache__ / .pyc）
cp -r app "$TMPDIR_PATCH/app"

python3 - "$ZIP_PATH" "$TMPDIR_PATCH" <<'PYEOF'
import sys, os, zipfile

zip_path = sys.argv[1]
base     = sys.argv[2]

with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    # code_version.txt 必须在 zip 根目录（bootstrap.read_code_version 要找它）
    zf.write(os.path.join(base, "code_version.txt"), "code_version.txt")
    for root, dirs, files in os.walk(os.path.join(base, "app")):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fname in files:
            if fname.endswith(".pyc"):
                continue
            abs_path = os.path.join(root, fname)
            # zip 内路径: app/xxx/yyy.py
            arc_path = os.path.relpath(abs_path, base)
            zf.write(abs_path, arc_path)

size_kb = os.path.getsize(zip_path) // 1024
print(f"   zip 大小: {size_kb} KB  ({zip_path})")
PYEOF

# Release body 格式必须与 UpdateService._check_patch() 的正则对应：
#   codever:<integer>
#   changelog:<text>
#   sha256:<hex64>   ← 客户端 download_and_apply_patch() 用它校验 zip 完整性
ZIP_SHA256=$(shasum -a 256 "$ZIP_PATH" | awk '{print $1}')
RELEASE_BODY="codever:${CODEVER}
changelog:${CHANGELOG}
sha256:${ZIP_SHA256}"

echo "▶ 正在上传到 GitHub release (tag=code)…"

# 删掉旧的 code release（资产会一起删），再重建
gh release delete code --yes 2>/dev/null || true
gh release create code \
  --repo "371066607/catch-radar" \
  --title "Code Patch" \
  --notes "$RELEASE_BODY" \
  --prerelease \
  "${ZIP_PATH}#app-code.zip"

rm -rf "$TMPDIR_PATCH"

echo ""
echo "✅ 热更新补丁已发布"
echo "   codever : $CODEVER"
echo "   changelog: $CHANGELOG"
echo "   客户端下次检查更新时将自动提示安装"
