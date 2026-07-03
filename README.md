# catch-radar

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

## 下载即用

到 [Releases](https://github.com/371066607/diandian-mini/releases) 下载对应平台整合包，解压双击即用（无需装 Python）：

- **macOS**：`macos` 标签下按芯片下载 `CatchRadar-AppleSilicon.dmg`（M1/M2/M3…）或 `CatchRadar-Intel.dmg` → 双击安装 `CatchRadar.app`
  - 首次打开若提示「无法验证开发者」，右键 App 选「打开」，或终端 `xattr -cr CatchRadar.app`
- **Windows**：`windows` 标签下的 `CatchRadar-windows.zip` → 解压双击 `CatchRadar.exe`

## 打包

本地打包成 macOS 应用（生成 `dist/CatchRadar.app`）：

```bash
sh scripts/build_macos.sh   # 自动生成 code_version.txt 并用 CatchRadar.spec 打包
```

## 版本与数据目录

- **版本号**用 commit 时间戳整数，构建时写入 `code_version.txt` 一起打进包；显示为 `年.月.日.时分`。
- **打包版的数据**（SQLite 库、日志）放在 app 之外的用户目录
  （macOS `~/Library/Application Support/CatchRadar`，Windows `%LOCALAPPDATA%\CatchRadar`），
  这样更新覆盖 app 也不会丢数据。开发态仍用项目 `data/`。

## 更新功能

- **开发态（有 `.git`）**：检查更新 = `git fetch` 比对，提示并可一键 `git pull` + 重启。
- **打包版**：查 `code` 标签 Release 的 `codever`，有新版则**热更新**——只下几百 KB 的
  `app-code.zip` 解压到用户目录 `app_override`（启动时优先加载）→ 自动重启，**登录态与数据都保留**，
  不用重下整包。
- 启动后静默检查 + 设置页「检查更新」按钮。

## 发布流程（GitHub Actions）

三个 workflow（`.github/workflows/`）：

| workflow | 触发 | 产物 |
|---|---|---|
| `publish-code-patch` | 手动（改了 Python 代码后跑这个） | `code` 标签：`app-code.zip` 热更新补丁 |
| `build-macos` | 手动 / 推 `v*` tag | `macos` 标签：完整 `.app` 整合包 |
| `build-windows` | 手动 / 推 `v*` tag | `windows` 标签：完整 `.exe` 整合包 |

日常只改 Python 代码 → 跑 `publish-code-patch`，用户端「检查更新」即可热更新；
依赖/打包配置变更时才重跑 `build-macos` / `build-windows` 出整包。整合包发布前会跑冒烟自检
（`--smoke-test`，确认打出来的二进制能正常启动）。
