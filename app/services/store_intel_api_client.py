from __future__ import annotations

import json
import time
from types import SimpleNamespace
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from pydantic import BaseModel

from app.schemas.app_schema import AppDetail, AppSummary
from app.schemas.chart_schema import ChartItem
from app.schemas.keyword_schema import KeywordRankResult
from app.schemas.review_schema import ReviewItem


DEFAULT_USER_AGENT = "CatchRadar/desktop"


class StoreIntelApiError(RuntimeError):
    pass


class StoreIntelApiClient:
    """Small stdlib HTTP client for the Go StoreIntel API.

    It deliberately mirrors the existing Python service method shapes where the QML
    bridge already depends on them, so the frontend can switch one call at a time.
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 30.0,
        log_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.base_url = (base_url or "").strip().rstrip("/")
        self.timeout = timeout
        self.log_sink = log_sink

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)

    def search(
        self,
        keyword: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 50,
    ) -> list[AppSummary]:
        data = self._request(
            "GET",
            "/api/store-intel/apps/search",
            query={"query": keyword, "country": country, "lang": lang, "limit": limit},
        )
        return [AppSummary(**item) for item in self._items(data)]

    def search_cached(
        self,
        keyword: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 50,
    ) -> list[AppSummary]:
        data = self._request(
            "GET",
            "/api/store-intel/apps/search/cache",
            query={"query": keyword, "country": country, "lang": lang, "limit": limit},
        )
        return [AppSummary(**item) for item in self._items(data)]

    def app_detail(self, app_id: str, country: str = "us", lang: str = "en") -> AppDetail:
        data = self._request(
            "GET",
            f"/api/store-intel/apps/{quote(app_id, safe='')}",
            query={"country": country, "lang": lang},
        )
        return AppDetail(**data)

    def cached_app_detail(self, app_id: str, country: str = "us", lang: str = "en") -> AppDetail:
        data = self._request(
            "GET",
            f"/api/store-intel/apps/{quote(app_id, safe='')}/cache",
            query={"country": country, "lang": lang},
        )
        if (data or {}).get("cached") is False or not (data or {}).get("detail"):
            raise StoreIntelApiError("暂无应用详情缓存。")
        return AppDetail(**(data.get("detail") or {}))

    def similar_apps(
        self,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 10,
    ) -> list[AppSummary]:
        data = self._request(
            "GET",
            f"/api/store-intel/apps/{quote(app_id, safe='')}/similar",
            query={"country": country, "lang": lang, "limit": limit},
        )
        return [AppSummary(**item) for item in self._items(data)]

    def permissions(
        self,
        app_id: str,
        country: str = "us",
        lang: str = "en",
    ) -> dict[str, list[str]]:
        data = self._request(
            "GET",
            f"/api/store-intel/apps/{quote(app_id, safe='')}/permissions",
            query={"country": country, "lang": lang},
        )
        groups = data.get("groups") or {}
        return {
            str(group): [str(item) for item in (items or [])] for group, items in groups.items()
        }

    def reviews(
        self,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        sort: str = "newest",
        continuation_token=None,
        limit: int = 20,
    ) -> tuple[list[ReviewItem], object]:
        query: dict[str, Any] = {
            "country": country,
            "lang": lang,
            "sort": sort,
            "limit": limit,
        }
        if continuation_token:
            query["continuation_token"] = str(continuation_token)
        data = self._request(
            "GET",
            f"/api/store-intel/apps/{quote(app_id, safe='')}/reviews",
            query=query,
        )
        return [ReviewItem(**item) for item in self._items(data)], data.get("next_token")

    def save_reviews(
        self,
        app_id: str,
        country: str,
        lang: str,
        items: list[ReviewItem],
    ) -> int:
        data = self._request(
            "POST",
            f"/api/store-intel/apps/{quote(app_id, safe='')}/reviews",
            body={
                "country": country,
                "lang": lang,
                "items": [self._to_jsonable(item) for item in items],
            },
        )
        return int(data.get("saved") or 0)

    def list_cached_reviews(self, app_id: str, limit: int = 10) -> list[ReviewItem]:
        data = self._request(
            "GET",
            f"/api/store-intel/apps/{quote(app_id, safe='')}/reviews/cache",
            query={"limit": limit},
        )
        return [ReviewItem(**item) for item in self._items(data)]

    def fetch_chart(
        self,
        chart_type: str,
        category: str | None,
        country: str,
        lang: str,
        limit: int,
    ) -> list[ChartItem]:
        data = self._request(
            "GET",
            "/api/store-intel/charts",
            query={
                "chart_type": chart_type,
                "category": category or "",
                "country": country,
                "lang": lang,
                "limit": limit,
            },
        )
        return [ChartItem(**item) for item in self._items(data)]

    def fetch_chart_cached(
        self,
        chart_type: str,
        category: str | None,
        country: str,
        lang: str,
        limit: int,
    ) -> list[ChartItem]:
        data = self._request(
            "GET",
            "/api/store-intel/charts/cache",
            query={
                "chart_type": chart_type,
                "category": category or "",
                "country": country,
                "lang": lang,
                "limit": limit,
            },
        )
        return [ChartItem(**item) for item in self._items(data)]

    def save_chart_snapshot(
        self,
        chart_type: str,
        category: str | None,
        country: str,
        lang: str,
        items: list[ChartItem],
    ) -> int:
        data = self._request(
            "POST",
            "/api/store-intel/charts/snapshot",
            body={
                "chart_type": chart_type,
                "category": category or "",
                "country": country,
                "lang": lang,
                "items": [self._to_jsonable(item) for item in items],
            },
        )
        return int(data.get("saved") or 0)

    def list_app_snapshots(
        self,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 80,
    ) -> list[SimpleNamespace]:
        data = self._request(
            "GET",
            "/api/store-intel/app-snapshots/history",
            query={"app_id": app_id, "country": country, "lang": lang, "limit": limit},
        )
        return [self._namespace(item) for item in self._items(data)]

    def list_recent_app_snapshots(self, limit: int = 8) -> list[SimpleNamespace]:
        data = self._request(
            "GET",
            "/api/store-intel/app-snapshots/recent",
            query={"limit": limit},
        )
        return [self._namespace(item) for item in self._items(data)]

    def count_app_snapshots(self) -> int:
        data = self._request("GET", "/api/store-intel/app-snapshots/count")
        return int(data.get("total") or 0)

    def rank_keyword(
        self,
        keyword: str,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 100,
    ) -> KeywordRankResult:
        data = self._request(
            "POST",
            "/api/store-intel/keyword-rank",
            body={
                "keyword": keyword,
                "app_id": app_id,
                "country": country,
                "lang": lang,
                "limit": limit,
            },
        )
        return KeywordRankResult(**data)

    def cached_keyword_rank(
        self,
        keyword: str,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 100,
    ) -> KeywordRankResult | None:
        history = self.list_keyword_rank_history(keyword, app_id, country, lang, limit=1)
        if not history:
            return None
        item = history[-1]
        results = []
        for raw in getattr(item, "results", []) or []:
            try:
                if isinstance(raw, AppSummary):
                    results.append(raw)
                elif isinstance(raw, dict):
                    results.append(AppSummary(**raw))
                else:
                    results.append(AppSummary(**vars(raw)))
            except (TypeError, ValueError):
                continue
        checked_limit = int(getattr(item, "checked_limit", 0) or 0)
        requested_limit = int(getattr(item, "requested_limit", 0) or checked_limit)
        returned_count = int(getattr(item, "returned_count", 0) or checked_limit or len(results))
        return KeywordRankResult(
            platform=getattr(item, "platform", "google_play"),
            keyword=getattr(item, "keyword", keyword),
            app_id=getattr(item, "app_id", app_id),
            country=getattr(item, "country", country),
            lang=getattr(item, "lang", lang),
            found=bool(getattr(item, "found", False)),
            rank=getattr(item, "rank", None),
            checked_limit=checked_limit,
            requested_limit=requested_limit,
            returned_count=returned_count,
            coverage_complete=bool(getattr(item, "coverage_complete", True)),
            captured_at=getattr(item, "captured_at", ""),
            results=results,
        )

    def analyze_coverage(
        self,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 50,
        deep: bool = False,
        candidates: list[str] | None = None,
        canonical_app_id: str | None = None,
    ) -> SimpleNamespace:
        data = self._request(
            "POST",
            "/api/store-intel/keyword-coverage",
            body={
                "app_id": app_id,
                "country": country,
                "lang": lang,
                "limit": limit,
                "deep": deep,
                "candidates": candidates or [],
                "canonical_app_id": canonical_app_id or "",
            },
        )
        return self._namespace(data)

    def cached_coverage(
        self,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        deep: bool = False,
    ) -> SimpleNamespace:
        data = self._request(
            "GET",
            "/api/store-intel/keyword-coverage/cache",
            query={
                "app_id": app_id,
                "country": country,
                "lang": lang,
                "deep": str(deep).lower(),
            },
            timeout=min(self.timeout, 5.0),
        )
        return self._namespace(data)

    def analyze_coverage_stream(
        self,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 50,
        deep: bool = False,
        candidates: list[str] | None = None,
        canonical_app_id: str | None = None,
        progress: Callable[[str, float], None] | None = None,
    ) -> SimpleNamespace:
        result = None
        for event in self._stream_request(
            "POST",
            "/api/store-intel/keyword-coverage/stream",
            body={
                "app_id": app_id,
                "country": country,
                "lang": lang,
                "limit": limit,
                "deep": deep,
                "candidates": candidates or [],
                "canonical_app_id": canonical_app_id or "",
            },
            timeout=max(self.timeout, 180.0 if deep else 90.0),
        ):
            event_type = str(event.get("type") or "")
            if event_type == "progress":
                if progress is not None:
                    progress(str(event.get("message") or ""), float(event.get("fraction") or 0.0))
            elif event_type == "result":
                result = self._namespace(event.get("data") or {})
            elif event_type == "error":
                raise StoreIntelApiError(str(event.get("message") or "覆盖词分析失败。"))
        if result is None:
            raise StoreIntelApiError("StoreIntel API 未返回覆盖词分析结果。")
        return result

    def get_settings(self) -> dict[str, str]:
        data = self._request("GET", "/api/store-intel/settings")
        return {str(key): str(value) for key, value in (data or {}).items()}

    def set_settings(self, values: dict[str, str]) -> dict[str, str]:
        data = self._request("POST", "/api/store-intel/settings", body=values)
        return {str(key): str(value) for key, value in (data or {}).items()}

    def list_tracked_apps(self, enabled: bool | None = None) -> list[SimpleNamespace]:
        data = self._request(
            "GET",
            "/api/store-intel/tracking/apps",
            query={} if enabled is None else {"enabled": str(enabled).lower()},
        )
        return [self._namespace(item) for item in self._items(data)]

    def list_tracked_keywords(self, enabled: bool | None = None) -> list[SimpleNamespace]:
        data = self._request(
            "GET",
            "/api/store-intel/tracking/keywords",
            query={} if enabled is None else {"enabled": str(enabled).lower()},
        )
        return [self._namespace(item) for item in self._items(data)]

    def list_tracked_chart_apps(self, enabled: bool | None = None) -> list[SimpleNamespace]:
        data = self._request(
            "GET",
            "/api/store-intel/tracking/chart-apps",
            query={} if enabled is None else {"enabled": str(enabled).lower()},
        )
        return [self._namespace(item) for item in self._items(data)]

    def add_tracked_app(
        self,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        frequency: str = "daily",
        tag: str = "",
    ) -> SimpleNamespace:
        data = self._request(
            "POST",
            "/api/store-intel/tracking/apps",
            body={
                "app_id": app_id,
                "country": country,
                "lang": lang,
                "frequency": frequency,
                "tag": tag,
            },
        )
        return self._namespace(data)

    def add_tracked_keyword(
        self,
        keyword: str,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        platform: str = "google_play",
    ) -> SimpleNamespace:
        data = self._request(
            "POST",
            "/api/store-intel/tracking/keywords",
            body={
                "keyword": keyword,
                "app_id": app_id,
                "country": country,
                "lang": lang,
                "platform": platform,
            },
        )
        return self._namespace(data)

    def add_tracked_chart_app(
        self,
        app_id: str,
        collection: str,
        category: str | None = "APPLICATION",
        country: str = "us",
        lang: str = "en",
        frequency: str = "daily",
    ) -> SimpleNamespace:
        data = self._request(
            "POST",
            "/api/store-intel/tracking/chart-apps",
            body={
                "app_id": app_id,
                "collection": collection,
                "category": category or "",
                "country": country,
                "lang": lang,
                "frequency": frequency,
            },
        )
        return self._namespace(data)

    def remove_tracked_app(self, app_id: str, country: str = "us", lang: str = "en") -> int:
        data = self._request(
            "POST",
            "/api/store-intel/tracking/apps/remove",
            body={"app_id": app_id, "country": country, "lang": lang},
        )
        return int(data.get("updated") or 0)

    def set_tracked_app_enabled(
        self, app_id: str, enabled: bool, country: str = "us", lang: str = "en"
    ) -> SimpleNamespace:
        data = self._request(
            "POST",
            "/api/store-intel/tracking/apps/enabled",
            body={"app_id": app_id, "country": country, "lang": lang, "enabled": enabled},
        )
        return self._namespace(data)

    def set_tracked_app_frequency(
        self, app_id: str, frequency: str, country: str = "us", lang: str = "en"
    ) -> SimpleNamespace:
        data = self._request(
            "POST",
            "/api/store-intel/tracking/apps/frequency",
            body={"app_id": app_id, "country": country, "lang": lang, "frequency": frequency},
        )
        return self._namespace(data)

    def set_tracked_app_tag(
        self, app_id: str, tag: str, country: str = "us", lang: str = "en"
    ) -> SimpleNamespace:
        data = self._request(
            "POST",
            "/api/store-intel/tracking/apps/tag",
            body={"app_id": app_id, "country": country, "lang": lang, "tag": tag},
        )
        return self._namespace(data)

    def remove_tracked_keyword(
        self,
        keyword: str,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        platform: str = "google_play",
    ) -> int:
        data = self._request(
            "POST",
            "/api/store-intel/tracking/keywords/remove",
            body={
                "keyword": keyword,
                "app_id": app_id,
                "country": country,
                "lang": lang,
                "platform": platform,
            },
        )
        return int(data.get("updated") or 0)

    def set_tracked_keyword_enabled(
        self,
        keyword: str,
        app_id: str,
        enabled: bool,
        country: str = "us",
        lang: str = "en",
        platform: str = "google_play",
    ) -> SimpleNamespace:
        data = self._request(
            "POST",
            "/api/store-intel/tracking/keywords/enabled",
            body={
                "keyword": keyword,
                "app_id": app_id,
                "country": country,
                "lang": lang,
                "platform": platform,
                "enabled": enabled,
            },
        )
        return self._namespace(data)

    def set_tracked_keyword_frequency(
        self,
        keyword: str,
        app_id: str,
        frequency: str,
        country: str = "us",
        lang: str = "en",
        platform: str = "google_play",
    ) -> SimpleNamespace:
        data = self._request(
            "POST",
            "/api/store-intel/tracking/keywords/frequency",
            body={
                "keyword": keyword,
                "app_id": app_id,
                "country": country,
                "lang": lang,
                "platform": platform,
                "frequency": frequency,
            },
        )
        return self._namespace(data)

    def sync_tracked_keyword_now(
        self,
        keyword: str,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        platform: str = "google_play",
        limit: int = 100,
    ) -> KeywordRankResult:
        data = self._request(
            "POST",
            "/api/store-intel/tracking/keywords/sync",
            body={
                "keyword": keyword,
                "app_id": app_id,
                "country": country,
                "lang": lang,
                "platform": platform,
                "limit": limit,
            },
        )
        return KeywordRankResult(**(data.get("rank") or {}))

    def remove_tracked_chart_app(
        self,
        app_id: str,
        collection: str,
        category: str | None = "APPLICATION",
        country: str = "us",
        lang: str = "en",
    ) -> int:
        data = self._request(
            "POST",
            "/api/store-intel/tracking/chart-apps/remove",
            body={
                "app_id": app_id,
                "collection": collection,
                "category": category or "",
                "country": country,
                "lang": lang,
            },
        )
        return int(data.get("updated") or 0)

    def set_tracked_chart_app_enabled(
        self,
        app_id: str,
        collection: str,
        enabled: bool,
        category: str | None = "APPLICATION",
        country: str = "us",
        lang: str = "en",
    ) -> SimpleNamespace:
        data = self._request(
            "POST",
            "/api/store-intel/tracking/chart-apps/enabled",
            body={
                "app_id": app_id,
                "collection": collection,
                "category": category or "",
                "country": country,
                "lang": lang,
                "enabled": enabled,
            },
        )
        return self._namespace(data)

    def sync_tracked_chart_app_now(
        self,
        app_id: str,
        collection: str,
        category: str | None = "APPLICATION",
        country: str = "us",
        lang: str = "en",
        limit: int = 100,
    ) -> SimpleNamespace:
        data = self._request(
            "POST",
            "/api/store-intel/tracking/chart-apps/sync",
            body={
                "app_id": app_id,
                "collection": collection,
                "category": category or "",
                "country": country,
                "lang": lang,
                "limit": limit,
            },
        )
        return self._namespace(data.get("rank") or {})

    def sync_app_now(self, app_id: str, country: str = "us", lang: str = "en") -> AppDetail:
        data = self._request(
            "POST",
            "/api/store-intel/tracking/apps/sync",
            body={"app_id": app_id, "country": country, "lang": lang},
        )
        return AppDetail(**data.get("detail", {}))

    def sync_all(self, due_only: bool = False) -> dict[str, int]:
        data = self._request(
            "POST",
            "/api/store-intel/tracking/sync-all",
            body={"due_only": due_only},
        )
        return {
            "apps": int(data.get("apps_synced") or 0),
            "keywords": int(data.get("keywords_synced") or 0),
            "charts": int(data.get("charts_synced") or 0),
        }

    def request_refresh(self, kind: str, **kwargs) -> SimpleNamespace:
        body = {"kind": kind, **{key: value for key, value in kwargs.items() if value is not None}}
        if kind == "chart" and "chart_type" in body and "collection" not in body:
            body["collection"] = body.pop("chart_type")
        data = self._request("POST", "/api/store-intel/refresh-jobs", body=body)
        return self._namespace(data)

    def get_refresh_job(self, job_id: str) -> SimpleNamespace:
        data = self._request(
            "GET",
            f"/api/store-intel/refresh-jobs/{quote(str(job_id), safe='')}",
        )
        return self._namespace(data)

    def wait_refresh_job(
        self,
        job_id: str,
        *,
        timeout: float = 60.0,
        interval: float = 1.0,
    ) -> SimpleNamespace:
        deadline = time.monotonic() + max(0.0, timeout)
        last_job = self.get_refresh_job(job_id)
        while str(getattr(last_job, "status", "")).lower() not in {
            "completed",
            "failed",
        }:
            if time.monotonic() >= deadline:
                raise StoreIntelApiError(f"刷新任务超时：{job_id}")
            time.sleep(max(0.1, interval))
            last_job = self.get_refresh_job(job_id)
        return last_job

    def cleanup_history(self) -> dict[str, int]:
        data = self._request("POST", "/api/store-intel/history/cleanup", body={})
        return {
            "snapshots": int(data.get("snapshots") or 0),
            "keywords": int(data.get("keywords") or 0),
            "charts": int(data.get("charts") or 0),
            "alerts": int(data.get("alerts") or 0),
            "reviews": int(data.get("reviews") or 0),
        }

    def list_alerts(
        self,
        *,
        app_id: str = "",
        alert_type: str = "",
        severity: str = "",
        is_read: bool | None = None,
        limit: int = 200,
    ) -> list[SimpleNamespace]:
        query: dict[str, Any] = {
            "app_id": app_id,
            "type": alert_type,
            "severity": severity,
            "limit": limit,
        }
        if is_read is not None:
            query["is_read"] = str(is_read).lower()
        data = self._request("GET", "/api/store-intel/alerts", query=query)
        return [self._namespace(item) for item in self._items(data)]

    def unread_count(self) -> int:
        return len(self.list_alerts(is_read=False, limit=200))

    def mark_alerts_read(self, ids: list[int] | None = None) -> int:
        data = self._request(
            "POST",
            "/api/store-intel/alerts/read",
            body={"ids": ids or []},
        )
        return int(data.get("updated") or 0)

    def latest_keyword_rank_label(
        self, keyword: str, app_id: str, country: str = "us", lang: str = "en"
    ) -> str:
        return self._rank_label(
            (self.list_keyword_rank_history(keyword, app_id, country, lang, limit=1) or [None])[-1]
        )

    def list_keyword_rank_history(
        self,
        keyword: str,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 0,
    ) -> list[SimpleNamespace]:
        data = self._request(
            "GET",
            "/api/store-intel/keyword-rank/history",
            query={
                "keyword": keyword,
                "app_id": app_id,
                "country": country,
                "lang": lang,
                "limit": limit,
            },
        )
        return [self._namespace(item) for item in self._items(data)]

    def list_recent_keyword_ranks(
        self,
        *,
        app_id: str = "",
        country: str = "",
        lang: str = "",
        limit: int = 8,
    ) -> list[SimpleNamespace]:
        query: dict[str, Any] = {"limit": limit}
        if app_id:
            query["app_id"] = app_id
        if country:
            query["country"] = country
        if lang:
            query["lang"] = lang
        data = self._request(
            "GET",
            "/api/store-intel/keyword-rank/recent",
            query=query,
        )
        return [self._namespace(item) for item in self._items(data)]

    def latest_chart_rank_label(
        self,
        app_id: str,
        collection: str,
        category: str | None = "APPLICATION",
        country: str = "us",
        lang: str = "en",
    ) -> str:
        return self._rank_label(
            (
                self.list_chart_rank_history(
                    app_id,
                    collection,
                    category=category,
                    country=country,
                    lang=lang,
                    limit=1,
                )
                or [None]
            )[-1]
        )

    def list_chart_rank_history(
        self,
        app_id: str,
        collection: str,
        category: str | None = "APPLICATION",
        country: str = "us",
        lang: str = "en",
        limit: int = 0,
    ) -> list[SimpleNamespace]:
        data = self._request(
            "GET",
            "/api/store-intel/chart-rank/history",
            query={
                "app_id": app_id,
                "collection": collection,
                "category": category or "",
                "country": country,
                "lang": lang,
                "limit": limit,
            },
        )
        return [self._namespace(item) for item in self._items(data)]

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        if not self.enabled:
            raise StoreIntelApiError("StoreIntel API 未配置。")
        url = self.base_url + path
        request_path = path
        if query:
            encoded_query = urlencode({k: v for k, v in query.items() if v is not None})
            url += "?" + encoded_query
            request_path += "?" + encoded_query
        payload = None
        headers = {"Accept": "application/json", "User-Agent": DEFAULT_USER_AGENT}
        if body is not None:
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        request = Request(url, data=payload, headers=headers, method=method)
        started = time.perf_counter()
        status: int | None = None
        code: Any = None
        ok = False
        error = ""
        response_data: Any = None
        raw_response = ""

        def emit_log() -> None:
            self._emit_log(
                method=method,
                path=request_path,
                query=query,
                body=body,
                response=response_data,
                raw_response=raw_response,
                status=status,
                code=code,
                ok=ok,
                error=error,
                started=started,
            )

        try:
            with urlopen(request, timeout=timeout or self.timeout) as response:
                status = getattr(response, "status", None)
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            status = getattr(exc, "code", None)
            raw = exc.read().decode("utf-8", errors="replace")
            raw_response = self._text_preview(raw)
            error = self._error_message(raw, exc.reason)
            emit_log()
            raise StoreIntelApiError(error) from exc
        except URLError as exc:
            error = f"StoreIntel API 请求失败：{exc.reason}"
            emit_log()
            raise StoreIntelApiError(error) from exc
        except Exception as exc:
            error = str(exc)
            emit_log()
            raise
        try:
            envelope = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            error = "StoreIntel API 返回了无效 JSON。"
            raw_response = self._text_preview(raw)
            emit_log()
            raise StoreIntelApiError(error) from exc
        try:
            code = envelope.get("code")
            response_data = envelope.get("data")
            if code != 200:
                error = self._error_message(raw, envelope.get("message") or "请求失败")
                raise StoreIntelApiError(error)
            ok = True
            return response_data
        finally:
            emit_log()

    def _stream_request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        timeout: float | None = None,
    ):
        if not self.enabled:
            raise StoreIntelApiError("StoreIntel API 未配置。")
        payload = None
        headers = {"Accept": "application/x-ndjson", "User-Agent": DEFAULT_USER_AGENT}
        if body is not None:
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        request = Request(self.base_url + path, data=payload, headers=headers, method=method)
        started = time.perf_counter()
        status: int | None = None
        ok = False
        error = ""
        try:
            with urlopen(request, timeout=timeout or self.timeout) as response:
                status = getattr(response, "status", None)
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError as exc:
                        error = "StoreIntel API 返回了无效流式 JSON。"
                        raise StoreIntelApiError(error) from exc
                ok = True
        except HTTPError as exc:
            status = getattr(exc, "code", None)
            raw = exc.read().decode("utf-8", errors="replace")
            error = self._error_message(raw, exc.reason)
            raise StoreIntelApiError(error) from exc
        except URLError as exc:
            error = f"StoreIntel API 请求失败：{exc.reason}"
            raise StoreIntelApiError(error) from exc
        except Exception as exc:
            if not error:
                error = str(exc)
            raise
        finally:
            self._emit_log(
                method=method,
                path=path,
                query=None,
                body=body,
                response=None,
                raw_response="",
                status=status,
                code=None,
                ok=ok,
                error=error,
                started=started,
                stream=True,
            )

    def set_log_sink(self, log_sink: Callable[[dict[str, Any]], None] | None) -> None:
        self.log_sink = log_sink

    def _emit_log(
        self,
        *,
        method: str,
        path: str,
        query: dict[str, Any] | None,
        body: dict[str, Any] | None,
        response: Any,
        raw_response: str,
        status: int | None,
        code: Any,
        ok: bool,
        error: str,
        started: float,
        stream: bool = False,
    ) -> None:
        if self.log_sink is None:
            return
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        entry = {
            "time": time.strftime("%H:%M:%S"),
            "method": method.upper(),
            "path": path,
            "query": self._payload_preview(query),
            "query_full": self._payload_text(query),
            "body": self._payload_preview(body),
            "body_full": self._payload_text(body),
            "response": self._payload_preview(response) if response is not None else raw_response,
            "response_full": self._payload_text(response) if response is not None else raw_response,
            "status": status if status is not None else "-",
            "code": code if code is not None else "-",
            "duration_ms": elapsed_ms,
            "ok": ok,
            "error": error,
            "stream": stream,
        }
        try:
            self.log_sink(entry)
        except Exception:
            pass

    def _payload_preview(self, value: Any) -> str:
        return self._payload_text(value, list_limit=20, max_chars=240)

    def _payload_text(
        self,
        value: Any,
        *,
        list_limit: int | None = None,
        max_chars: int | None = None,
    ) -> str:
        if value is None:
            return ""
        sensitive = {"authorization", "password", "token", "secret", "api_key", "key", "proxy"}

        def sanitize(item: Any) -> Any:
            if isinstance(item, dict):
                result = {}
                for key, child in item.items():
                    if str(key).lower() in sensitive:
                        result[key] = "***"
                    else:
                        result[key] = sanitize(child)
                return result
            if isinstance(item, list):
                children = item if list_limit is None else item[:list_limit]
                return [sanitize(child) for child in children]
            return item

        text = json.dumps(sanitize(value), ensure_ascii=False, separators=(",", ":"))
        if max_chars is not None and len(text) > max_chars:
            return text[: max_chars - 3] + "..."
        return text

    def _text_preview(self, text: str) -> str:
        if len(text) > 240:
            return text[:237] + "..."
        return text

    @staticmethod
    def _to_jsonable(value: Any) -> Any:
        if isinstance(value, BaseModel):
            return value.model_dump(mode="json", exclude_none=True)
        if isinstance(value, dict):
            return value
        return dict(value)

    @staticmethod
    def _namespace(value: dict[str, Any]) -> SimpleNamespace:
        return SimpleNamespace(**{str(k): v for k, v in (value or {}).items()})

    @staticmethod
    def _items(data: dict[str, Any]) -> list[Any]:
        items = (data or {}).get("items")
        return items if isinstance(items, list) else []

    @staticmethod
    def _rank_label(item: Any | None) -> str:
        if not item:
            return "未同步"
        found = item.get("found") if isinstance(item, dict) else getattr(item, "found", False)
        rank = item.get("rank") if isinstance(item, dict) else getattr(item, "rank", None)
        if found and rank is not None:
            return f"#{rank}"
        return "未命中"

    @staticmethod
    def _error_message(raw: str, fallback: str) -> str:
        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError:
            return str(fallback)
        message = payload.get("message") or fallback
        error_code = (payload.get("data") or {}).get("error_code")
        return f"{message} ({error_code})" if error_code else str(message)
