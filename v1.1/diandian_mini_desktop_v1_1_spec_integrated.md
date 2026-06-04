# 点点数据 Mini 桌面客户端 v1.1 开发规格书

版本：v1.1  
基于：v1.0 Python 单机桌面版  
目标开发方式：交给 Claude / Codex 以目标模式继续开发  
技术定位：Python 单机桌面客户端，一套代码，不做后端 API，不做 Web 服务  

---

## 1. v1.1 目标

v1.1 是在 v1.0 已完成的基础上继续增强，不重构主架构。

v1.1 重点新增：

1. App Store 基础支持。
2. CSV / Excel 导出。
3. AI 评论总结。
4. 商业化评分解释增强。
5. 数据刷新与缓存策略优化。
6. 本地项目 / 分组管理。
7. UI 细节优化。
8. 稳定性与错误处理增强。

v1.1 仍然是单机桌面应用，不做云端同步，不做多人协作，不做服务端 API。

---

## 2. v1.1 非目标

不要在 v1.1 做：

1. 真实订阅收入。
2. 真实 IAP 收入。
3. DAU / MAU。
4. 留存率。
5. 广告消耗。
6. 用户画像。
7. 云端账号。
8. 团队空间。
9. 分布式爬虫。
10. 大规模代理池。

商业化相关仍然只能叫：

```txt
商业化强度
商业化评分
收入区间粗略推断
```

不要叫：

```txt
真实收入
真实订阅收入
后台流水
精确下载量
```

---

## 3. v1.1 新增依赖

在 v1.0 基础上新增：

```txt
openpyxl
pandas
requests
```

如果实现 AI 评论总结：

```txt
openai
```

如果希望支持本地模型：

```txt
ollama
```

v1.1 requirements.txt 建议：

```txt
PySide6
SQLAlchemy
APScheduler
google-play-scraper
pydantic
python-dateutil
matplotlib
pytest
ruff
pyinstaller
pandas
openpyxl
requests
openai
```

如果用户没有配置 OpenAI Key，AI 功能应显示为未配置，而不是报错。

---

## 4. v1.1 项目结构变更

在 v1.0 结构上新增这些文件：

```txt
app/
├── services/
│   ├── app_store_service.py
│   ├── export_service.py
│   ├── ai_review_service.py
│   ├── project_service.py
│   └── cache_service.py
│
├── ui/
│   └── pages/
│       ├── export_page.py
│       ├── ai_reviews_page.py
│       └── projects_page.py
│
├── utils/
│   ├── csv_utils.py
│   ├── excel_utils.py
│   └── privacy.py
│
└── integrations/
    ├── __init__.py
    ├── app_store_scraper_node/
    │   ├── package.json
    │   ├── index.js
    │   └── README.md
    └── README.md
```

说明：

- Google Play 继续用 Python 库。
- App Store 推荐 v1.1 先通过 Node 子进程集成 app-store-scraper。
- 仍然不启动常驻后端服务。
- Node 脚本只在需要 App Store 数据时被 Python 调用。

---

## 5. v1.1 新增页面

侧边栏在 v1.0 基础上新增：

```txt
项目
AI 评论
导出
```

最终侧边栏：

```txt
首页
项目
应用搜索
应用详情
评论
AI 评论
榜单
关键词
监控
导出
设置
```

---

## 6. App Store 支持

### 6.1 目标

v1.1 支持 App Store 的基础能力：

1. 按关键词搜索 App Store。
2. 按 app id 获取详情。
3. 获取 App Store 评论。
4. 获取 App Store 榜单。
5. 在同一 UI 中用 platform 切换：
   - google_play
   - app_store

### 6.2 实现策略

优先使用 Node 版 app-store-scraper。

Python 调用方式：

```txt
Python AppStoreService
        ↓ subprocess
Node script
        ↓
app-store-scraper
        ↓
stdout JSON
        ↓
Python normalize
```

不要在 v1.1 为 App Store 开独立 HTTP 服务。

### 6.3 Node 集成目录

```txt
app/integrations/app_store_scraper_node/
├── package.json
├── index.js
└── README.md
```

package.json：

```json
{
  "name": "diandian-mini-app-store-scraper",
  "version": "1.0.0",
  "private": true,
  "type": "commonjs",
  "dependencies": {
    "app-store-scraper": "^0.17.0"
  }
}
```

### 6.4 Node CLI 协议

Python 调用：

```bash
node index.js search '{"term":"photo editor","country":"us","limit":20}'
node index.js app '{"id":310633997,"country":"us"}'
node index.js reviews '{"id":310633997,"country":"us","limit":100}'
node index.js charts '{"collection":"topfreeapplications","category":6007,"country":"us","limit":100}'
```

Node 输出必须是 JSON：

成功：

```json
{
  "ok": true,
  "data": []
}
```

失败：

```json
{
  "ok": false,
  "error": "error message"
}
```

### 6.5 AppStoreService

文件：

```txt
app/services/app_store_service.py
```

实现：

```python
class AppStoreService:
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

    def reviews(
        self,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        sort: str = "recent",
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

### 6.6 平台切换

所有相关页面增加平台选择：

```txt
平台: Google Play / App Store
```

内部值：

```txt
google_play
app_store
```

需要更新页面：

1. 应用搜索页
2. 应用详情页
3. 评论页
4. 榜单页
5. 关键词页
6. 监控页
7. 导出页

### 6.7 App Store 字段映射

App Store raw 字段映射到统一模型：

```txt
id -> app_id
appId -> bundle_id，可保存在 raw
title -> title
developer -> developer
developerId -> developer_id
genre -> category
score -> rating
reviews -> reviews_count
ratings -> ratings_count
price -> price
free -> free
version -> version
updated -> updated
released -> released
description -> description
icon -> icon_url
screenshots -> screenshots
url -> store_url
```

注意：

- App Store 没有 Google Play 安装量字段。
- App Store 的 installs、min_installs 应为 None。
- 商业化评分对 App Store 要降低置信度。

---

## 7. CSV / Excel 导出

### 7.1 目标

用户可以把本地数据导出为 CSV 或 Excel。

新增页面：

```txt
导出
```

### 7.2 ExportService

文件：

```txt
app/services/export_service.py
```

实现：

```python
class ExportService:
    def export_apps(self, path: str, file_type: str = "xlsx") -> str: ...
    def export_app_snapshots(self, path: str, file_type: str = "xlsx") -> str: ...
    def export_reviews(self, path: str, app_id: str | None = None, file_type: str = "xlsx") -> str: ...
    def export_keyword_ranks(self, path: str, file_type: str = "xlsx") -> str: ...
    def export_chart_snapshots(self, path: str, file_type: str = "xlsx") -> str: ...
    def export_all(self, path: str) -> str: ...
```

### 7.3 导出页面

字段：

```txt
数据类型：
- 应用基础信息
- 应用历史快照
- 评论
- 关键词排名
- 榜单快照
- 全部数据

文件格式：
- xlsx
- csv

筛选：
- platform
- app_id
- country
- date_from
- date_to
```

按钮：

```txt
选择保存路径
开始导出
打开文件夹
```

### 7.4 Excel 多 Sheet

当用户选择“全部数据”时，导出为一个 xlsx：

```txt
apps
app_snapshots
reviews
keyword_ranks
chart_snapshots
tracked_apps
alerts
```

### 7.5 导出要求

1. 导出不能阻塞 UI。
2. 空数据要提示，不要生成空文件后无提示。
3. 文件名默认：diandian_mini_export_YYYYMMDD_HHMMSS.xlsx
4. CSV 使用 UTF-8 with BOM，避免中文乱码。
5. Excel 第一行加粗。
6. 列宽自动适配。

---

## 8. AI 评论总结

### 8.1 目标

新增「AI 评论」页面，对已抓取评论做总结。

功能：

1. 总结差评原因。
2. 总结用户需求。
3. 总结 Bug 反馈。
4. 总结版本相关问题。
5. 输出产品改进建议。
6. 支持按 app、国家、语言、星级、时间范围筛选。

### 8.2 AIReviewService

文件：

```txt
app/services/ai_review_service.py
```

实现：

```python
class AIReviewService:
    def summarize_reviews(
        self,
        app_id: str,
        platform: str = "google_play",
        country: str = "us",
        lang: str = "en",
        rating_min: int | None = None,
        rating_max: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        max_reviews: int = 300,
    ) -> dict:
        ...
```

返回：

```python
{
  "summary": "...",
  "pain_points": [
    {"title": "登录失败", "count": 12, "evidence": ["..."]}
  ],
  "bug_reports": [
    {"title": "消息发送失败", "count": 8, "evidence": ["..."]}
  ],
  "feature_requests": [
    {"title": "希望支持主题色", "count": 5, "evidence": ["..."]}
  ],
  "sentiment": {
    "positive": 0.22,
    "neutral": 0.31,
    "negative": 0.47
  },
  "suggestions": [
    "优先排查最新版本的登录问题"
  ],
  "model": "openai 或 local",
  "created_at": "ISO_TIME"
}
```

### 8.3 AI 配置

设置页新增：

```txt
AI Provider:
- disabled
- openai
- ollama

OpenAI API Key:
- password input
- 本地保存
- 可为空

OpenAI Model:
- gpt-4o-mini
- gpt-4.1-mini
- 自定义

Ollama Base URL:
- http://localhost:11434

Ollama Model:
- qwen2.5
- llama3.1
- 自定义
```

注意：

- API Key 不要打印到日志。
- 配置为空时，AI 页面显示“尚未配置 AI”。
- AI 调用失败要显示中文错误。

### 8.4 AI Prompt

系统提示词：

```txt
你是一个移动应用评论分析助手。请基于用户评论总结问题、需求、Bug 和改进建议。不要编造评论中没有的信息。输出 JSON。
```

用户提示词模板：

```txt
请分析以下应用评论。

应用：{app_id}
平台：{platform}
国家：{country}
语言：{lang}
评论数量：{count}

请输出 JSON，字段包括：
summary, pain_points, bug_reports, feature_requests, sentiment, suggestions。

评论：
{reviews_text}
```

### 8.5 本地存储 AI 结果

新增表：

```sql
CREATE TABLE ai_review_insights (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  platform TEXT NOT NULL,
  app_id TEXT NOT NULL,
  country TEXT DEFAULT 'us',
  lang TEXT DEFAULT 'en',
  rating_min INTEGER,
  rating_max INTEGER,
  date_from TEXT,
  date_to TEXT,
  summary TEXT,
  pain_points_json TEXT,
  bug_reports_json TEXT,
  feature_requests_json TEXT,
  sentiment_json TEXT,
  suggestions_json TEXT,
  model TEXT,
  raw_json TEXT,
  created_at TEXT NOT NULL
);
```

---

## 9. 商业化评分解释增强

### 9.1 目标

v1.0 只有分数，v1.1 要给出更清晰解释。

应用详情页显示：

```txt
商业化强度：高
分数：72 / 100
置信度：低 / 中 / 高
```

解释：

```txt
加分项：
+20 存在应用内购
+15 安装量区间 >= 1,000,000
+10 评分 >= 4.5
+10 评分数 >= 100,000
+12 Top Grossing 排名 <= 100

扣分 / 限制：
- Google Play 公开安装量只是区间
- 没有真实订阅收入
- 没有真实付费率
```

### 9.2 MonetizationService 返回格式

```python
{
  "score": 72,
  "level": "high",
  "confidence": "medium",
  "positive_signals": [
    {"label": "存在应用内购", "points": 20},
    {"label": "安装量区间 >= 1,000,000", "points": 15}
  ],
  "negative_signals": [
    {"label": "无 Top Grossing 排名", "points": 0}
  ],
  "limitations": [
    "公开安装量不是精确下载量",
    "无法获取真实订阅收入",
    "无法获取退款和续订数据"
  ],
  "note": "基于公开数据推断，不代表真实收入。"
}
```

---

## 10. 项目 / 分组管理

### 10.1 目标

用户可以创建项目，把 App 和关键词归到项目里。

例如：

```txt
AI 图片工具
VPN 出海竞品
聊天应用竞品
```

### 10.2 新增表 projects

```sql
CREATE TABLE projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  description TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

### 10.3 新增表 project_apps

```sql
CREATE TABLE project_apps (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL,
  platform TEXT NOT NULL,
  app_id TEXT NOT NULL,
  country TEXT DEFAULT 'us',
  lang TEXT DEFAULT 'en',
  created_at TEXT NOT NULL,
  UNIQUE(project_id, platform, app_id, country, lang)
);
```

### 10.4 新增表 project_keywords

```sql
CREATE TABLE project_keywords (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL,
  platform TEXT NOT NULL,
  app_id TEXT NOT NULL,
  keyword TEXT NOT NULL,
  country TEXT DEFAULT 'us',
  lang TEXT DEFAULT 'en',
  created_at TEXT NOT NULL,
  UNIQUE(project_id, platform, app_id, keyword, country, lang)
);
```

### 10.5 Projects Page

页面功能：

1. 创建项目。
2. 编辑项目名称和描述。
3. 删除项目。
4. 查看项目下 App。
5. 查看项目下关键词。
6. 从搜索结果或详情页把 App 加入项目。
7. 从关键词页把关键词加入项目。

### 10.6 ProjectService

```python
class ProjectService:
    def create_project(self, name: str, description: str | None = None) -> int: ...
    def list_projects(self) -> list[Project]: ...
    def update_project(self, project_id: int, name: str, description: str | None) -> None: ...
    def delete_project(self, project_id: int) -> None: ...
    def add_app(self, project_id: int, platform: str, app_id: str, country: str, lang: str) -> None: ...
    def remove_app(self, project_id: int, platform: str, app_id: str, country: str, lang: str) -> None: ...
    def add_keyword(self, project_id: int, platform: str, app_id: str, keyword: str, country: str, lang: str) -> None: ...
    def list_project_apps(self, project_id: int) -> list: ...
    def list_project_keywords(self, project_id: int) -> list: ...
```

---

## 11. 缓存策略

### 11.1 目标

减少重复请求，提高体验。

新增设置：

```txt
cache_enabled = true
app_detail_cache_minutes = 60
search_cache_minutes = 30
reviews_cache_minutes = 60
charts_cache_minutes = 60
```

### 11.2 新增表 request_cache

```sql
CREATE TABLE request_cache (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cache_key TEXT NOT NULL UNIQUE,
  cache_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);
```

### 11.3 CacheService

```python
class CacheService:
    def get(self, cache_key: str) -> dict | list | None: ...
    def set(self, cache_key: str, cache_type: str, payload: dict | list, ttl_seconds: int) -> None: ...
    def delete_expired(self) -> int: ...
    def clear_all(self) -> int: ...
```

### 11.4 缓存键

```txt
google_play:search:{keyword}:{country}:{lang}:{limit}
google_play:detail:{app_id}:{country}:{lang}
google_play:reviews:{app_id}:{country}:{lang}:{sort}:{limit}
google_play:chart:{chart_type}:{category}:{country}:{lang}:{limit}

app_store:search:{keyword}:{country}:{lang}:{limit}
app_store:detail:{app_id}:{country}:{lang}
app_store:reviews:{app_id}:{country}:{lang}:{sort}:{limit}
app_store:chart:{chart_type}:{category}:{country}:{lang}:{limit}
```

---

## 12. UI 优化

### 12.1 全局体验

1. 所有表格支持复制 app_id。
2. 所有表格支持右键菜单：
   - 打开详情
   - 加入监控
   - 加入项目
   - 复制 App ID
   - 打开商店链接

3. 所有耗时按钮显示 loading。
4. 状态栏显示当前操作。
5. 网络失败时提示，不崩溃。
6. 详情页支持平台标签。

### 12.2 颜色建议

继续使用 v1.0 风格：

```txt
左侧导航：深色
内容区域：浅灰
卡片：白色
主按钮：蓝色
警告：橙色
错误：红色
成功：绿色
```

### 12.3 表格列宽

表格要求：

1. App 名称列宽较大。
2. app_id 可复制。
3. 长文本截断，但 tooltip 显示完整内容。
4. 评论内容列支持多行或展开弹窗。

---

## 13. 数据迁移

v1.1 必须兼容 v1.0 数据库。

新增 migrations：

```txt
001_init_v1.py
002_v1_1_add_ai_projects_cache.py
```

如果当前数据库没有新增表，则创建。

v1.1 启动时执行：

```python
run_migrations()
```

迁移要求：

1. 不删除 v1.0 数据。
2. 不重建旧表。
3. 新表不存在才创建。
4. 新字段不存在才添加。
5. 迁移失败写入日志，并提示用户备份数据库。

---

## 14. 设置项新增

新增设置：

```python
V1_1_DEFAULT_SETTINGS = {
    "ai_provider": "disabled",
    "openai_api_key": "",
    "openai_model": "gpt-4o-mini",
    "ollama_base_url": "http://localhost:11434",
    "ollama_model": "qwen2.5",
    "cache_enabled": "true",
    "app_detail_cache_minutes": "60",
    "search_cache_minutes": "30",
    "reviews_cache_minutes": "60",
    "charts_cache_minutes": "60",
    "export_default_format": "xlsx",
}
```

注意：

- OpenAI API Key 不要显示明文，输入框用 password mode。
- 不要把 API Key 写入日志。
- 本地存储即可，不要求加密。

---

## 15. v1.1 测试

新增测试：

### test_export_service.py

1. 导出 apps xlsx。
2. 导出 reviews csv。
3. 导出全部数据 xlsx 多 sheet。
4. 空数据时返回友好提示。

### test_cache_service.py

1. set/get cache。
2. expired cache returns None。
3. delete_expired works。
4. clear_all works。

### test_project_service.py

1. create project。
2. add app。
3. add keyword。
4. duplicate app should not duplicate。
5. delete project。

### test_monetization_explanation.py

1. returns positive_signals。
2. returns limitations。
3. score clamped to 100。
4. no exact revenue claim in note。

### test_app_store_service.py

如果 Node 环境不可用，允许 skip。

测试：

1. Node command builder。
2. parse success JSON。
3. parse error JSON。
4. normalize App Store detail。

---

## 16. v1.1 开发阶段

### Phase 1: 数据迁移和项目分组

交付：

- migrations
- projects 表
- project_apps 表
- project_keywords 表
- ProjectService
- Projects Page

验收：

- v1.0 数据库可打开。
- 可创建项目。
- 可把 App 加入项目。
- 可把关键词加入项目。

### Phase 2: 导出

交付：

- ExportService
- Export Page
- CSV 导出
- Excel 导出
- 全部数据多 sheet 导出

验收：

- 可导出 apps。
- 可导出 reviews。
- 可导出全部数据。
- 中文不乱码。

### Phase 3: 商业化解释增强

交付：

- MonetizationService 返回 explanation。
- 应用详情页显示加分项、限制和 disclaimer。

验收：

- 商业化评分显示完整解释。
- 不出现“真实收入”字样。

### Phase 4: AI 评论总结

交付：

- AIReviewService
- AI Reviews Page
- OpenAI 配置
- Ollama 配置
- ai_review_insights 表

验收：

- 未配置时显示提示。
- 配置后可分析本地评论。
- 结果保存到数据库。
- AI 调用失败不崩溃。

### Phase 5: 缓存

交付：

- request_cache 表
- CacheService
- scraper 查询前读缓存
- 设置页缓存配置
- 清理缓存按钮

验收：

- 相同请求在缓存期内不重复调用 scraper。
- 过期后重新请求。
- 可手动清空缓存。

### Phase 6: App Store 基础支持

交付：

- Node app-store-scraper wrapper
- AppStoreService
- 平台切换 UI
- 搜索 / 详情 / 评论 / 榜单基础支持

验收：

- 可搜索 App Store 应用。
- 可获取 App Store 详情。
- 可抓 App Store 评论。
- App Store 无安装量时 UI 不异常。

---

## 17. v1.1 手动 QA

### 数据迁移

- 用 v1.0 数据库启动 v1.1。
- 确认旧数据存在。
- 新表创建成功。

### 项目

- 创建项目“AI 图片工具”。
- 从搜索结果加入一个 App。
- 从关键词页加入一个关键词。
- 项目详情能看到数据。

### 导出

- 导出全部数据为 xlsx。
- 打开 Excel，确认多个 sheet。
- 中文正常。
- 空数据时提示明确。

### 商业化解释

- 打开 com.whatsapp。
- 商业化卡片显示 score、level、confidence。
- 能看到加分项和限制说明。

### AI 评论

- 抓取评论。
- 设置 OpenAI Key。
- 生成评论总结。
- 结果保存。
- 清空 Key 后显示未配置。

### 缓存

- 搜索 photo editor 两次。
- 第二次应更快或命中缓存。
- 清空缓存后再次请求。

### App Store

- platform 选择 App Store。
- 搜索 photo editor。
- 打开某 App 详情。
- 评论和榜单基础可用。

---

## 18. v1.1 README 更新

README 增加：

1. v1.1 新功能。
2. App Store Node wrapper 安装方式。
3. AI 配置说明。
4. 导出说明。
5. 数据缓存说明。
6. 免责声明。

App Store wrapper 安装：

```bash
cd app/integrations/app_store_scraper_node
npm install
```

AI 配置说明：

```txt
如果不配置 AI Provider，AI 评论页不可用，但其他功能正常。
```

免责声明：

```txt
本工具只使用公开商店数据。Google Play 安装量是公开档位，不是精确下载量。商业化评分基于公开信号推断，不代表真实收入、订阅收入或后台流水。
```

---

## 19. v1.1 给 Claude 的执行顺序

请按以下顺序开发：

1. 检查 v1.0 项目结构。
2. 添加 v1.1 migration。
3. 添加 projects / cache / ai_review_insights 数据表。
4. 实现 ProjectService。
5. 实现 Projects Page。
6. 实现 ExportService。
7. 实现 Export Page。
8. 增强 MonetizationService。
9. 更新 App Detail Page 商业化解释 UI。
10. 实现 AIReviewService。
11. 实现 AI Reviews Page。
12. 更新 Settings Page，加入 AI 和缓存配置。
13. 实现 CacheService。
14. 给 GooglePlayService 接入缓存。
15. 添加 Node app-store-scraper wrapper。
16. 实现 AppStoreService。
17. 给 Search / Detail / Reviews / Charts 页面加入 platform 切换。
18. 添加测试。
19. 更新 README。
20. 手动 QA。
21. 修复问题。
22. 打包验证。

---

## 20. v1.1 完成标准

v1.1 完成后，应用应具备：

1. Google Play 完整 v1.0 能力不退化。
2. App Store 基础搜索和详情能力。
3. 项目分组能力。
4. 本地数据导出能力。
5. AI 评论总结能力。
6. 缓存能力。
7. 更清晰的商业化解释。
8. v1.0 数据库兼容。
9. PyInstaller 可打包。
10. README 可指导用户安装和使用。

---

## 21. 真实上游调用地址

本项目是单机桌面应用，不提供后端 HTTP API。

桌面客户端内部调用链：

```txt
Python UI
  ↓
Service 层
  ↓
第三方 scraper / 官方接口 / 本地文件
```

本章节整理的是**真实会被请求的上游地址**，不是我们自己封装的 Python 方法名。

---

### 21.1 真实上游地址总览

| 模块 | 功能 | 真实地址 / 域名 | 示例 |
|---|---|---|---|
| Google Play | 应用详情 | `https://play.google.com/store/apps/details` | `https://play.google.com/store/apps/details?id=com.whatsapp&hl=en&gl=US` |
| Google Play | 搜索 | `https://play.google.com/store/search` | `https://play.google.com/store/search?q=photo%20editor&c=apps&hl=en&gl=US` |
| Google Play | 评论 | Google Play Web 内部 RPC | 由 `google-play-scraper` 封装，不建议手写 |
| Google Play | 榜单 | Google Play collection / 内部接口 | 由 `google-play-scraper` 封装 |
| Google Play | 相似应用 | Google Play 详情页 related / similar 区块 | 由 `google-play-scraper` 封装 |
| App Store | 搜索 | `https://itunes.apple.com/search` | `https://itunes.apple.com/search?term=photo%20editor&country=us&entity=software&limit=20` |
| App Store | 应用详情 | `https://itunes.apple.com/lookup` | `https://itunes.apple.com/lookup?id=310633997&country=us` |
| App Store | 应用详情 by bundleId | `https://itunes.apple.com/lookup` | `https://itunes.apple.com/lookup?bundleId=com.burbn.instagram&country=us` |
| App Store | 评论 | `https://itunes.apple.com/{country}/rss/customerreviews/.../json` | `https://itunes.apple.com/us/rss/customerreviews/id=310633997/sortBy=mostRecent/json` |
| App Store | 评论分页 | `https://itunes.apple.com/{country}/rss/customerreviews/page={page}/.../json` | `https://itunes.apple.com/us/rss/customerreviews/page=1/id=310633997/sortBy=mostRecent/json` |
| App Store | 免费榜 | `https://itunes.apple.com/{country}/rss/topfreeapplications/.../json` | `https://itunes.apple.com/us/rss/topfreeapplications/limit=100/genre=6007/json` |
| App Store | 付费榜 | `https://itunes.apple.com/{country}/rss/toppaidapplications/.../json` | `https://itunes.apple.com/us/rss/toppaidapplications/limit=100/genre=6007/json` |
| App Store | 收入榜 | `https://itunes.apple.com/{country}/rss/topgrossingapplications/.../json` | `https://itunes.apple.com/us/rss/topgrossingapplications/limit=100/genre=6007/json` |
| OpenAI | AI 评论总结 | `https://api.openai.com/v1/responses` | `POST /v1/responses` |
| OpenAI | Chat Completions 可选 | `https://api.openai.com/v1/chat/completions` | `POST /v1/chat/completions` |
| Ollama | 本地 AI chat | `http://localhost:11434/api/chat` | `POST /api/chat` |
| Ollama | 本地 AI generate | `http://localhost:11434/api/generate` | `POST /api/generate` |
| npm | app-store-scraper 安装 | `https://registry.npmjs.org/app-store-scraper` | `npm install app-store-scraper` |
| 本地 DB | SQLite | `./data/diandian_mini.sqlite3` | 本地文件 |
| 本地日志 | Log file | `./data/logs/app.log` | 本地文件 |

---

### 21.2 Google Play 真实调用地址

#### 21.2.1 应用详情

真实页面地址：

```txt
https://play.google.com/store/apps/details
```

示例：

```txt
https://play.google.com/store/apps/details?id=com.whatsapp&hl=en&gl=US
```

参数：

| 参数 | 示例 | 说明 |
|---|---|---|
| `id` | `com.whatsapp` | Android package name |
| `hl` | `en` | 语言 |
| `gl` | `US` | 国家 / 地区 |

Python 层建议调用：

```python
from google_play_scraper import app

result = app(
    "com.whatsapp",
    lang="en",
    country="us",
)
```

---

#### 21.2.2 应用搜索

真实页面地址：

```txt
https://play.google.com/store/search
```

示例：

```txt
https://play.google.com/store/search?q=photo%20editor&c=apps&hl=en&gl=US
```

参数：

| 参数 | 示例 | 说明 |
|---|---|---|
| `q` | `photo editor` | 搜索关键词 |
| `c` | `apps` | 搜索 App |
| `hl` | `en` | 语言 |
| `gl` | `US` | 国家 / 地区 |

Python 层建议调用：

```python
from google_play_scraper import search

result = search(
    "photo editor",
    lang="en",
    country="us",
    n_hits=20,
)
```

---

#### 21.2.3 评论

Google Play 评论不建议手写 URL。

原因：

1. 评论分页通常通过 Google Play Web 内部 RPC 获取。
2. 请求参数复杂。
3. Google Play 页面结构变化可能导致手写逻辑失效。
4. scraper 库已经封装了这部分逻辑。

Python 层建议调用：

```python
from google_play_scraper import reviews, Sort

result, token = reviews(
    "com.whatsapp",
    lang="en",
    country="us",
    sort=Sort.NEWEST,
    count=100,
)
```

真实上游类型：

```txt
Google Play Web 内部 RPC / batchexecute
```

---

#### 21.2.4 榜单

Google Play 榜单建议用 scraper 封装，不要硬写 URL。

Python 层建议调用：

```python
from google_play_scraper import collection

result = collection(
    collection="topselling_free",
    category="APPLICATION",
    country="us",
    lang="en",
    n_hits=100,
)
```

具体 collection 映射需要按 `google-play-scraper` 实际 API 调整。

建议内部统一枚举：

```txt
top_free      -> topselling_free
top_paid      -> topselling_paid
top_grossing  -> topgrossing
```

---

#### 21.2.5 相似应用

相似应用通常来自：

```txt
Google Play 应用详情页 related / similar 区块
```

Python 层根据库能力实现：

```python
# 如果当前库支持 similar
service.similar("com.whatsapp", country="us", lang="en", limit=20)

# 如果当前库不支持 similar
# 则先从 app detail raw 中解析，或暂时返回空列表并提示“不支持”
```

---

### 21.3 App Store 真实调用地址

App Store 比 Google Play 更适合直接使用 URL，因为 Apple 有公开的 iTunes Search / Lookup API。

#### 21.3.1 App Store 搜索

真实地址：

```txt
https://itunes.apple.com/search
```

示例：

```txt
https://itunes.apple.com/search?term=photo%20editor&country=us&entity=software&limit=20
```

参数：

| 参数 | 示例 | 说明 |
|---|---|---|
| `term` | `photo editor` | 搜索关键词 |
| `country` | `us` | 国家 |
| `entity` | `software` | 搜索 App |
| `limit` | `20` | 返回数量 |

Python requests 示例：

```python
import requests

resp = requests.get(
    "https://itunes.apple.com/search",
    params={
        "term": "photo editor",
        "country": "us",
        "entity": "software",
        "limit": 20,
    },
    timeout=20,
)
data = resp.json()
```

返回结构通常包含：

```json
{
  "resultCount": 20,
  "results": []
}
```

---

#### 21.3.2 App Store 应用详情：按 id 查询

真实地址：

```txt
https://itunes.apple.com/lookup
```

示例：

```txt
https://itunes.apple.com/lookup?id=310633997&country=us
```

Python requests 示例：

```python
import requests

resp = requests.get(
    "https://itunes.apple.com/lookup",
    params={
        "id": "310633997",
        "country": "us",
    },
    timeout=20,
)
data = resp.json()
```

---

#### 21.3.3 App Store 应用详情：按 bundleId 查询

真实地址：

```txt
https://itunes.apple.com/lookup
```

示例：

```txt
https://itunes.apple.com/lookup?bundleId=com.burbn.instagram&country=us
```

Python requests 示例：

```python
import requests

resp = requests.get(
    "https://itunes.apple.com/lookup",
    params={
        "bundleId": "com.burbn.instagram",
        "country": "us",
    },
    timeout=20,
)
data = resp.json()
```

---

#### 21.3.4 App Store 评论

常见 RSS JSON 地址：

```txt
https://itunes.apple.com/{country}/rss/customerreviews/id={app_id}/sortBy=mostRecent/json
```

示例：

```txt
https://itunes.apple.com/us/rss/customerreviews/id=310633997/sortBy=mostRecent/json
```

分页示例：

```txt
https://itunes.apple.com/us/rss/customerreviews/page=1/id=310633997/sortBy=mostRecent/json
```

Python requests 示例：

```python
import requests

url = "https://itunes.apple.com/us/rss/customerreviews/page=1/id=310633997/sortBy=mostRecent/json"

resp = requests.get(url, timeout=20)
data = resp.json()
```

注意：

1. App Store 评论 RSS 返回结构和 Search API 不同。
2. 不同国家评论不同。
3. 评论数量有限，不保证能拿到全部历史评论。
4. 有时 RSS 字段会变化，必须防御式解析。

---

#### 21.3.5 App Store 免费榜

真实地址模板：

```txt
https://itunes.apple.com/{country}/rss/topfreeapplications/limit={limit}/genre={genre}/json
```

示例：

```txt
https://itunes.apple.com/us/rss/topfreeapplications/limit=100/genre=6007/json
```

---

#### 21.3.6 App Store 付费榜

真实地址模板：

```txt
https://itunes.apple.com/{country}/rss/toppaidapplications/limit={limit}/genre={genre}/json
```

示例：

```txt
https://itunes.apple.com/us/rss/toppaidapplications/limit=100/genre=6007/json
```

---

#### 21.3.7 App Store 收入榜

真实地址模板：

```txt
https://itunes.apple.com/{country}/rss/topgrossingapplications/limit={limit}/genre={genre}/json
```

示例：

```txt
https://itunes.apple.com/us/rss/topgrossingapplications/limit=100/genre=6007/json
```

---

#### 21.3.8 App Store 榜单类型映射

| 内部 chart_type | App Store RSS path |
|---|---|
| `top_free` | `topfreeapplications` |
| `top_paid` | `toppaidapplications` |
| `top_grossing` | `topgrossingapplications` |

---

#### 21.3.9 App Store 常见 genre id

| 类型 | genre id |
|---|---|
| 全部 App | 可省略 genre |
| Business | `6000` |
| Weather | `6001` |
| Utilities | `6002` |
| Travel | `6003` |
| Sports | `6004` |
| Social Networking | `6005` |
| Reference | `6006` |
| Productivity | `6007` |
| Photo & Video | `6008` |
| News | `6009` |
| Navigation | `6010` |
| Music | `6011` |
| Lifestyle | `6012` |
| Health & Fitness | `6013` |
| Games | `6014` |
| Finance | `6015` |
| Entertainment | `6016` |
| Education | `6017` |
| Books | `6018` |
| Medical | `6020` |
| Newsstand | `6021` |
| Catalogs | `6022` |
| Food & Drink | `6023` |
| Shopping | `6024` |
| Stickers | `6025` |
| Developer Tools | `6026` |
| Graphics & Design | `6027` |

---

### 21.4 App Store Node Wrapper 真实调用链

如果使用 Node `app-store-scraper`，Python 不直接调 Apple URL，而是通过子进程。

调用链：

```txt
Python AppStoreService
  ↓ subprocess.run()
node app/integrations/app_store_scraper_node/index.js
  ↓
app-store-scraper
  ↓
itunes.apple.com / apps.apple.com / RSS
```

Python 示例：

```python
import subprocess
import json

payload = {
    "term": "photo editor",
    "country": "us",
    "limit": 20,
}

result = subprocess.run(
    [
        "node",
        "app/integrations/app_store_scraper_node/index.js",
        "search",
        json.dumps(payload, ensure_ascii=False),
    ],
    capture_output=True,
    text=True,
    timeout=30,
    check=True,
)

data = json.loads(result.stdout)
```

Node 输出协议：

```json
{
  "ok": true,
  "data": []
}
```

错误协议：

```json
{
  "ok": false,
  "error": "error message"
}
```

---

### 21.5 OpenAI 真实调用地址

#### 21.5.1 推荐：Responses API

真实地址：

```txt
https://api.openai.com/v1/responses
```

HTTP 示例：

```http
POST https://api.openai.com/v1/responses
Authorization: Bearer YOUR_OPENAI_API_KEY
Content-Type: application/json
```

Body 示例：

```json
{
  "model": "gpt-4.1-mini",
  "input": "请总结这些应用评论..."
}
```

Python 示例：

```python
from openai import OpenAI

client = OpenAI(api_key=api_key)

response = client.responses.create(
    model="gpt-4.1-mini",
    input="请总结这些应用评论...",
)
```

---

#### 21.5.2 可选：Chat Completions

真实地址：

```txt
https://api.openai.com/v1/chat/completions
```

HTTP 示例：

```http
POST https://api.openai.com/v1/chat/completions
Authorization: Bearer YOUR_OPENAI_API_KEY
Content-Type: application/json
```

Body 示例：

```json
{
  "model": "gpt-4.1-mini",
  "messages": [
    {
      "role": "system",
      "content": "你是一个移动应用评论分析助手。"
    },
    {
      "role": "user",
      "content": "请总结这些应用评论..."
    }
  ]
}
```

---

### 21.6 Ollama 本地调用地址

如果用户选择 Ollama，本地真实地址一般是：

```txt
http://localhost:11434/api/chat
```

或：

```txt
http://localhost:11434/api/generate
```

推荐 v1.1 用 chat 接口：

```http
POST http://localhost:11434/api/chat
Content-Type: application/json
```

Body 示例：

```json
{
  "model": "qwen2.5",
  "messages": [
    {
      "role": "user",
      "content": "请总结这些应用评论..."
    }
  ],
  "stream": false
}
```

---

### 21.7 npm 依赖真实地址

App Store wrapper 安装依赖时：

```bash
npm install app-store-scraper
```

实际访问 npm registry：

```txt
https://registry.npmjs.org/app-store-scraper
```

---

### 21.8 本地文件地址

这些不是网络地址，是本地真实路径。

| 功能 | 真实地址 |
|---|---|
| SQLite 数据库 | `./data/diandian_mini.sqlite3` |
| 日志 | `./data/logs/app.log` |
| 导出文件 | 用户选择路径，例如 `~/Downloads/diandian_mini_export_20260604_120000.xlsx` |
| App Store Node wrapper | `./app/integrations/app_store_scraper_node/index.js` |

---

### 21.9 实现约束

1. Google Play 详情和搜索可以用真实页面 URL 理解数据来源，但代码层优先使用 `google-play-scraper`。
2. Google Play 评论、榜单、分页不建议手写 URL，必须优先使用 `google-play-scraper` 封装。
3. App Store 搜索和详情可以直接用 `https://itunes.apple.com/search` 和 `https://itunes.apple.com/lookup`。
4. App Store 评论和榜单可以用 RSS JSON 地址，也可以通过 `app-store-scraper` 封装。
5. OpenAI API Key 不能写入日志。
6. Ollama 是本地地址，不需要 API Key。
7. 所有网络请求必须有 timeout。
8. 所有网络错误必须用中文提示，不允许导致 UI 崩溃。

