# CatchRadar Agent Memory

这份文件给后续 agent 快速接手用。它补充 `AGENTS.md`、`CLAUDE.md` 和
`FRONTEND_AGENT_API.md`，记录当前迁移状态、运行方式、远端约定和最近验证证据。

## 当前项目定位

- 本仓库是 CatchRadar 桌面端，根路径：`/Volumes/DevSpace/myData——destop`。
- 桌面入口仍是 `main.py`，默认 UI 是 QML/PySide6。
- 当前方向是 API mode：桌面端通过 StoreIntel 后端读 MySQL 缓存和提交刷新任务，不再由前端同步阻塞抓取。
- 本地旧 SQLite/本地抓取模式只作为诊断 fallback，不是默认产品路径。

## 相关仓库与文档

- 前端接口手册：`FRONTEND_AGENT_API.md`。
- 后端项目路径：`/Volumes/DevSpace/services/modular-go-backend`。
- 后端同样维护了一份接口手册：`/Volumes/DevSpace/services/modular-go-backend/FRONTEND_AGENT_API.md`。
- 本项目原有开发规则在 `AGENTS.md` / `CLAUDE.md`，运行技能在 `.agents/skills/run-app/SKILL.md`。

## 运行方式

默认远端 API：

```bash
cd "/Volumes/DevSpace/myData——destop"
CATCH_RADAR_STOREINTEL_API_URL="https://catchradar.meshub.ai" .venv/bin/python3.12 main.py
```

本地后端 API：

```bash
cd "/Volumes/DevSpace/myData——destop"
CATCH_RADAR_STOREINTEL_API_URL="http://127.0.0.1:8081" .venv/bin/python3.12 main.py
```

无界面冒烟：

```bash
cd "/Volumes/DevSpace/myData——destop"
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software \
  CATCH_RADAR_STOREINTEL_API_URL="https://catchradar.meshub.ai" \
  .venv/bin/python3.12 main.py --smoke-test
```

注意：这个项目路径包含中文破折号 `——`，命令里的路径要加引号。

## 数据与同步原则

- MySQL 是权威数据源。
- Redis 只作为后端任务队列/传输层，不是最终数据源。
- 前端常规页面必须先读 DB/cache 接口。
- 如果缓存没有数据，前端提交 refresh job，等待 job 终态后再读同一个 DB/cache 接口。
- 搜索、详情、榜单、关键词排名、覆盖词、评论页面不应同步阻塞抓取。
- “同步全部 / 同步选中 / 同步到期”应提交 refresh job，由服务器 worker 执行。
- 部署时只跑后端 scheduler/worker；桌面端保持 RemoteSchedulerProxy，不在本机执行远端抓取计划。

## 远端约定

- 生产 API base：`https://catchradar.meshub.ai`。
- 远端主机：`18.144.206.114`。
- 远端运行用户约定：`www`。
- 不要把 SSH 密钥、密码、API key 或数据库密码写进仓库文档。
- 远端排障优先看 HTTP health、真实接口响应、服务日志和 MySQL/Redis 状态。

## 关键接口规则

- 读缓存接口和 refresh job 接口以 `FRONTEND_AGENT_API.md` 为准。
- 常规读取：`GET /api/store-intel/.../cache` 或 history/recent/list 类 DB 接口。
- 缓存 miss：`POST /api/store-intel/refresh-jobs`，再轮询
  `GET /api/store-intel/refresh-jobs/{job_id}`。
- job 终态：`completed` / `failed`。
- 已支持 job kind：`all`、`sync_all`、`due`、`sync_due`、`search`、`app`、`keyword`、`chart`、`coverage`、`reviews`。

## 最近已知实现状态

- 前端 API mode 默认启用，远端 API 由 `CATCH_RADAR_STOREINTEL_API_URL` 控制。
- DB-only/cache-first 查询链路已覆盖搜索、详情、评论、榜单、关键词、覆盖词、监控、历史、告警、设置等主要页面。
- 当 DB 为空时，前端应自动提交对应 refresh job，完成后再读取缓存数据。
- 同步类动作已改为请求刷新任务，不应直接做 blocking 抓取。
- 后端已补 MySQL-backed refresh job 表/查询、Redis 队列和 worker 恢复未完成 job 的逻辑。
- 桌面端右侧已加入接口日志面板：实时显示请求日志，点击可看传入 query/body、返回 data 和错误信息。
- 本仓库原有的 `go/storeintel/`（过渡期孵化的 Go 服务端模块）已删除：它已被后端
  `internal/project/catchradar/`（`/Volumes/DevSpace/services/modular-go-backend`）取代，
  自 2026-06-24 起未再更新、已分叉，前端代码本身也不 import 它。真实后端才是 source of truth。

## 最近验证证据

本地验证报告：

```text
verification/catchradar-20260621-023513/REPORT.md
```

最近一次本地验证通过：

```bash
python3 -m py_compile app/services/store_intel_api_client.py app/ui/qml_bridge.py tests/test_store_intel_api_client.py
.venv/bin/python3.12 -m pytest tests/test_store_intel_api_client.py tests/test_qml_bridge_api_adapter.py tests/test_tracking_service.py -q
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software CATCH_RADAR_STOREINTEL_API_URL="https://catchradar.meshub.ai" .venv/bin/python3.12 main.py --smoke-test
```

当时 pytest 结果：`45 passed`。

## 当前注意事项

- App Store 模式还不是当前验证主线；当前主要验证 Google Play。
- Cloudflare/上游可能拦默认 Python urllib UA；桌面 API 请求和 curl 形态曾验证可通。
- 如果桌面端显示占位符但右侧接口日志显示请求成功，要先检查 QML 数据映射字段，而不是先怀疑后端。
- 如果右侧接口日志没有出现请求，先从页面 entry、按钮 handler、QML bridge、API client 这条链路查。
- 不要改动无关重命名、打包、发布和 GitHub workflow 文件，除非用户明确要求。
- 不要主动 push 或发布；先完成本地验证并让用户确认。
