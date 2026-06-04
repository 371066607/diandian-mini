# 点点数据 Mini

基于 PySide6 + SQLite 的本地桌面客户端，用于抓取和查看 Google Play 应用情报。

## 运行环境

- Python 3.12
- macOS / Windows / Linux 桌面环境

## 安装

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 启动

```bash
python main.py
```

## 测试 / 代码检查

```bash
pytest          # 全部测试
ruff check .    # 静态检查
```

## 打包

本地打包成 macOS 应用（生成 `dist/DiandianMini.app`）：

```bash
sh scripts/build_macos.sh
```

或手动：

```bash
pyinstaller --noconfirm --windowed --name DiandianMini main.py
```

## 更新功能

应用内置「检查更新」：

- **启动时**会静默查询本仓库的 GitHub Releases，若有新版本则在右下角轻提示。
- **设置页**有「检查更新」按钮，可手动检查并获取下载链接。

版本号在 `app/constants.py:APP_VERSION`，更新检查的目标仓库在 `GITHUB_REPO`。

## 发布新版本

打 tag 即可由 GitHub Actions 自动构建 macOS / Windows 安装包并发布到 Releases：

```bash
# 1. 改 app/constants.py 里的 APP_VERSION，例如 1.1.0
# 2. 提交后打 tag 并推送
git tag v1.1.0
git push origin v1.1.0
```

`.github/workflows/release.yml` 会在 `v*` tag 推送时构建并把安装包附到对应 Release；
用户端的「检查更新」随即就能检测到新版本。
