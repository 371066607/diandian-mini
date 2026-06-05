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
    rating = _to_float(_get_first(raw, "score", "rating"))
    score_text = _to_text(_get_first(raw, "scoreText", "score_text"))
    if not score_text and rating is not None:
        score_text = f"{rating:.1f}"  # the lib omits scoreText for search; derive it
    return AppSummary(
        app_id=app_id or "",
        title=_to_text(_get_first(raw, "title")),
        developer=_to_text(_get_first(raw, "developer")),
        developer_id=_to_text(_get_first(raw, "developerId", "developer_id")),
        category=_to_text(_get_first(raw, "genre", "category")),
        summary=_to_text(_get_first(raw, "summary")),
        rating=rating,
        score_text=score_text,
        ratings_count=_to_int(_get_first(raw, "ratings", "ratings_count")),
        reviews_count=_to_int(_get_first(raw, "reviews", "reviews_count")),
        installs=_to_text(_get_first(raw, "installs")),
        min_installs=min_installs,
        price=_format_price(raw),
        currency=_to_text(_get_first(raw, "currency")),
        free=_to_bool(_get_first(raw, "free")),
        has_iap=_to_bool(_get_first(raw, "offersIAP", "has_iap")),
        icon_url=_to_text(_get_first(raw, "icon", "icon_url")),
        store_url=_to_text(_get_first(raw, "url", "appUrl", "store_url")),
        raw=_json_safe(raw),
    )


def normalize_app_detail(raw: dict) -> AppDetail:
    summary = normalize_app_summary(raw)
    real_installs = _to_int(_get_first(raw, "realInstalls", "real_installs"))
    min_installs = _to_int(_get_first(raw, "minInstalls", "min_installs"))
    # Prefer the pre-computed value from gplay_scraper; derive as fallback for google_play_scraper.
    age_days = _to_int(_get_first(raw, "appAgeDays")) if "appAgeDays" in raw else _app_age_days(_get_first(raw, "released"))

    # 6 install-period fields — gplay_scraper provides all of them directly.
    # For google_play_scraper (which only has realInstalls/minInstalls) we derive.
    real_daily = _to_int(_get_first(raw, "realDailyInstalls"))
    min_daily = _to_int(_get_first(raw, "minDailyInstalls"))
    real_monthly = _to_int(_get_first(raw, "realMonthlyInstalls"))
    min_monthly = _to_int(_get_first(raw, "minMonthlyInstalls"))
    if real_daily is None:
        real_daily, _rm = _per_period_installs(None, real_installs, age_days)
        if real_monthly is None:
            real_monthly = _rm
    if min_daily is None:
        min_daily, _mm = _per_period_installs(None, min_installs, age_days)
        if min_monthly is None:
            min_monthly = _mm
    daily_installs = _to_int(_get_first(raw, "dailyInstalls"))
    if daily_installs is None:
        daily_installs = real_daily
    monthly_installs = _to_int(_get_first(raw, "monthlyInstalls"))
    if monthly_installs is None:
        monthly_installs = real_monthly

    return AppDetail(
        **summary.model_dump(),
        version=_to_text(_get_first(raw, "version")),
        updated=_to_date_text(_get_first(raw, "lastUpdatedOn", "lastUpdated", "updated")),
        released=_to_date_text(_get_first(raw, "released")),
        android_version=_to_text(_get_first(raw, "androidVersion", "android_version")),
        content_rating=_to_text(_get_first(raw, "contentRating", "content_rating")),
        description=_to_text(_get_first(raw, "description")),
        # ``summary`` now lives on AppSummary and is already in ``model_dump()`` above.
        changelog=_to_text(_get_first(raw, "recentChanges", "whatsNew", "changelog")),
        screenshots=_normalize_string_list(_get_first(raw, "screenshots")),
        real_installs=real_installs,
        histogram=_normalize_int_list(_get_first(raw, "histogram")),
        contains_ads=_to_bool(_get_first(raw, "containsAds", "contains_ads")),
        iap_price_range=_to_text(_get_first(raw, "inAppProductPrice", "iap_price_range")),
        developer_email=_to_text(_get_first(raw, "developerEmail", "developer_email")),
        developer_website=_to_text(_get_first(raw, "developerWebsite", "developer_website")),
        privacy_policy=_to_text(_get_first(raw, "privacyPolicy", "privacy_policy")),
        header_image=_to_text(_get_first(raw, "headerImage", "header_image")),
        # --- Extended app_analyze fields ---
        genre_id=_to_text(_get_first(raw, "genreId", "genre_id")),
        categories=_normalize_categories(_get_first(raw, "categories")),
        available=_to_bool(_get_first(raw, "available")) if "available" in raw else True,
        app_age_days=age_days,
        video=_to_text(_get_first(raw, "video")),
        video_image=_to_text(_get_first(raw, "videoImage", "video_image")),
        daily_installs=daily_installs,
        min_daily_installs=min_daily,
        real_daily_installs=real_daily,
        monthly_installs=monthly_installs,
        min_monthly_installs=min_monthly,
        real_monthly_installs=real_monthly,
        ad_supported=_to_bool(_get_first(raw, "adSupported", "ad_supported")),
        max_android_api=_to_int(_get_first(raw, "maxAndroidApi", "max_android_api")),
        min_android_api=_to_int(_get_first(raw, "minAndroidApi", "min_android_api")),
        app_bundle=_to_text(_get_first(raw, "appBundle", "app_bundle"))
        or (summary.app_id or None),
        content_rating_description=_to_text(
            _get_first(raw, "contentRatingDescription", "content_rating_description")
        ),
        permissions=_as_mapping(_get_first(raw, "permissions")),
        data_safety=_as_list(_get_first(raw, "dataSafety", "data_safety")),
        sale=_to_bool(_get_first(raw, "sale")),
        original_price=_to_float(_get_first(raw, "originalPrice", "original_price")),
        developer_address=_to_text(_get_first(raw, "developerAddress", "developer_address")),
        developer_phone=_to_text(_get_first(raw, "developerPhone", "developer_phone")),
        publisher_country=_to_text(_get_first(raw, "publisherCountry", "publisher_country")),
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


def _normalize_categories(value: Any) -> list[str]:
    """Flatten the scraper's ``[{name, id}, ...]`` category list to display names."""
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        if isinstance(item, dict):
            name = item.get("name") or item.get("id")
            if name:
                names.append(str(name))
        elif item:
            names.append(str(item))
    return names


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _app_age_days(released: Any) -> int | None:
    """Days since release, parsed from the scraper's date string (e.g. ``Oct 18, 2010``)."""
    if released in (None, ""):
        return None
    text = str(released).strip()
    parsed: datetime | None = None
    if text.isdigit():
        try:
            parsed = datetime.fromtimestamp(int(text))
        except (OSError, OverflowError, ValueError):
            parsed = None
    if parsed is None:
        for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    delta = (datetime.now() - parsed).days
    return delta if delta >= 0 else None


def _per_period_installs(
    explicit_daily: int | None, total: int | None, age_days: int | None
) -> tuple[int | None, int | None]:
    """Return ``(daily, monthly)`` installs, preferring an explicit value, else averaging
    total installs over the app's age (mirrors gplay-scraper's derived metrics)."""
    if explicit_daily is not None:
        return explicit_daily, explicit_daily * 30
    if not total or not age_days or age_days <= 0:
        return None, None
    daily = round(total / age_days)
    return daily, daily * 30


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
