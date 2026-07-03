> ⚠️ **历史文档，已过时**：本文档描述的是 v1.0 纯本地单机架构（"不做后端 API"、"不做 Web
> 服务"等约束）。项目自 2026-06 起已迁移为 API-first 架构——桌面端默认通过 Go 后端
> （`/Volumes/DevSpace/services/modular-go-backend` 的 `internal/project/catchradar/`）读写数据，
> 本文档描述的纯本地/无后端模式现在只是 legacy/offline 诊断 fallback，且已冻结。
> 当前架构现状见仓库根目录的 `AGENTS.md` / `CLAUDE.md` / `AGENT_MEMORY.md`，
> 接口契约见 `FRONTEND_AGENT_API.md`。本文档仅作历史参考，不要据此做架构判断。

# catch-radar 桌面客户端开发规格书

版本：v1.0  
目标开发方式：交给 Claude / Codex 以目标模式开发  
技术定位：Python 单机桌面客户端，一套代码，不做后端 API，不做 Web 服务  
默认平台：Google Play  
默认语言：中文 UI  

---

## 1. 项目目标

开发一个 Python 桌面应用，作为「catch-radar」的单机版竞品分析工具。

第一版只做 Google Play，不做 App Store，不做真实收入，不做云端同步。

应用需要支持：

1. 按关键词搜索 Google Play 应用。
2. 按包名获取应用详情。
3. 获取相似应用 / 竞品。
4. 获取应用评论。
5. 获取 Google Play 榜单。
6. 查询某个 App 在关键词下的排名。
7. 本地监控指定 App。
8. 使用 SQLite 存储应用快照和历史趋势。
9. 展示评分、评论数、安装量区间等历史趋势图。
10. 计算「商业化强度评分」。
11. 提供一个清晰可用的桌面 UI。

不要宣称可以获得真实下载量、真实订阅收入、真实 IAP 收入。  
所有收入相关功能只能叫「商业化强度」或「粗略估算」，并提示基于公开数据推断。

---

## 2. 技术栈

使用：

```txt
Python 3.11+
PySide6
SQLite
SQLAlchemy 2.x
APScheduler
google-play-scraper
pydantic
python-dateutil
matplotlib
pytest
ruff
pyinstaller
```

不要使用：

```txt
FastAPI
Flask
Celery
Redis
PostgreSQL
ClickHouse
Electron
Tauri
React
Vue
```

这是一个单机桌面应用，不需要服务端。

---

## 3. 项目结构

```txt
catch_radar_desktop/
├── main.py
├── requirements.txt
├── README.md
├── pyproject.toml
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── constants.py
│   ├── logging_config.py
│   │
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── main_window.py
│   │   ├── widgets/
│   │   │   ├── app_table.py
│   │   │   ├── review_table.py
│   │   │   ├── chart_widget.py
│   │   │   ├── loading_overlay.py
│   │   │   └── message_box.py
│   │   └── pages/
│   │       ├── dashboard_page.py
│   │       ├── app_search_page.py
│   │       ├── app_detail_page.py
│   │       ├── reviews_page.py
│   │       ├── charts_page.py
│   │       ├── keywords_page.py
│   │       ├── tracking_page.py
│   │       └── settings_page.py
│   │
│   ├── services/
│   │   ├── google_play_service.py
│   │   ├── keyword_service.py
│   │   ├── chart_service.py
│   │   ├── review_service.py
│   │   ├── tracking_service.py
│   │   ├── monetization_service.py
│   │   ├── alert_service.py
│   │   └── settings_service.py
│   │
│   ├── db/
│   │   ├── database.py
│   │   ├── models.py
│   │   ├── repositories.py
│   │   └── migrations.py
│   │
│   ├── schemas/
│   │   ├── app_schema.py
│   │   ├── review_schema.py
│   │   ├── chart_schema.py
│   │   ├── keyword_schema.py
│   │   └── tracking_schema.py
│   │
│   ├── jobs/
│   │   ├── scheduler.py
│   │   └── sync_jobs.py
│   │
│   └── utils/
│       ├── normalize.py
│       ├── time_utils.py
│       ├── install_parser.py
│       ├── image_loader.py
│       └── worker.py
│
├── tests/
│   ├── test_install_parser.py
│   ├── test_keyword_rank.py
│   ├── test_monetization_score.py
│   └── test_repositories.py
│
└── data/
    └── .gitkeep
```

---

## 4. 核心页面

客户端必须包含 8 个页面：

| 页面 | 中文名称 | 作用 |
|---|---|---|
| Dashboard | 首页 | 总览监控数量、快照数量、提醒、最近变化 |
| App Search | 应用搜索 | 按关键词搜索应用 |
| App Detail | 应用详情 | 按包名查看详情、趋势、相似应用 |
| Reviews | 评论 | 抓取评论、筛选星级、查看差评 |
| Charts | 榜单 | 查看 Top Free / Top Paid / Top Grossing |
| Keywords | 关键词 | 查询关键词排名、保存历史 |
| Tracking | 监控 | 管理监控应用、手动同步 |
| Settings | 设置 | 配置国家、语言、定时任务、数据库路径 |

---

## 5. 数据库设计

默认 SQLite 路径：

```txt
./data/catch_radar.sqlite3
```

### 5.1 apps 表

```sql
CREATE TABLE apps (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  platform TEXT NOT NULL DEFAULT 'google_play',
  app_id TEXT NOT NULL,
  title TEXT,
  developer TEXT,
  developer_id TEXT,
  category TEXT,
  genre TEXT,
  icon_url TEXT,
  store_url TEXT,
  country TEXT DEFAULT 'us',
  lang TEXT DEFAULT 'en',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(platform, app_id, country, lang)
);
```

### 5.2 app_snapshots 表

```sql
CREATE TABLE app_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  platform TEXT NOT NULL DEFAULT 'google_play',
  app_id TEXT NOT NULL,
  country TEXT DEFAULT 'us',
  lang TEXT DEFAULT 'en',
  captured_at TEXT NOT NULL,

  title TEXT,
  developer TEXT,
  category TEXT,
  rating REAL,
  ratings_count INTEGER,
  reviews_count INTEGER,
  installs TEXT,
  min_installs INTEGER,
  max_installs INTEGER,
  price TEXT,
  free INTEGER,
  has_iap INTEGER,
  version TEXT,
  updated TEXT,
  released TEXT,
  android_version TEXT,
  content_rating TEXT,
  description TEXT,
  summary TEXT,
  changelog TEXT,
  icon_url TEXT,
  screenshots_json TEXT,
  raw_json TEXT
);
```

### 5.3 reviews 表

```sql
CREATE TABLE reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  platform TEXT NOT NULL DEFAULT 'google_play',
  app_id TEXT NOT NULL,
  country TEXT DEFAULT 'us',
  lang TEXT DEFAULT 'en',

  review_id TEXT,
  user_name TEXT,
  rating INTEGER,
  content TEXT,
  app_version TEXT,
  helpful_count INTEGER,
  review_created_at TEXT,
  captured_at TEXT NOT NULL,
  raw_json TEXT,

  UNIQUE(platform, app_id, review_id)
);
```

### 5.4 chart_snapshots 表

```sql
CREATE TABLE chart_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  platform TEXT NOT NULL DEFAULT 'google_play',
  chart_type TEXT NOT NULL,
  category TEXT,
  country TEXT DEFAULT 'us',
  lang TEXT DEFAULT 'en',
  captured_at TEXT NOT NULL,
  rank INTEGER NOT NULL,
  app_id TEXT NOT NULL,
  title TEXT,
  developer TEXT,
  rating REAL,
  installs TEXT,
  icon_url TEXT,
  raw_json TEXT
);
```

### 5.5 keyword_ranks 表

```sql
CREATE TABLE keyword_ranks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  platform TEXT NOT NULL DEFAULT 'google_play',
  keyword TEXT NOT NULL,
  app_id TEXT NOT NULL,
  country TEXT DEFAULT 'us',
  lang TEXT DEFAULT 'en',
  rank INTEGER,
  found INTEGER NOT NULL DEFAULT 0,
  checked_limit INTEGER,
  captured_at TEXT NOT NULL,
  raw_json TEXT
);
```

### 5.6 tracked_apps 表

```sql
CREATE TABLE tracked_apps (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  platform TEXT NOT NULL DEFAULT 'google_play',
  app_id TEXT NOT NULL,
  title TEXT,
  country TEXT DEFAULT 'us',
  lang TEXT DEFAULT 'en',
  frequency TEXT DEFAULT 'daily',
  enabled INTEGER NOT NULL DEFAULT 1,
  last_synced_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(platform, app_id, country, lang)
);
```

### 5.7 tracked_keywords 表

```sql
CREATE TABLE tracked_keywords (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  platform TEXT NOT NULL DEFAULT 'google_play',
  app_id TEXT NOT NULL,
  keyword TEXT NOT NULL,
  country TEXT DEFAULT 'us',
  lang TEXT DEFAULT 'en',
  frequency TEXT DEFAULT 'daily',
  enabled INTEGER NOT NULL DEFAULT 1,
  last_synced_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(platform, app_id, keyword, country, lang)
);
```

### 5.8 alerts 表

```sql
CREATE TABLE alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  type TEXT NOT NULL,
  severity TEXT NOT NULL,
  app_id TEXT,
  title TEXT,
  message TEXT NOT NULL,
  payload_json TEXT,
  is_read INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
```

### 5.9 settings 表

```sql
CREATE TABLE settings (
  key TEXT PRIMARY KEY,
  value TEXT,
  updated_at TEXT NOT NULL
);
```

---

## 6. Pydantic 数据结构

### 6.1 AppSummary

```python
class AppSummary(BaseModel):
    platform: str = "google_play"
    app_id: str
    title: str | None = None
    developer: str | None = None
    developer_id: str | None = None
    category: str | None = None
    rating: float | None = None
    ratings_count: int | None = None
    reviews_count: int | None = None
    installs: str | None = None
    min_installs: int | None = None
    price: str | None = None
    free: bool | None = None
    has_iap: bool | None = None
    icon_url: str | None = None
    store_url: str | None = None
    raw: dict[str, Any] = {}
```

### 6.2 AppDetail

```python
class AppDetail(AppSummary):
    version: str | None = None
    updated: str | None = None
    released: str | None = None
    android_version: str | None = None
    content_rating: str | None = None
    description: str | None = None
    summary: str | None = None
    changelog: str | None = None
    screenshots: list[str] = []
```

### 6.3 ReviewItem

```python
class ReviewItem(BaseModel):
    platform: str = "google_play"
    app_id: str
    review_id: str | None = None
    user_name: str | None = None
    rating: int | None = None
    content: str | None = None
    app_version: str | None = None
    helpful_count: int | None = None
    review_created_at: str | None = None
    raw: dict[str, Any] = {}
```

### 6.4 ChartItem

```python
class ChartItem(AppSummary):
    rank: int
    chart_type: str
    category: str | None = None
    country: str = "us"
    lang: str = "en"
```

### 6.5 KeywordRankResult

```python
class KeywordRankResult(BaseModel):
    platform: str = "google_play"
    keyword: str
    app_id: str
    country: str = "us"
    lang: str = "en"
    found: bool
    rank: int | None = None
    checked_limit: int
    captured_at: str
    results: list[AppSummary] = []
```

---

## 7. 服务层接口

### 7.1 GooglePlayService

文件：

```txt
app/services/google_play_service.py
```

必须实现：

```python
class GooglePlayService:
    def search(
        self,
        keyword: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 20,
    ) -> list[AppSummary]:
        ...

    def app_detail(
        self,
        app_id: str,
        country: str = "us",
        lang: str = "en",
    ) -> AppDetail:
        ...

    def similar(
        self,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 20,
    ) -> list[AppSummary]:
        ...

    def reviews(
        self,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        sort: str = "newest",
        limit: int = 100,
    ) -> list[ReviewItem]:
        ...

    def chart(
        self,
        chart_type: str,
        category: str | None = None,
        country: str = "us",
        lang: str = "en",
        limit: int = 100,
    ) -> list[ChartItem]:
        ...
```

底层使用 `google-play-scraper`。

示例导入：

```python
from google_play_scraper import app, search, reviews, Sort, collection
```

如果实际库接口和示例不同，开发时应检查包的真实 API，并适配。

### 7.2 KeywordService

```python
class KeywordService:
    def __init__(self, google_play_service: GooglePlayService):
        self.google_play_service = google_play_service

    def search(
        self,
        keyword: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 50,
    ) -> list[AppSummary]:
        return self.google_play_service.search(keyword, country, lang, limit)

    def rank(
        self,
        keyword: str,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 100,
    ) -> KeywordRankResult:
        ...
```

排名逻辑：

1. 调用 search。
2. 遍历结果。
3. 比较 `app_id`。
4. 找到则 rank = index + 1。
5. 找不到则 found = False, rank = None。

### 7.3 TrackingService

```python
class TrackingService:
    def add_app(self, app_id: str, country="us", lang="en") -> None: ...
    def remove_app(self, app_id: str, country="us", lang="en") -> None: ...
    def list_apps(self) -> list[TrackedApp]: ...
    def sync_app_now(self, app_id: str, country="us", lang="en") -> AppDetail: ...
    def sync_all_apps(self) -> int: ...
    def get_history(self, app_id: str, country="us", lang="en") -> list[AppSnapshot]: ...
```

### 7.4 MonetizationService

```python
class MonetizationService:
    def score(
        self,
        detail: AppDetail,
        grossing_rank: int | None = None,
        review_growth_rate: float | None = None,
    ) -> dict:
        ...
```

评分规则：

```txt
score = 0

has_iap:
  +20

free is false:
  +10

min_installs:
  >= 100,000,000: +25
  >= 10,000,000: +20
  >= 1,000,000: +15
  >= 100,000: +8

rating:
  >= 4.5: +10
  >= 4.0: +6
  >= 3.5: +3

ratings_count:
  >= 1,000,000: +15
  >= 100,000: +10
  >= 10,000: +5

grossing_rank:
  <= 10: +25
  <= 50: +18
  <= 100: +12
  <= 200: +6

review_growth_rate:
  >= 0.1: +10
  >= 0.03: +5

Clamp score to 100.
```

等级：

```txt
0-29: low
30-59: medium
60-79: high
80-100: very_high
```

返回：

```python
{
  "score": 82,
  "level": "very_high",
  "confidence": "low",
  "signals": [...],
  "note": "基于公开数据推断，不代表真实收入。"
}
```

---

## 8. UI 设计要求

使用 PySide6。

主窗口：

- QMainWindow
- 左侧 Sidebar
- 右侧 QStackedWidget
- 顶部标题区域
- 底部状态栏
- 全局 Loading
- 全局错误弹窗

侧边栏：

```txt
首页
应用搜索
应用详情
评论
榜单
关键词
监控
设置
```

窗口标题：

```txt
catch-radar - Google Play 情报工具
```

默认窗口大小：

```txt
1440 x 900
```

### 8.1 线程要求

所有网络请求、爬虫请求、数据库批处理都不能阻塞 UI 线程。

必须实现通用 Worker：

```python
class WorkerSignals(QObject):
    started = Signal()
    finished = Signal(object)
    error = Signal(str)
    progress = Signal(str)

class Worker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        ...
```

通过：

```python
QThreadPool.globalInstance().start(worker)
```

执行耗时任务。

---

## 9. 页面细节

### 9.1 首页 Dashboard

显示卡片：

- 监控 App 数量
- 已存快照数量
- 关键词监控数量
- 未读提醒数量
- 最后同步时间

表格：

- 最近提醒
- 最近变化 App

### 9.2 应用搜索页

输入：

- 关键词
- 国家
- 语言
- limit

按钮：

- 搜索
- 打开详情
- 加入监控

表格字段：

- 图标
- 应用名
- 包名
- 开发者
- 评分
- 评分数
- 安装量
- 价格
- 内购

### 9.3 应用详情页

输入：

- app_id
- 国家
- 语言

按钮：

- 获取详情
- 保存快照
- 加入监控
- 获取相似应用
- 获取评论
- 打开 Google Play

展示：

- icon
- title
- app_id
- developer
- category
- rating
- ratings_count
- reviews_count
- installs
- price
- has_iap
- version
- updated
- released
- description
- changelog
- screenshots
- similar apps table
- rating history chart
- reviews_count history chart
- monetization score card

### 9.4 评论页

输入：

- app_id
- 国家
- 语言
- sort
- limit
- rating filter
- text filter

按钮：

- 获取评论
- 保存评论

表格字段：

- 用户
- 星级
- 内容
- 版本
- helpful
- 时间

### 9.5 榜单页

输入：

- chart_type: top_free / top_paid / top_grossing
- category
- country
- lang
- limit

按钮：

- 获取榜单
- 保存榜单快照
- 打开详情

表格字段：

- rank
- icon
- title
- app_id
- developer
- rating
- installs

### 9.6 关键词页

输入：

- keyword
- target app_id
- country
- lang
- limit

按钮：

- 查询排名
- 保存排名
- 加入关键词监控

输出：

- 当前排名
- 搜索结果表
- 排名历史图

### 9.7 监控页

显示：

- tracked_apps 表
- tracked_keywords 表

按钮：

- 添加 App 监控
- 删除监控
- 同步选中
- 同步全部
- 启用 / 禁用

### 9.8 设置页

字段：

- default_country
- default_lang
- default_limit
- scheduler_enabled
- daily_sync_time
- database_path
- request_delay_seconds
- proxy

---

## 10. 定时任务

使用 APScheduler。

文件：

```txt
app/jobs/scheduler.py
```

实现：

```python
class AppScheduler:
    def start(self) -> None: ...
    def shutdown(self) -> None: ...
    def reload_jobs(self) -> None: ...
```

默认每天 09:00 同步。

定时任务：

```python
def sync_tracked_apps_job():
    tracking_service.sync_all_apps()
```

规则：

1. 如果 scheduler_enabled = false，不启动。
2. App 关闭后不继续后台同步。
3. 启动时自动读取设置。
4. 退出时关闭 scheduler。
5. 所有任务错误写入日志。

---

## 11. 数据标准化

文件：

```txt
app/utils/normalize.py
```

实现：

```python
def normalize_app_summary(raw: dict) -> AppSummary: ...
def normalize_app_detail(raw: dict) -> AppDetail: ...
def normalize_review(raw: dict, app_id: str) -> ReviewItem: ...
def normalize_chart_item(raw: dict, rank: int, chart_type: str, country: str, lang: str) -> ChartItem: ...
```

需要兼容字段：

```txt
appId / app_id
title
developer
developerId
genre
genreId
score
ratings
reviews
installs
minInstalls
maxInstalls
price
free
offersIAP
containsAds
version
updated
released
androidVersion
contentRating
description
summary
recentChanges
icon
screenshots
url
```

任何字段缺失都不能导致程序崩溃。

---

## 12. 安装量解析

文件：

```txt
app/utils/install_parser.py
```

实现：

```python
def parse_installs(text: str | None) -> tuple[int | None, int | None]:
    ...
```

测试用例：

```python
parse_installs("1,000+") == (1000, None)
parse_installs("10,000+") == (10000, None)
parse_installs("1M+") == (1000000, None)
parse_installs("5B+") == (5000000000, None)
parse_installs(None) == (None, None)
```

---

## 13. Alert 规则

同步 App 快照后生成提醒。

规则：

1. 评分下降 >= 0.2。
2. ratings_count 增长 >= 10%。
3. reviews_count 增长 >= 10%。
4. version 发生变化。
5. installs 档位变化。
6. App 获取失败或疑似下架。

提醒字段：

```txt
type
severity
app_id
title
message
payload_json
created_at
```

---

## 14. 设置默认值

```python
DEFAULT_SETTINGS = {
    "default_country": "us",
    "default_lang": "en",
    "default_limit": "50",
    "scheduler_enabled": "true",
    "daily_sync_time": "09:00",
    "request_delay_seconds": "1",
    "database_path": "./data/catch_radar.sqlite3",
    "proxy": "",
}
```

---

## 15. 错误处理

所有爬取请求必须捕获异常并给用户中文提示。

示例：

```txt
网络请求失败，请稍后重试。
没有找到该应用。
Google Play 返回空结果。
请求可能被限流，请稍后再试。
数据格式异常，请查看日志。
```

日志路径：

```txt
./data/logs/app.log
```

使用 rotating file handler：

- 5 MB 一个文件
- 保留 5 个备份

---

## 16. 打包

使用 PyInstaller。

README 中提供命令：

```bash
pyinstaller --noconfirm --windowed --name CatchRadar main.py
```

启动时自动创建：

```txt
data/
data/logs/
data/catch_radar.sqlite3
```

---

## 17. 测试

使用 pytest。

必须实现：

### test_install_parser.py

```python
parse_installs("1,000+") == (1000, None)
parse_installs("10,000+") == (10000, None)
parse_installs("1M+") == (1000000, None)
parse_installs("5B+") == (5000000000, None)
parse_installs(None) == (None, None)
```

### test_keyword_rank.py

mock search results:

- app found at rank 1
- app found at rank 10
- app not found

### test_monetization_score.py

- has_iap raises score
- high installs raises score
- grossing rank raises score
- score clamps to 100

### test_repositories.py

临时 SQLite：

- insert app
- insert snapshot
- list snapshots
- upsert reviews no duplicates
- add/remove tracked app

---

## 18. 开发阶段

### Phase 1: 基础设施

交付：

- 项目结构
- requirements.txt
- pyproject.toml
- SQLite 初始化
- SQLAlchemy models
- SettingsService
- Logging
- 主窗口
- Sidebar
- 空页面

验收：

- App 能启动。
- 数据库自动创建。
- 设置可读写。
- 页面可切换。

### Phase 2: 搜索和详情

交付：

- GooglePlayService.search
- GooglePlayService.app_detail
- App Search page
- App Detail page
- Snapshot saving

验收：

- 搜索 `photo editor` 有结果。
- 查询 `com.whatsapp` 有结果。
- 快照写入 SQLite。

### Phase 3: 评论和相似 App

交付：

- GooglePlayService.reviews
- GooglePlayService.similar
- Reviews page
- Similar apps table

验收：

- 能抓 100 条评论。
- 评论保存不重复。
- 相似 App 显示正常。

### Phase 4: 榜单和关键词

交付：

- GooglePlayService.chart
- KeywordService.rank
- Charts page
- Keywords page

验收：

- 能抓 top_free 榜单。
- 能查询关键词排名。
- 关键词排名历史可保存。

### Phase 5: 监控和定时任务

交付：

- Tracking page
- APScheduler
- Sync selected
- Sync all
- Daily sync

验收：

- 能加入监控。
- 能手动同步。
- 定时任务在 App 开启时生效。

### Phase 6: 首页和提醒

交付：

- Dashboard
- AlertService
- Monetization score

验收：

- 首页统计真实数据。
- 版本变化 / 评分下降产生提醒。
- 应用详情显示商业化强度。

---

## 19. 手动 QA 清单

### 搜索

- 搜索 `photo editor`
- 展示结果
- 双击结果进入详情

### 详情

- 输入 `com.whatsapp`
- 展示 title、developer、rating、installs
- 保存 snapshot
- 历史图显示

### 评论

- 抓取 `com.whatsapp` 评论
- 表格显示
- 重复抓取不重复保存

### 关键词

- keyword: `messenger`
- app_id: `com.whatsapp`
- 显示排名
- 保存历史

### 榜单

- 获取 top_free
- 排名显示正常

### 监控

- 添加 `com.whatsapp`
- 手动同步
- 快照数量增加

### 首页

- 数量正确
- 提醒显示

---

## 20. UI 参考图

Claude 开发时参考以下图片：

1. `ui_reference_dashboard.png`
2. `ui_reference_app_detail.png`
3. `ui_reference_reviews_keywords.png`
4. `ui_reference_tracking_settings.png`

设计风格：

- 桌面数据工具风格
- 左侧深色导航栏
- 右侧浅色内容区
- 卡片 + 表格 + 图表
- 优先清晰，不追求炫酷
- 中文标签
- 默认窗口 1440 x 900
