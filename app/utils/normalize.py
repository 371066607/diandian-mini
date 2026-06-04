from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.schemas.app_schema import AppDetail, AppSummary
from app.schemas.chart_schema import ChartItem
from app.schemas.review_schema import ReviewItem
from app.utils.install_parser import parse_installs


def bool_to_int(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if value else 0


def int_to_bool(value: int | None) -> bool | None:
    if value is None:
        return None
    return bool(value)


def safe_int(value: Any, default: int = 0) -> int:
    """Best-effort int conversion that never raises (returns ``default``)."""
    result = _to_int(value)
    return default if result is None else result


def safe_float(value: Any, default: float = 0.0) -> float:
    """Best-effort float conversion that never raises (returns ``default``)."""
    result = _to_float(value)
    return default if result is None else result


def dump_json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, default=str)


def normalize_app_summary(raw: dict) -> AppSummary:
    app_id = _get_first(raw, "appId", "app_id")
    min_installs = _to_int(_get_first(raw, "minInstalls", "min_installs"))
    if min_installs is None:
        min_installs, _ = parse_installs(_to_text(_get_first(raw, "installs")))
    return AppSummary(
        app_id=app_id or "",
        title=_to_text(_get_first(raw, "title")),
        developer=_to_text(_get_first(raw, "developer")),
        developer_id=_to_text(_get_first(raw, "developerId", "developer_id")),
        category=_to_text(_get_first(raw, "genre", "category")),
        rating=_to_float(_get_first(raw, "score", "rating")),
        ratings_count=_to_int(_get_first(raw, "ratings", "ratings_count")),
        reviews_count=_to_int(_get_first(raw, "reviews", "reviews_count")),
        installs=_to_text(_get_first(raw, "installs")),
        min_installs=min_installs,
        price=_format_price(raw),
        free=_to_bool(_get_first(raw, "free")),
        has_iap=_to_bool(_get_first(raw, "offersIAP", "has_iap")),
        icon_url=_to_text(_get_first(raw, "icon", "icon_url")),
        store_url=_to_text(_get_first(raw, "url", "store_url")),
        raw=_json_safe(raw),
    )


def normalize_app_detail(raw: dict) -> AppDetail:
    summary = normalize_app_summary(raw)
    return AppDetail(
        **summary.model_dump(),
        version=_to_text(_get_first(raw, "version")),
        updated=_to_date_text(_get_first(raw, "lastUpdatedOn", "updated")),
        released=_to_date_text(_get_first(raw, "released")),
        android_version=_to_text(_get_first(raw, "androidVersion", "android_version")),
        content_rating=_to_text(_get_first(raw, "contentRating", "content_rating")),
        description=_to_text(_get_first(raw, "description")),
        summary=_to_text(_get_first(raw, "summary")),
        changelog=_to_text(_get_first(raw, "recentChanges", "changelog")),
        screenshots=_normalize_string_list(_get_first(raw, "screenshots")),
        real_installs=_to_int(_get_first(raw, "realInstalls", "real_installs")),
        histogram=_normalize_int_list(_get_first(raw, "histogram")),
        contains_ads=_to_bool(_get_first(raw, "containsAds", "adSupported", "contains_ads")),
        iap_price_range=_to_text(_get_first(raw, "inAppProductPrice", "iap_price_range")),
        developer_email=_to_text(_get_first(raw, "developerEmail", "developer_email")),
        developer_website=_to_text(_get_first(raw, "developerWebsite", "developer_website")),
        privacy_policy=_to_text(_get_first(raw, "privacyPolicy", "privacy_policy")),
        header_image=_to_text(_get_first(raw, "headerImage", "header_image")),
    )


def normalize_review(raw: dict, app_id: str) -> ReviewItem:
    return ReviewItem(
        app_id=app_id,
        review_id=_to_text(_get_first(raw, "reviewId", "review_id", "id")),
        user_name=_to_text(_get_first(raw, "userName", "user_name")),
        rating=_to_int(_get_first(raw, "score", "rating")),
        content=_to_text(_get_first(raw, "content", "text")),
        app_version=_to_text(
            _get_first(raw, "appVersion", "reviewCreatedVersion", "app_version", "version")
        ),
        helpful_count=_to_int(_get_first(raw, "thumbsUpCount", "helpful_count")),
        review_created_at=_to_text(_get_first(raw, "at", "reviewCreatedAt", "review_created_at")),
        raw=_json_safe(raw),
    )


def normalize_chart_item(
    raw: dict,
    rank: int,
    chart_type: str,
    country: str,
    lang: str,
) -> ChartItem:
    summary = normalize_app_summary(raw)
    payload = summary.model_dump()
    payload["category"] = _to_text(_get_first(raw, "category", "genre"))
    return ChartItem(
        **payload,
        rank=rank,
        chart_type=chart_type,
        country=country,
        lang=lang,
    )


def _get_first(raw: dict, *keys: str) -> Any:
    for key in keys:
        if key in raw and raw[key] not in ("", []):
            return raw[key]
    return None


def _to_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _to_date_text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value).date().isoformat()
        except (OSError, OverflowError, ValueError):
            return str(value)
    if isinstance(value, str):
        normalized = value.strip()
        if normalized.isdigit():
            try:
                return datetime.fromtimestamp(int(normalized)).date().isoformat()
            except (OSError, OverflowError, ValueError):
                return normalized
        return normalized
    return str(value)


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        normalized = value.replace(",", "").strip()
        if not normalized:
            return None
        try:
            return int(float(normalized))
        except ValueError:
            return None
    return None


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        normalized = value.replace(",", "").strip()
        if not normalized:
            return None
        try:
            return float(normalized)
        except ValueError:
            return None
    return None


def _to_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    return None


def _normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return []


def _normalize_int_list(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        number = _to_int(item)
        if number is not None:
            result.append(number)
    return result


def _format_price(raw: dict) -> str | None:
    free = _to_bool(_get_first(raw, "free"))
    if free:
        return "Free"
    price = _get_first(raw, "price")
    currency = _to_text(_get_first(raw, "currency"))
    if price in (None, ""):
        return None
    if isinstance(price, str):
        return price
    if isinstance(price, (int, float)):
        if currency:
            return f"{currency} {price}"
        return str(price)
    return _to_text(price)


def _json_safe(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    return {}
