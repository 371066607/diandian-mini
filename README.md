# catch-radar

基于 PySide6/QML 的桌面客户端，用于查看和追踪应用商店情报。默认且固定通过远端
Go 后端（`https://catchradar.meshub.ai`）的 API 读写数据。

## 如何运行

运行环境：Python 3.12，macOS / Windows / Linux 桌面系统。

macOS / Linux：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

Windows PowerShell：

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

源码直跑和打包版本都默认连接远端 API：
`https://catchradar.meshub.ai`。需要调试本地 Go 后端时，必须显式允许 localhost 并指定地址：

```bash
CATCH_RADAR_ALLOW_LOCAL_API=true \
CATCH_RADAR_STOREINTEL_API_URL=http://127.0.0.1:18082 \
python main.py
```

## 如何测试

```bash
# 最快的启动自检：初始化数据库、迁移和服务后退出，成功时输出 smoke-ok
python main.py --smoke-test

# 默认产品路径：跳过已冻结的 legacy / offline 测试
python -m pytest -m "not legacy"

# 全量测试
python -m pytest

# 静态检查
python -m ruff check .
```

只跑单个文件或测试用例：

```bash
python -m pytest tests/test_store_intel_api_client.py
python -m pytest tests/test_store_intel_api_client.py::test_store_intel_api_client_guest_retries_once_on_401
```

## Codex 怎么用：我是如何做这个项目的

CatchRadar 几乎全程都是我和 Codex 一起完成的。我没有让 Codex 只生成一段代码再手动复制，
而是直接在 Codex 中打开整个项目，用自然语言告诉它我想做什么。Codex 会自己读取现有代码、
找到需要改的文件、直接实现功能，然后在终端里启动项目、运行测试和修复报错。

项目开始时，我先对 Codex 描述了产品目标：做一个能够搜索应用、查看详情和评论、分析榜单与关键词、
追踪应用并发出告警的桌面工具。Codex 先搭出可运行的 PySide6/QML 客户端，之后再根据我每次提出的需求
继续完善页面、数据、监控、更新和打包。后来项目需要更稳定的远端数据服务，我又让 Codex 协助把主要数据逻辑
迁移到 Go 后端，将桌面端收口成通过 API 工作的轻客户端。

我在这个过程中主要负责：

- 决定产品要做什么，以及功能优先级。
- 用自然语言描述新功能、问题和期望结果。
- 查看 Codex 做出的界面和运行结果，然后继续提出调整。
- 做最终的产品取舍和验收。

Codex 则负责把这些需求落到真实仓库中：读代码、改代码、追请求链路、跑测试、查日志、修复问题，
并在每轮完成后告诉我改了什么、哪些测试已经通过、还有什么风险。

我给 Codex 的指令通常很直接，例如：

```text
做一个应用详情页，展示安装量、评分、评论和历史趋势。
把关键词监控改成使用后端真实数据，不要用本地假数据。
看一下这个页面为什么没有数据，从界面一直查到 API 和数据源。
把修复做完，运行测试，确认没问题再停。
```

## GPT-5.6 怎么用：它在这个项目里做了什么

我在 Codex 中使用 **GPT-5.6** 作为主要开发模型。Codex 是它读写仓库和运行终端的工作环境，
GPT-5.6 则负责理解我的需求、理解整个项目的上下文，并决定如何实现。

在 CatchRadar 里，GPT-5.6 主要用来：

- 把产品想法转成可运行的页面和功能。
- 同时理解 Python/QML 桌面端和 Go 后端，处理两边的接口对接。
- 从页面、Controller、API 一直追到后端和数据源，定位真实问题。
- 根据错误日志和测试结果继续修改，而不是只给一个建议就结束。
- 检查已完成的代码，帮我发现回归问题和未覆盖的边界。

GPT-5.6 并没有被接入 CatchRadar 作为产品功能，运行这个应用也不需要 OpenAI API Key。
它的作用是帮我把产品想法更快地变成一个可以真正运行、测试和发布的软件项目。

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
