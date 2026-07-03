"""Pure, stateless display-formatting helpers shared across QmlBridge domains.

These were originally private @staticmethods on QmlBridge, called from
dashboard/tracking/search/detail/reviews/alerts code alike (e.g. _fmt_count
is used by both the search-results and app-detail formatters). Extracted
as plain functions — not tied to any one domain controller — so every
controller (and QmlBridge itself, during the ongoing decomposition) can
import them directly instead of routing through the bridge.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from app.ui.alert_labels import ALERT_SEVERITY_COLORS, alert_severity_label, alert_type_label
from app.utils.time_utils import FREQUENCY_HOURS, is_sync_due


def rank_text(rank) -> str:
    return ("#" + str(rank)) if rank else "未命中"


def fmt_size(value) -> str:
    try:
        size = int(value)
    except (TypeError, ValueError):
        return "-"
    if size >= 1024**3:
        return f"{size / 1024**3:.2f} GB"
    return f"{size / 1024**2:.1f} MB"


def histogram_rows(histogram) -> list[dict[str, Any]]:
    counts = list(histogram or [])
    if not counts or sum(counts) == 0:
        return []
    total = sum(counts)
    maximum = max(counts) or 1
    rows = []
    for star in range(5, 0, -1):
        count = counts[star - 1] if len(counts) >= star else 0
        rows.append(
            {
                "star": star,
                "count": count,
                "ratio": count / maximum,
                "text": f"{count:,} ({count / total * 100:.0f}%)",
            }
        )
    return rows


def price_label(item) -> str:
    # None means "unknown" (e.g. iTunes has no IAP/ads flags) — say nothing then.
    parts = [item.price or ("免费" if item.free in (True, None) else "-")]
    if item.has_iap is not None:
        parts.append("含内购" if item.has_iap else "无内购")
    ads = item.contains_ads if item.contains_ads is not None else item.ad_supported
    if ads is not None:
        parts.append("含广告" if ads else "无广告")
    return " · ".join(parts)


def fmt_count(value) -> str:
    return f"{value:,}" if isinstance(value, (int, float)) and value else "-"


def yes_no(value) -> str:
    if value is None:
        return "-"
    return "是" if value else "否"


def data_safety_text(data_safety) -> str:
    """Render the dataSafety list (shape varies by source) into a short summary."""
    if not data_safety:
        return "-"
    parts: list[str] = []
    for entry in data_safety:
        if isinstance(entry, dict):
            name = (
                entry.get("data") or entry.get("type") or entry.get("name") or entry.get("category")
            )
            if name:
                parts.append(str(name))
        elif entry:
            parts.append(str(entry))
    if not parts:
        return f"{len(data_safety)} 项"
    return "、".join(parts[:8]) + (" …" if len(parts) > 8 else "")


def compact_text(value: Any, limit: int = 0) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    if limit > 0 and len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def short_time(value: str | None) -> str:
    if not value:
        return "-"
    return value[5:16].replace("T", " ") if len(value) >= 16 else value


def fmt_dt(value: str | None) -> str:
    if not value:
        return "未同步"
    try:
        return datetime.fromisoformat(value).strftime("%m-%d %H:%M")
    except (TypeError, ValueError):
        return value[:10] if len(value) >= 10 else value


def latest_sync_time(*groups) -> str | None:
    values = [
        item.last_synced_at
        for group in groups
        for item in group
        if getattr(item, "last_synced_at", None)
    ]
    return max(values) if values else None


def frequency_label(value: str | None) -> str:
    return {"daily": "每日", "weekly": "每周", "manual": "手动"}.get(value or "daily", value)


def fail_label(item) -> str:
    count = getattr(item, "consecutive_failures", 0) or 0
    return "-" if count == 0 else f"{count} 次"


def review_row(item) -> dict[str, Any]:
    raw = getattr(item, "raw", None) or {}
    raw_text = ""
    if raw:
        try:
            raw_text = json.dumps(raw, ensure_ascii=False, separators=(",", ":"))
        except TypeError:
            raw_text = str(raw)
    rating = getattr(item, "rating", None)
    helpful = getattr(item, "helpful_count", None)
    review_created_at = getattr(item, "review_created_at", "") or ""
    captured_at = getattr(item, "captured_at", "") or ""
    content = getattr(item, "content", "") or ""
    return {
        "platform": getattr(item, "platform", "") or "-",
        "appId": getattr(item, "app_id", "") or "-",
        "country": getattr(item, "country", "") or "-",
        "lang": getattr(item, "lang", "") or "-",
        "reviewId": getattr(item, "review_id", "") or "-",
        "user": getattr(item, "user_name", "") or "-",
        "rating": rating if rating is not None else "-",
        "version": getattr(item, "app_version", "") or "-",
        "helpful": helpful if helpful is not None else "-",
        "time": review_created_at[:10] or "-",
        "reviewCreatedAt": review_created_at[:19].replace("T", " ") or "-",
        "capturedAt": captured_at[:19].replace("T", " ") or "-",
        "content": compact_text(content),
        "contentFull": str(content),
        "rawText": compact_text(raw_text, 500),
        "rawFull": raw_text,
    }


def alert_row(alert) -> dict[str, Any]:
    return {
        "id": alert.id,
        "time": short_time(alert.created_at),
        "severity": alert_severity_label(alert.severity),
        "severityColor": ALERT_SEVERITY_COLORS.get(alert.severity, "#64748B"),
        "type": alert_type_label(alert.type),
        "appId": alert.app_id or "-",
        "message": alert.message,
        "isRead": "已读" if alert.is_read else "未读",
        "unread": not alert.is_read,
    }


def next_sync_label(last_synced_at: str | None, frequency: str | None) -> str:
    freq = (frequency or "daily").lower()
    if freq == "manual":
        return "手动"
    if not last_synced_at:
        return "待首次同步"
    if is_sync_due(last_synced_at, freq):
        return "已到期"
    interval = FREQUENCY_HOURS.get(freq, FREQUENCY_HOURS["daily"])
    if interval is None:
        return "手动"
    try:
        last = datetime.fromisoformat(last_synced_at)
    except (ValueError, TypeError):
        return "待首次同步"
    return (last + timedelta(hours=interval)).strftime("%m-%d %H:%M")
