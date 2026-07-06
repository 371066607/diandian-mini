from __future__ import annotations

from typing import Any

from app.ui.formatting import alert_row, fmt_count, fmt_size, review_row, yes_no
from app.utils.time_utils import now_iso


def has_app_detail_data(item) -> bool:
    if item is None or not getattr(item, "app_id", ""):
        return False
    fields = ("title", "summary", "store_url", "icon_url", "description")
    return any(getattr(item, field, None) not in (None, "", [], {}) for field in fields)


def has_complete_app_detail_data(item) -> bool:
    if item is None or not getattr(item, "app_id", ""):
        return False
    fields = (
        "developer",
        "developer_id",
        "developer_email",
        "developer_website",
        "privacy_policy",
        "rating",
        "ratings_count",
        "reviews_count",
        "installs",
        "min_installs",
        "real_installs",
        "version",
        "updated",
        "released",
        "content_rating",
        "screenshots",
        "histogram",
        "contains_ads",
        "has_iap",
    )
    return any(getattr(item, field, None) not in (None, "", [], {}) for field in fields)


def dev_links(item, is_ios: bool) -> list[dict[str, str]]:
    links = [
        {"label": "官网", "text": item.developer_website or "", "url": item.developer_website or ""},
    ]
    if not is_ios:
        links.insert(
            0,
            {
                "label": "邮箱",
                "text": item.developer_email or "",
                "url": f"mailto:{item.developer_email}" if item.developer_email else "",
            },
        )
        links.append(
            {"label": "隐私政策", "text": item.privacy_policy or "", "url": item.privacy_policy or ""}
        )
    return links


def dev_plain(item, is_ios: bool) -> list[dict[str, str]]:
    if is_ios:
        return [
            {"label": "卖家", "value": item.developer_address or "-"},
            {"label": "发布国", "value": item.publisher_country or "-"},
        ]
    return [
        {"label": "地址", "value": item.developer_address or "-"},
        {"label": "电话", "value": item.developer_phone or "-"},
        {"label": "发布国", "value": item.publisher_country or "-"},
    ]


def more_info(item, is_ios: bool) -> list[dict[str, Any]]:
    if is_ios:
        return [
            {"label": "App ID", "value": item.app_id},
            {"label": "Bundle ID", "value": item.app_bundle or "-"},
            {"label": "类目 ID", "value": item.genre_id or "-"},
            {"label": "开发者 ID", "value": item.developer_id or "-"},
            {"label": "货币", "value": item.currency or "-"},
            {"label": "全部类目", "value": "、".join(item.categories) if item.categories else "-"},
        ]
    return [
        {"label": "应用包", "value": item.app_bundle or "-"},
        {"label": "类目 ID", "value": item.genre_id or "-"},
        {"label": "开发者 ID", "value": item.developer_id or "-"},
        {"label": "货币", "value": item.currency or "-"},
        {"label": "最低日均安装", "value": fmt_count(item.min_daily_installs)},
        {"label": "最低月均安装", "value": fmt_count(item.min_monthly_installs)},
        {"label": "预告片", "value": "观看", "url": item.video or ""},
        {"label": "头图", "value": "查看", "url": item.header_image or ""},
    ]


def metrics_app_store(item) -> list[dict[str, Any]]:
    """iOS-native chip set — iTunes lookup has no install counts / Android fields,
    but does carry size, min OS, device & language coverage and per-version rating."""
    raw = getattr(item, "raw", None) or {}
    current_rating = raw.get("averageUserRatingForCurrentVersion")
    devices = raw.get("supportedDevices") or []
    languages = raw.get("languageCodesISO2A") or []
    return [
        {
            "label": "评分",
            "value": f"{getattr(item, 'rating'):.2f}" if getattr(item, "rating", None) else "-",
            "accent": "blue",
        },
        {"label": "评分数", "value": fmt_count(getattr(item, "ratings_count", None))},
        {"label": "当前版本评分", "value": f"{current_rating:.2f}" if current_rating else "-"},
        {
            "label": "当前版本评分数",
            "value": fmt_count(raw.get("userRatingCountForCurrentVersion")),
        },
        {"label": "价格", "value": item.price or ("免费" if item.free else "-"), "accent": "blue"},
        {"label": "内购", "value": yes_no(item.has_iap)},
        {"label": "大小", "value": fmt_size(raw.get("fileSizeBytes"))},
        {
            "label": "最低系统",
            "value": f"iOS {raw['minimumOsVersion']}+" if raw.get("minimumOsVersion") else "-",
        },
        {"label": "支持设备", "value": f"{len(devices)} 种" if devices else "-"},
        {"label": "支持语言", "value": f"{len(languages)} 种" if languages else "-"},
        {"label": "版本", "value": item.version or "-"},
        {"label": "发布日期", "value": item.released or "-"},
        {"label": "最近更新", "value": item.updated or "-"},
        {"label": "上线天数", "value": f"{item.app_age_days:,} 天" if item.app_age_days else "-"},
        {"label": "内容分级", "value": item.content_rating or "-"},
        {"label": "可下载", "value": yes_no(item.available)},
    ]


def metrics(item) -> list[dict[str, Any]]:
    if getattr(item, "platform", "google_play") == "app_store":
        return metrics_app_store(item)
    daily = getattr(item, "real_daily_installs", None) or getattr(item, "daily_installs", None)
    monthly = getattr(item, "real_monthly_installs", None) or getattr(item, "monthly_installs", None)
    ads = (
        getattr(item, "contains_ads", None)
        if getattr(item, "contains_ads", None) is not None
        else getattr(item, "ad_supported", None)
    )
    min_api = getattr(item, "min_android_api", None)
    max_api = getattr(item, "max_android_api", None)
    if min_api and max_api:
        api_text = f"{min_api} ~ {max_api}"
    elif min_api:
        api_text = f"{min_api}+"
    else:
        api_text = "-"
    original_price = getattr(item, "original_price", None)
    currency = getattr(item, "currency", "")
    if original_price:
        original = f"{currency} {original_price:.2f}" if currency else f"{original_price:.2f}"
    else:
        original = "-"
    return [
        {
            "label": "评分",
            "value": f"{getattr(item, 'rating'):.2f}" if getattr(item, "rating", None) else "-",
            "accent": "blue",
        },
        {"label": "评分数", "value": fmt_count(getattr(item, "ratings_count", None))},
        {"label": "评论数", "value": fmt_count(getattr(item, "reviews_count", None))},
        {"label": "安装量", "value": getattr(item, "installs", "") or "-", "accent": "blue"},
        {"label": "最低安装", "value": fmt_count(getattr(item, "min_installs", None))},
        {
            "label": "真实安装",
            "value": fmt_count(getattr(item, "real_installs", None)),
            "accent": "blue",
        },
        {"label": "日均安装", "value": fmt_count(daily)},
        {"label": "月均安装", "value": fmt_count(monthly)},
        {
            "label": "上线天数",
            "value": f"{getattr(item, 'app_age_days'):,} 天"
            if getattr(item, "app_age_days", None)
            else "-",
        },
        {"label": "发布日期", "value": getattr(item, "released", "") or "-"},
        {"label": "最近更新", "value": getattr(item, "updated", "") or "-"},
        {"label": "版本", "value": getattr(item, "version", "") or "-"},
        {"label": "Android 版本", "value": getattr(item, "android_version", "") or "-"},
        {"label": "Android API", "value": api_text},
        {"label": "内容分级", "value": getattr(item, "content_rating", "") or "-"},
        {
            "label": "价格",
            "value": getattr(item, "price", "") or ("免费" if getattr(item, "free", False) else "-"),
        },
        {"label": "原价", "value": original},
        {"label": "促销", "value": yes_no(getattr(item, "sale", None))},
        {"label": "内购", "value": yes_no(getattr(item, "has_iap", None))},
        {"label": "内购价", "value": getattr(item, "iap_price_range", "") or "-"},
        {"label": "含广告", "value": yes_no(ads)},
        {"label": "可下载", "value": yes_no(getattr(item, "available", None))},
    ]


class DetailController:
    """Domain logic for fetching an app's detail page and its async "extras"
    (history/alerts/recent-reviews/similar-apps), shared between API mode and
    legacy/offline mode. Needs a reference to the bridge for the shared
    _store_intel_api/_request_api_refresh/_active_store helpers and for
    services/logger. QmlBridge owns the Slot surface, async dispatch (_run),
    detail state (_detail/_detail_item/_detail_gen), and signal emission.
    """

    def __init__(self, bridge) -> None:
        self.bridge = bridge

    def fetch(self, app_id: str, ctx: dict[str, str], platform: str, request_id: int) -> dict[str, Any]:
        api = self.bridge._store_intel_api()
        if api is None:
            store = self.bridge._active_store()
            return {
                "detail": store.app_detail(app_id, country=ctx["country"], lang=ctx["lang"]),
                "queued": False,
                "request_id": request_id,
            }
        try:
            cached = api.cached_app_detail(
                app_id, country=ctx["country"], lang=ctx["lang"], platform=platform
            )
        except Exception:
            self.bridge._request_api_refresh(
                api, "app", app_id=app_id, country=ctx["country"], lang=ctx["lang"], platform=platform
            )
            cached = api.cached_app_detail(
                app_id, country=ctx["country"], lang=ctx["lang"], platform=platform
            )
        if not has_app_detail_data(cached):
            raise RuntimeError("服务器没有返回可用的应用详情数据。")
        if not has_complete_app_detail_data(cached):
            self.bridge._request_api_refresh(
                api, "app", app_id=app_id, country=ctx["country"], lang=ctx["lang"], platform=platform
            )
            try:
                refreshed = api.cached_app_detail(
                    app_id, country=ctx["country"], lang=ctx["lang"], platform=platform
                )
                if has_app_detail_data(refreshed):
                    cached = refreshed
            except Exception:
                pass
        return {
            "detail": cached,
            "queued": False,
            "partial": not has_complete_app_detail_data(cached),
            "request_id": request_id,
        }

    def list_cached_reviews(
        self, api, app_id: str, country: str, lang: str, limit: int, platform: str = "google_play"
    ):
        items = api.list_cached_reviews(app_id, limit=limit, platform=platform)
        if items:
            return items
        self.bridge._request_api_refresh(
            api, "reviews", app_id=app_id, country=country, lang=lang, limit=limit, platform=platform
        )
        return api.list_cached_reviews(app_id, limit=limit, platform=platform)

    def collect_extras(self, item) -> dict[str, Any]:
        ctx = self.bridge._detail_context or {"country": "us", "lang": "en"}
        platform = getattr(item, "platform", "google_play") or "google_play"
        api = self.bridge._store_intel_api(platform)
        services = self.bridge.services

        def load_optional(section: str, fn):
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001 - optional blocks must not hide the main detail
                self.bridge.logger.warning(
                    "detail %s load failed for %s: %s", section, item.app_id, exc
                )
                return []

        if api is not None:
            history = load_optional(
                "history",
                lambda: api.list_app_snapshots(
                    item.app_id, country=ctx["country"], lang=ctx["lang"], limit=80, platform=platform
                ),
            )
            alerts = load_optional(
                "alerts", lambda: api.list_alerts(app_id=item.app_id, limit=8, platform=platform)
            )
            reviews = load_optional(
                "reviews",
                lambda: self.list_cached_reviews(
                    api, item.app_id, country=ctx["country"], lang=ctx["lang"], limit=10, platform=platform
                ),
            )
        else:
            history = load_optional(
                "history",
                lambda: services["tracking_service"].get_history(
                    item.app_id, country=ctx["country"], lang=ctx["lang"]
                ),
            )
            alerts = load_optional(
                "alerts", lambda: services["alert_service"].list_alerts(app_id=item.app_id, limit=8)
            )
            reviews = []
            review_service = services.get("review_service")
            if review_service is not None:
                reviews = load_optional("reviews", lambda: review_service.list_cached(item.app_id, limit=10))
        labels = [(getattr(snap, "captured_at", "") or "")[5:10] for snap in history]
        rating_values = [getattr(snap, "rating", None) or 0 for snap in history]
        reviews_values = [getattr(snap, "reviews_count", None) or 0 for snap in history]
        installs_values = [
            getattr(snap, "real_installs", None) or getattr(snap, "min_installs", None) or 0
            for snap in history
        ]
        # Keep an existing trend current by appending today's freshly-fetched
        # values — but never fabricate a one-point "trend" when there is no
        # snapshot history at all (the SparkLine then shows its empty state).
        today = now_iso()[5:10]
        if labels and labels[-1] != today:
            labels.append(today)
            rating_values.append(getattr(item, "rating", None) or 0)
            reviews_values.append(getattr(item, "reviews_count", None) or 0)
            installs_values.append(
                getattr(item, "real_installs", None) or getattr(item, "min_installs", None) or 0
            )
        return {
            "historyLabels": labels,
            "ratingValues": rating_values,
            "reviewsValues": reviews_values,
            "installsValues": installs_values,
            "recentAlerts": [alert_row(alert) for alert in alerts],
            "recentReviews": [review_row(r) for r in reviews],
        }
