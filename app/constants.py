APP_TITLE = "点点数据 Mini - Google Play 情报工具"
# owner/name of the GitHub repo the in-app update checker queries for new releases
GITHUB_REPO = "371066607/diandian-mini"
WINDOW_WIDTH = 1440
WINDOW_HEIGHT = 900

SIDEBAR_ITEMS = [
    ("dashboard", "首页"),
    ("app_search", "应用搜索"),
    ("app_detail", "应用详情"),
    ("reviews", "评论"),
    ("charts", "榜单"),
    ("keywords", "关键词"),
    ("tracking", "监控"),
    ("settings", "设置"),
]

DEFAULT_SETTINGS = {
    "default_country": "us",
    "default_lang": "en",
    "default_limit": "50",
    "scheduler_enabled": "true",
    "daily_sync_time": "09:00",
    "request_delay_seconds": "1",
    "database_path": "./data/diandian_mini.sqlite3",
    "proxy": "",
}

NETWORK_ERROR_MESSAGE = "网络请求失败，请稍后重试。"
NOT_FOUND_MESSAGE = "没有找到该应用。"
EMPTY_RESULT_MESSAGE = "Google Play 返回空结果。"
RATE_LIMIT_MESSAGE = "请求可能被限流，请稍后再试。"
DATA_ERROR_MESSAGE = "数据格式异常，请查看日志。"
