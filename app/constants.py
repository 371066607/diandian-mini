APP_TITLE = "catch-radar - Google Play 情报工具"
# owner/name of the GitHub repo the in-app update checker queries for new releases
GITHUB_REPO = "371066607/catch-radar"
DEFAULT_STOREINTEL_API_URL = "https://catchradar.meshub.ai"
WINDOW_WIDTH = 1440
WINDOW_HEIGHT = 900

SIDEBAR_ITEMS = [
    ("dashboard", "🏠  首页"),
    ("app_search", "🔍  搜索"),
    ("app_detail", "📱  应用详情"),
    ("reviews", "💬  评论"),
    ("charts", "📊  榜单"),
    ("keywords", "🔑  关键词"),
    ("tracking", "👁  监控"),
    ("history", "📈  历史"),
    ("alerts", "🔔  提醒"),
    ("settings", "⚙️  设置"),
]

DEFAULT_SETTINGS = {
    "default_country": "us",
    "default_lang": "en",
    "default_limit": "50",
    "scheduler_enabled": "true",
    "daily_sync_time": "09:00",
    "request_delay_seconds": "1",
    "database_path": "./data/catch_radar.sqlite3",
    "proxy": "",
    "theme": "slate",  # UI 主题（含亮/暗），可在设置页切换：light / sand / slate / violet / teal
    # --- Coverage scan proxy pool (覆盖词扫描多 IP 并发，仅在配置了代理时启用) ---
    # 代理清单：每行/逗号一个，形如 http://host:port（也接受 host:port）。也可放
    # data/proxies.txt。配了代理才会并发；没配则维持单线程串行（同 IP 并发=徒增封禁风险）。
    "coverage_proxies": "",
    "coverage_concurrency": "6",  # 配了代理时的最大并发线程数
    # --- Alert thresholds (tunable sensitivity for the monitoring diffs) ---
    "alert_rating_drop": "0.2",  # 评分下降达到该绝对值才告警
    "alert_growth_percent": "10",  # 评分数/评论数增长达到该百分比才告警
    "alert_keyword_top_band": "10",  # 关键词「前 N 名」里程碑
    "alert_keyword_move": "5",  # 关键词榜内移动该名次才告警
    "alert_negative_review_surge_percent": "20",  # 新增评分里差评(1-2星)占比达此值告警
    "alert_positive_ratio_drop": "5",  # 好评率(4-5星占比)下降达此百分点告警
    # --- Desktop notifications (主动推送后台同步产生的告警) ---
    "desktop_notifications": "true",  # 是否弹系统托盘通知
    "notify_min_severity": "high",  # 仅推送 >= 此级别的告警：high/medium/low
    # --- Sync failure escalation ---
    "alert_fetch_escalate_after": "3",  # 连续失败达到该次数升级为「持续失败」高优告警
    # --- History data retention (保留清理；默认保守安全，每个对象至少保留 min_keep 条) ---
    "retention_enabled": "true",  # 是否启用历史数据自动清理
    "snapshot_retention_days": "180",  # 应用快照保留天数
    "keyword_retention_days": "180",  # 关键词排名保留天数
    "alert_retention_days": "365",  # 告警（仅已读）保留天数
    "review_retention_days": "180",  # 评论保留天数
    "retention_min_keep": "30",  # 每个对象至少保留最近多少条（早于此不删，趋势不空）
    # --- Review monitoring (同步时抓取评论并对新增差评告警) ---
    "review_monitor_enabled": "true",  # 同步监控 App 时是否顺带抓评论
    "review_monitor_limit": "50",  # 每次抓取的评论条数上限
    "review_alert_max_rating": "2",  # 评分 <= 此值视为差评
    "review_alert_min_count": "3",  # 本次新增差评达到该条数才告警
}

# Severity ordering for notify_min_severity filtering (higher = more urgent).
SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2}

NETWORK_ERROR_MESSAGE = "网络请求失败，请稍后重试。"
NOT_FOUND_MESSAGE = "没有找到该应用。"
EMPTY_RESULT_MESSAGE = "Google Play 返回空结果。"
RATE_LIMIT_MESSAGE = "请求可能被限流，请稍后再试。"
DATA_ERROR_MESSAGE = "数据格式异常，请查看日志。"
