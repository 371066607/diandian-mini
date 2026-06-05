"""Shared Chinese labels / colors for alert display.

Single source of truth for the Dashboard's "最近提醒" table and the dedicated
Alert Center page, so the two never drift out of sync as new alert types land.
"""

from __future__ import annotations

# Human-readable Chinese labels for the raw alert `type` codes.
ALERT_TYPE_LABELS = {
    "rating_drop": "评分下降",
    "ratings_growth": "评分数增长",
    "reviews_growth": "评论数增长",
    "version_changed": "版本变化",
    "negative_review_surge": "差评激增",
    "positive_ratio_drop": "好评率下降",
    "review_negative_spike": "新增差评",
    "install_band_changed": "安装档位变化",
    "installs_milestone": "安装量里程碑",
    "ads_changed": "广告状态变化",
    "price_changed": "价格/促销变化",
    "developer_contact_changed": "开发者信息变化",
    "fetch_failed": "抓取失败",
    "fetch_failed_persistent": "持续抓取失败",
    "fetch_recovered": "抓取恢复",
    "keyword_entered": "进入榜单",
    "keyword_dropped": "跌出范围",
    "keyword_top_entered": "升入前N",
    "keyword_top_dropped": "跌出前N",
    "keyword_rank_up": "排名上升",
    "keyword_rank_down": "排名下降",
    "chart_entered": "进入榜单",
    "chart_dropped": "跌出榜单",
    "chart_top_entered": "升入榜单前N",
    "chart_top_dropped": "跌出榜单前N",
    "chart_rank_up": "榜单排名上升",
    "chart_rank_down": "榜单排名下降",
}

ALERT_SEVERITY_LABELS = {"high": "高", "medium": "中", "low": "低"}

# Filter dropdown label -> stored severity value (None = no filter).
ALERT_SEVERITY_FILTERS = {"全部级别": None, "仅高": "high", "仅中": "medium", "仅低": "low"}

# Row-tint colors by severity (None severities are left untinted).
ALERT_SEVERITY_COLORS = {"high": "#DC2626", "medium": "#D97706", "low": "#0F766E"}


def alert_type_label(alert_type: str) -> str:
    return ALERT_TYPE_LABELS.get(alert_type, alert_type)


def alert_severity_label(severity: str) -> str:
    return ALERT_SEVERITY_LABELS.get(severity, severity)
