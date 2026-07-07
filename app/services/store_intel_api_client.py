from __future__ import annotations

import json
import hashlib
from http.client import HTTPException
import platform
import threading
import time
import uuid
from types import SimpleNamespace
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import ProxyHandler, Request, build_opener

from curl_cffi import requests as curl_requests
from pydantic import BaseModel

from app.schemas.app_schema import AppDetail, AppSummary
from app.schemas.chart_schema import ChartItem
from app.schemas.keyword_schema import KeywordRankResult
from app.schemas.review_schema import ReviewItem


DEFAULT_USER_AGENT = "CatchRadar/desktop"

# Transient-network retry budget for idempotent GETs (see _request): one flaky
# hop shouldn't fail a read that would succeed 500ms later.
_TRANSIENT_RETRIES = 2
_TRANSIENT_BACKOFF_SECONDS = 0.5

# Backend API calls should be direct. urllib reads macOS system proxies even
# when shell proxy env vars are empty, which can route localhost tests and
# Cloudflare API reads through a flaky local proxy.
urlopen = build_opener(ProxyHandler({})).open
_CURL_IMPERSONATE = "chrome"
_TRANSIENT_EXCEPTIONS = (
    OSError,
    HTTPException,
    curl_requests.exceptions.RequestException,
)


class StoreIntelApiError(RuntimeError):
    pass


class StoreIntelApiCacheMiss(StoreIntelApiError):
    pass


class _HTTPStatusError(Exception):
    def __init__(self, status: int | None, raw: str, reason: str = "") -> None:
        super().__init__(reason or str(status or ""))
        self.status = status
        self.raw = raw
        self.reason = reason


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
        auth_app_id: str = "catchradar",
        device_id: str | None = None,
    ) -> None:
        self.base_url = (base_url or "").strip().rstrip("/")
        self.timeout = timeout
        self.log_sink = log_sink
        self.auth_app_id = auth_app_id
        self.device_id = device_id or self._default_device_id()
        self._access_token = ""
        self._refresh_token = ""
        self._auth_lock = threading.Lock()
        self._auth_epoch = 0

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)

    @property
    def api_url(self) -> str:
        """The configured API base URL, for UI 'connected to: ...' indicators."""
        return self.base_url

    def search(
        self,
        keyword: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 50,
        platform: str = "google_play",
    ) -> list[AppSummary]:
        data = self._request(
            "GET",
            "/api/store-intel/apps/search",
            query={
                "query": keyword,
                "country": country,
                "lang": lang,
                "limit": limit,
                "platform": platform,
            },
        )
        return [AppSummary(**item) for item in self._items(data)]

    def search_cached(
        self,
        keyword: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 50,
        platform: str = "google_play",
    ) -> list[AppSummary]:
        data = self._request(
            "GET",
            "/api/store-intel/apps/search/cache",
            query={
                "query": keyword,
                "country": country,
                "lang": lang,
                "limit": limit,
                "platform": platform,
            },
        )
        return [AppSummary(**item) for item in self._items(data)]

    def app_detail(
        self, app_id: str, country: str = "us", lang: str = "en", platform: str = "google_play"
    ) -> AppDetail:
        data = self._request(
            "GET",
            f"/api/store-intel/apps/{quote(app_id, safe='')}",
            query={"country": country, "lang": lang, "platform": platform},
        )
        return AppDetail(**data)

    def cached_app_detail(
        self, app_id: str, country: str = "us", lang: str = "en", platform: str = "google_play"
    ) -> AppDetail:
        data = self._request(
            "GET",
            f"/api/store-intel/apps/{quote(app_id, safe='')}/cache",
            query={"country": country, "lang": lang, "platform": platform},
        )
        if (data or {}).get("cached") is False or not (data or {}).get("detail"):
            raise StoreIntelApiCacheMiss("暂无应用详情缓存。")
        return AppDetail(**(data.get("detail") or {}))

    def similar_apps(
        self,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 10,
        platform: str = "google_play",
    ) -> list[AppSummary]:
        data = self._request(
            "GET",
            f"/api/store-intel/apps/{quote(app_id, safe='')}/similar",
            query={"country": country, "lang": lang, "limit": limit, "platform": platform},
        )
        return [AppSummary(**item) for item in self._items(data)]

    def permissions(
        self,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        platform: str = "google_play",
    ) -> dict[str, list[str]]:
        data = self._request(
            "GET",
            f"/api/store-intel/apps/{quote(app_id, safe='')}/permissions",
            query={"country": country, "lang": lang, "platform": platform},
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
        platform: str = "google_play",
    ) -> tuple[list[ReviewItem], object]:
        query: dict[str, Any] = {
            "country": country,
            "lang": lang,
            "sort": sort,
            "limit": limit,
            "platform": platform,
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
        platform: str = "google_play",
    ) -> int:
        data = self._request(
            "POST",
            f"/api/store-intel/apps/{quote(app_id, safe='')}/reviews",
            body={
                "country": country,
                "lang": lang,
                "items": [self._to_jsonable(item) for item in items],
                "platform": platform,
            },
        )
        return int(data.get("saved") or 0)

    def list_cached_reviews(
        self, app_id: str, limit: int = 10, platform: str = "google_play"
    ) -> list[ReviewItem]:
        data = self._request(
            "GET",
            f"/api/store-intel/apps/{quote(app_id, safe='')}/reviews/cache",
            query={"limit": limit, "platform": platform},
        )
        return [ReviewItem(**item) for item in self._items(data)]

    def fetch_chart(
        self,
        chart_type: str,
        category: str | None,
        country: str,
        lang: str,
        limit: int,
        platform: str = "google_play",
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
                "platform": platform,
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
        platform: str = "google_play",
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
                "platform": platform,
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
        platform: str = "google_play",
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
                "platform": platform,
            },
        )
        return int(data.get("saved") or 0)

    def list_app_snapshots(
        self,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 80,
        platform: str = "google_play",
    ) -> list[SimpleNamespace]:
        data = self._request(
            "GET",
            "/api/store-intel/app-snapshots/history",
            query={
                "app_id": app_id,
                "country": country,
                "lang": lang,
                "limit": limit,
                "platform": platform,
            },
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
        platform: str = "google_play",
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
                "platform": platform,
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
        platform: str = "google_play",
    ) -> KeywordRankResult | None:
        history = self.list_keyword_rank_history(
            keyword, app_id, country, lang, limit=1, platform=platform
        )
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
        platform: str = "google_play",
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
                "platform": platform,
            },
        )
        return self._namespace(data)

    def cached_coverage(
        self,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        deep: bool = False,
        platform: str = "google_play",
    ) -> SimpleNamespace:
        data = self._request(
            "GET",
            "/api/store-intel/keyword-coverage/cache",
            query={
                "app_id": app_id,
                "country": country,
                "lang": lang,
                "deep": str(deep).lower(),
                "platform": platform,
            },
            timeout=min(self.timeout, 5.0),
        )
        return self._namespace(data)

    def list_app_keyword_serp(
        self,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 200,
        platform: str = "google_play",
    ) -> SimpleNamespace:
        data = self._request(
            "GET",
            "/api/store-intel/keyword-serp/app",
            query={
                "app_id": app_id,
                "country": country,
                "lang": lang,
                "limit": limit,
                "platform": platform,
            },
        )
        return self._namespace(data)

    def analyze_keyword_gap(
        self,
        app_id: str,
        competitor_app_id: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 200,
        platform: str = "google_play",
    ) -> SimpleNamespace:
        data = self._request(
            "GET",
            "/api/store-intel/keyword-gap",
            query={
                "app_id": app_id,
                "competitor_app_id": competitor_app_id,
                "country": country,
                "lang": lang,
                "limit": limit,
                "platform": platform,
            },
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
        platform: str = "google_play",
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
                "platform": platform,
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

    def list_tracked_apps(
        self, enabled: bool | None = None, platform: str = ""
    ) -> list[SimpleNamespace]:
        query: dict[str, Any] = {}
        if enabled is not None:
            query["enabled"] = str(enabled).lower()
        if platform:
            query["platform"] = platform
        data = self._request("GET", "/api/store-intel/tracking/apps", query=query)
        return [self._namespace(item) for item in self._items(data)]

    def list_tracked_keywords(
        self, enabled: bool | None = None, platform: str = ""
    ) -> list[SimpleNamespace]:
        query: dict[str, Any] = {}
        if enabled is not None:
            query["enabled"] = str(enabled).lower()
        if platform:
            query["platform"] = platform
        data = self._request("GET", "/api/store-intel/tracking/keywords", query=query)
        return [self._namespace(item) for item in self._items(data)]

    def list_tracked_chart_apps(
        self, enabled: bool | None = None, platform: str = ""
    ) -> list[SimpleNamespace]:
        query: dict[str, Any] = {}
        if enabled is not None:
            query["enabled"] = str(enabled).lower()
        if platform:
            query["platform"] = platform
        data = self._request("GET", "/api/store-intel/tracking/chart-apps", query=query)
        return [self._namespace(item) for item in self._items(data)]

    def add_tracked_app(
        self,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        frequency: str = "daily",
        tag: str = "",
        platform: str = "google_play",
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
                "platform": platform,
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
        platform: str = "google_play",
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
                "platform": platform,
            },
        )
        return self._namespace(data)

    def remove_tracked_app(
        self, app_id: str, country: str = "us", lang: str = "en", platform: str = "google_play"
    ) -> int:
        data = self._request(
            "POST",
            "/api/store-intel/tracking/apps/remove",
            body={"app_id": app_id, "country": country, "lang": lang, "platform": platform},
        )
        return int(data.get("updated") or 0)

    def set_tracked_app_enabled(
        self,
        app_id: str,
        enabled: bool,
        country: str = "us",
        lang: str = "en",
        platform: str = "google_play",
    ) -> SimpleNamespace:
        data = self._request(
            "POST",
            "/api/store-intel/tracking/apps/enabled",
            body={
                "app_id": app_id,
                "country": country,
                "lang": lang,
                "enabled": enabled,
                "platform": platform,
            },
        )
        return self._namespace(data)

    def set_tracked_app_frequency(
        self,
        app_id: str,
        frequency: str,
        country: str = "us",
        lang: str = "en",
        platform: str = "google_play",
    ) -> SimpleNamespace:
        data = self._request(
            "POST",
            "/api/store-intel/tracking/apps/frequency",
            body={
                "app_id": app_id,
                "country": country,
                "lang": lang,
                "frequency": frequency,
                "platform": platform,
            },
        )
        return self._namespace(data)

    def set_tracked_app_tag(
        self,
        app_id: str,
        tag: str,
        country: str = "us",
        lang: str = "en",
        platform: str = "google_play",
    ) -> SimpleNamespace:
        data = self._request(
            "POST",
            "/api/store-intel/tracking/apps/tag",
            body={"app_id": app_id, "country": country, "lang": lang, "tag": tag, "platform": platform},
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
        platform: str = "google_play",
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
                "platform": platform,
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
        platform: str = "google_play",
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
                "platform": platform,
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
        platform: str = "google_play",
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
                "platform": platform,
            },
        )
        return self._namespace(data.get("rank") or {})

    def sync_app_now(
        self, app_id: str, country: str = "us", lang: str = "en", platform: str = "google_play"
    ) -> AppDetail:
        data = self._request(
            "POST",
            "/api/store-intel/tracking/apps/sync",
            body={"app_id": app_id, "country": country, "lang": lang, "platform": platform},
        )
        return AppDetail(**(data.get("detail") or {}))

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
            "dead",  # exhausted server-side retry attempts — treat like failed
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
        platform: str = "",
    ) -> list[SimpleNamespace]:
        query: dict[str, Any] = {
            "app_id": app_id,
            "type": alert_type,
            "severity": severity,
            "limit": limit,
        }
        if is_read is not None:
            query["is_read"] = str(is_read).lower()
        if platform:
            query["platform"] = platform
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
        self,
        keyword: str,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        platform: str = "google_play",
    ) -> str:
        return self._rank_label(
            (
                self.list_keyword_rank_history(
                    keyword, app_id, country, lang, limit=1, platform=platform
                )
                or [None]
            )[-1]
        )

    def list_keyword_rank_history(
        self,
        keyword: str,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 0,
        platform: str = "google_play",
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
                "platform": platform,
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
        platform: str = "",
    ) -> list[SimpleNamespace]:
        query: dict[str, Any] = {"limit": limit}
        if app_id:
            query["app_id"] = app_id
        if country:
            query["country"] = country
        if lang:
            query["lang"] = lang
        if platform:
            query["platform"] = platform
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
        platform: str = "google_play",
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
                    platform=platform,
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
        platform: str = "google_play",
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
                "platform": platform,
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
        if body is not None:
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
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

        auth_epoch = self._auth_epoch
        auth_attempt = 0
        # Only idempotent GETs retry on transient network failures — retrying a
        # POST could double-apply a mutation the server actually processed.
        transient_left = _TRANSIENT_RETRIES if method.upper() == "GET" else 0
        while True:
            headers = self._request_headers("application/json", has_body=body is not None)
            try:
                if self._use_curl_transport():
                    response = curl_requests.request(
                        method,
                        url,
                        data=payload,
                        headers=headers,
                        timeout=timeout or self.timeout,
                        impersonate=_CURL_IMPERSONATE,
                    )
                    status = response.status_code
                    raw = response.text
                    if status >= 400:
                        raise _HTTPStatusError(status, raw, response.reason)
                else:
                    request = Request(
                        url,
                        data=payload,
                        headers=headers,
                        method=method,
                    )
                    with urlopen(request, timeout=timeout or self.timeout) as response:
                        status = getattr(response, "status", None)
                        raw = response.read().decode("utf-8")
                break
            except _HTTPStatusError as exc:
                status = exc.status
                raw = exc.raw
                raw_response = self._text_preview(raw)
                if self._should_reauth_retry(path, status, auth_attempt):
                    auth_attempt += 1
                    try:
                        self._reauthenticate(auth_epoch)
                    except StoreIntelApiError as auth_exc:
                        error = f"{self._error_message(raw, exc.reason)}；{auth_exc}"
                        emit_log()
                        raise StoreIntelApiError(error) from exc
                    continue
                error = self._error_message(raw, exc.reason)
                emit_log()
                raise StoreIntelApiError(error) from exc
            except HTTPError as exc:
                status = getattr(exc, "code", None)
                raw = exc.read().decode("utf-8", errors="replace")
                raw_response = self._text_preview(raw)
                if self._should_reauth_retry(path, status, auth_attempt):
                    auth_attempt += 1
                    try:
                        self._reauthenticate(auth_epoch)
                    except StoreIntelApiError as auth_exc:
                        error = f"{self._error_message(raw, exc.reason)}；{auth_exc}"
                        emit_log()
                        raise StoreIntelApiError(error) from exc
                    continue
                error = self._error_message(raw, exc.reason)
                emit_log()
                raise StoreIntelApiError(error) from exc
            except _TRANSIENT_EXCEPTIONS as exc:
                # URLError, ssl.SSLError, socket timeouts, connection resets,
                # RemoteDisconnected and IncompleteRead are transient for reads.
                # Retry idempotent GETs before surfacing a clean error.
                if transient_left > 0:
                    transient_left -= 1
                    time.sleep(
                        _TRANSIENT_BACKOFF_SECONDS * (_TRANSIENT_RETRIES - transient_left)
                    )
                    continue
                error = f"StoreIntel API 请求失败：{getattr(exc, 'reason', None) or exc}"
                emit_log()
                raise StoreIntelApiError(error) from exc
            except Exception as exc:
                error = f"StoreIntel API 请求异常：{exc}"
                emit_log()
                raise StoreIntelApiError(error) from exc
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
        if body is not None:
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        started = time.perf_counter()
        status: int | None = None
        ok = False
        error = ""
        try:
            auth_epoch = self._auth_epoch
            for attempt in range(2):
                request = Request(
                    self.base_url + path,
                    data=payload,
                    headers=self._request_headers(
                        "application/x-ndjson",
                        has_body=body is not None,
                    ),
                    method=method,
                )
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
                    break
                except HTTPError as exc:
                    status = getattr(exc, "code", None)
                    raw = exc.read().decode("utf-8", errors="replace")
                    if self._should_reauth_retry(path, status, attempt):
                        try:
                            self._reauthenticate(auth_epoch)
                        except StoreIntelApiError as auth_exc:
                            error = f"{self._error_message(raw, exc.reason)}；{auth_exc}"
                            raise StoreIntelApiError(error) from exc
                        continue
                    error = self._error_message(raw, exc.reason)
                    raise StoreIntelApiError(error) from exc
        except HTTPError as exc:
            status = getattr(exc, "code", None)
            raw = exc.read().decode("utf-8", errors="replace")
            error = self._error_message(raw, exc.reason)
            raise StoreIntelApiError(error) from exc
        except StoreIntelApiError:
            raise
        except OSError as exc:
            # Covers URLError plus mid-stream stalls (socket timeout / reset),
            # which are NOT URLError subclasses once bytes started flowing.
            error = f"StoreIntel API 请求失败：{getattr(exc, 'reason', None) or exc}"
            raise StoreIntelApiError(error) from exc
        except Exception as exc:
            if not error:
                error = str(exc)
            raise StoreIntelApiError(f"StoreIntel API 流式请求异常：{exc}") from exc
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

    def _request_headers(
        self,
        accept: str,
        *,
        has_body: bool,
        include_auth: bool = True,
    ) -> dict[str, str]:
        headers = {"Accept": accept, "User-Agent": DEFAULT_USER_AGENT}
        if has_body:
            headers["Content-Type"] = "application/json; charset=utf-8"
        if include_auth and self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    def _use_curl_transport(self) -> bool:
        return self.base_url.lower().startswith("https://")

    def _should_reauth_retry(self, path: str, status: int | None, attempt: int) -> bool:
        return status == 401 and attempt == 0 and path not in (
            "/api/auth/guest",
            "/api/auth/refresh",
        )

    def _reauthenticate(self, observed_epoch: int) -> None:
        """Re-establish auth after a 401, coalescing concurrent callers.

        Prefers refreshing the existing session (POST /api/auth/refresh) over
        starting a new guest session, falling back to guest login if no
        refresh token is available or the refresh itself fails. observed_epoch
        is the auth epoch the caller saw before its request failed; if another
        thread already advanced the epoch (i.e. already re-authenticated) by
        the time we get the lock, this is a no-op — the caller's retry will
        just use the already-refreshed token.
        """
        with self._auth_lock:
            if self._auth_epoch != observed_epoch:
                return
            if self._refresh_token:
                try:
                    self._refresh_access_token()
                    self._auth_epoch += 1
                    return
                except StoreIntelApiError:
                    pass
            self._guest_login()
            self._auth_epoch += 1

    def _guest_login(self) -> None:
        if not self.enabled:
            raise StoreIntelApiError("StoreIntel API 未配置。")
        body = {
            "app_id": self.auth_app_id,
            "device_id": self.device_id,
            "platform": "desktop",
        }
        access_token, refresh_token = self._auth_request(
            "/api/auth/guest", body, context="guest 登录"
        )
        self._access_token = access_token
        self._refresh_token = refresh_token

    def _refresh_access_token(self) -> None:
        if not self.enabled:
            raise StoreIntelApiError("StoreIntel API 未配置。")
        if not self._refresh_token:
            raise StoreIntelApiError("没有可用的 refresh_token。")
        body = {
            "app_id": self.auth_app_id,
            "refresh_token": self._refresh_token,
        }
        access_token, refresh_token = self._auth_request(
            "/api/auth/refresh", body, context="token 刷新"
        )
        self._access_token = access_token
        self._refresh_token = refresh_token

    def _auth_request(
        self, path: str, body: dict[str, Any], *, context: str
    ) -> tuple[str, str]:
        """POST to an auth endpoint (guest login or token refresh) and return
        the (access_token, refresh_token) pair from a successful response."""
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = self._request_headers("application/json", has_body=True, include_auth=False)
        try:
            if self._use_curl_transport():
                response = curl_requests.post(
                    self.base_url + path,
                    data=payload,
                    headers=headers,
                    timeout=self.timeout,
                    impersonate=_CURL_IMPERSONATE,
                )
                raw = response.text
                if response.status_code >= 400:
                    raise _HTTPStatusError(response.status_code, raw, response.reason)
            else:
                request = Request(
                    self.base_url + path,
                    data=payload,
                    headers=headers,
                    method="POST",
                )
                with urlopen(request, timeout=self.timeout) as response:
                    raw = response.read().decode("utf-8")
        except _HTTPStatusError as exc:
            raise StoreIntelApiError(
                f"StoreIntel API {context}失败：{self._error_message(exc.raw, exc.reason)}"
            ) from exc
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise StoreIntelApiError(
                f"StoreIntel API {context}失败：{self._error_message(raw, exc.reason)}"
            ) from exc
        except _TRANSIENT_EXCEPTIONS as exc:
            raise StoreIntelApiError(
                f"StoreIntel API {context}失败：{getattr(exc, 'reason', None) or exc}"
            ) from exc

        try:
            envelope = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise StoreIntelApiError(f"StoreIntel API {context}返回了无效 JSON。") from exc
        if envelope.get("code") != 200:
            raise StoreIntelApiError(
                f"StoreIntel API {context}失败：{self._error_message(raw, envelope.get('message'))}"
            )
        data = envelope.get("data") or {}
        access_token = str(data.get("access_token") or "")
        if not access_token:
            raise StoreIntelApiError(f"StoreIntel API {context}没有返回 access_token。")
        return access_token, str(data.get("refresh_token") or "")

    @staticmethod
    def _default_device_id() -> str:
        seed = "|".join(
            [
                platform.node(),
                platform.system(),
                platform.machine(),
                str(uuid.getnode()),
            ]
        )
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        return f"desktop-{digest[:32]}"

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
