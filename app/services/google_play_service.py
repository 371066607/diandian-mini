"""FROZEN — legacy/offline-diagnostic scraper only, not the product data path.

The default (API mode) desktop client reads/writes exclusively through
StoreIntelApiClient against the Go backend, which does its own Google Play
scraping in internal/project/catchradar/upstream/googleplay. This module is
a shadow implementation only exercised when CATCH_RADAR_LEGACY_LOCAL_MODE or
CATCH_RADAR_OFFLINE_MODE is set — kept for local diagnostics, not maintained
for new stores/features. If Google changes page structure, fix the Go-side
client; only patch this file for diagnostic-mode-breaking regressions.
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request

from app.constants import (
    EMPTY_RESULT_MESSAGE,
    NETWORK_ERROR_MESSAGE,
    NOT_FOUND_MESSAGE,
)
from app.schemas.app_schema import AppDetail, AppSummary
from app.schemas.chart_schema import ChartItem
from app.schemas.review_schema import ReviewItem
from app.utils.network import urlopen_proxied
from app.utils.normalize import (
    normalize_app_detail,
    normalize_review,
)

_FEATURE_RETIRED_MESSAGE = "该功能已下线，请使用在线（API）模式。"


class ServiceError(RuntimeError):
    pass


class GooglePlayService:
    _PLAY_BASE_URL = "https://play.google.com"

    # gplay_scraper supports pluggable HTTP clients. A TLS-fingerprinting client
    # (curl_cffi) impersonates a real browser, surviving the bot-blocking /
    # IncompleteRead failures the plain-urllib path keeps hitting. Prefer the most
    # resilient available client; fall back to the library default (None) when the
    # optional backend isn't bundled.
    _GPLAY_HTTP_CLIENTS = ("curl_cffi", None)

    def __init__(self, request_delay_seconds: float = 1.0) -> None:
        self.request_delay_seconds = max(0.0, request_delay_seconds)
        try:
            from google_play_scraper import Sort, app, permissions, reviews, search
            from google_play_scraper.constants.element import ElementSpecs
            from google_play_scraper.constants.regex import Regex
            from google_play_scraper.features.app import parse_dom
        except ImportError as exc:  # pragma: no cover - dependency validation
            raise ServiceError(
                "缺少 google-play-scraper 依赖，请先安装 requirements.txt。"
            ) from exc

        self._ElementSpecs = ElementSpecs
        self._Regex = Regex
        self._Sort = Sort
        self._app = app
        self._app_parse_dom = parse_dom
        self._search = search
        self._reviews = reviews
        self._permissions = permissions

        try:
            from gplay_scraper import GPlayScraper

            self._gplay_scraper, self._gplay_http_client = self._build_gplay_scraper(GPlayScraper)
        except ImportError:  # pragma: no cover - optional dependency
            self._gplay_scraper = None
            self._gplay_http_client = None

    @classmethod
    def _build_gplay_scraper(cls, gplay_scraper_cls):
        """Instantiate GPlayScraper preferring a resilient HTTP client, returning
        ``(instance, active_client_name)``. Best-effort: a client whose backend
        isn't importable or fails to init is skipped for the next candidate, so a
        missing optional dependency degrades to the library default instead of
        breaking construction."""
        import importlib.util

        for client in cls._GPLAY_HTTP_CLIENTS:
            if client is not None and importlib.util.find_spec(client) is None:
                continue
            try:
                return gplay_scraper_cls(http_client=client), client
            except Exception:  # noqa: BLE001 - try the next client on any init error
                continue
        return gplay_scraper_cls(), None

    def configure(self, *, request_delay_seconds: float | None = None) -> None:
        """Update runtime request tuning (called when settings change)."""
        if request_delay_seconds is not None:
            self.request_delay_seconds = max(0.0, request_delay_seconds)

    def search(
        self,
        keyword: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 20,
        proxy: str | None = None,
    ) -> list[AppSummary]:
        raise ServiceError(_FEATURE_RETIRED_MESSAGE)

    def suggest(
        self,
        term: str,
        country: str = "us",
        lang: str = "en",
        count: int = 8,
    ) -> list[str]:
        """Google Play search autocomplete — expand a seed term into real query
        phrases (e.g. "photo edit" -> "photo editor free"). Best-effort: returns []
        when the optional gplay_scraper backend or the network is unavailable, since
        suggestions only enrich the keyword-coverage candidate pool."""
        term = (term or "").strip()
        if not term or self._gplay_scraper is None:
            return []
        try:
            hints = self._gplay_scraper.suggest_analyze(
                term, count=max(1, count), lang=lang, country=country or ""
            )
        except Exception:
            return []
        return [h.strip() for h in (hints or []) if isinstance(h, str) and h.strip()]

    def app_detail(
        self,
        app_id: str,
        country: str = "us",
        lang: str = "en",
    ) -> AppDetail:
        # Primary path: gplay_scraper (TLS-bypass client, 57-field response).
        if self._gplay_scraper is not None:
            try:
                raw = self._gplay_scraper.app_analyze(app_id=app_id, lang=lang, country=country)
                if raw:
                    return self._map_detail(raw)
            except Exception:
                pass

        # Fallback: google_play_scraper with DOM enrichment.
        url = self._build_store_url(app_id, country=country, lang=lang)
        dom = None
        try:
            raw = self._run_with_retry(
                self._app,
                app_id,
                max_attempts=6,
                country=country,
                lang=lang,
            )
        except Exception as exc:
            if "not found" in str(exc).lower():
                raise ServiceError(NOT_FOUND_MESSAGE) from exc
            try:
                dom = self._run_with_retry(
                    self._request_text,
                    url,
                    max_attempts=3,
                )
                raw = self._app_parse_dom(dom=dom, app_id=app_id, url=url)
            except Exception:
                raise ServiceError(NETWORK_ERROR_MESSAGE) from exc

        if not raw:
            raise ServiceError(NOT_FOUND_MESSAGE)
        return self._map_detail(raw)

    def similar(
        self,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 20,
    ) -> list[AppSummary]:
        raise ServiceError(_FEATURE_RETIRED_MESSAGE)

    def reviews(
        self,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        sort: str = "newest",
        continuation_token=None,
    ) -> tuple[list[ReviewItem], object]:
        sort_mapping = {
            "newest": self._Sort.NEWEST,
            "rating": self._Sort.RATING,
            "helpfulness": self._Sort.MOST_RELEVANT,
            "most_relevant": self._Sort.MOST_RELEVANT,
        }
        try:
            raw_items, next_token = self._run_with_retry(
                self._reviews,
                app_id,
                max_attempts=3,
                country=country,
                lang=lang,
                sort=sort_mapping.get(sort, self._Sort.NEWEST),
                count=20,
                continuation_token=continuation_token,
            )
        except Exception as exc:
            raise ServiceError(NETWORK_ERROR_MESSAGE) from exc

        return [self._map_review(app_id, item) for item in raw_items], next_token

    def permissions(
        self,
        app_id: str,
        country: str = "us",
        lang: str = "en",
    ) -> dict[str, list[str]]:
        try:
            result = self._run_with_retry(
                self._permissions,
                app_id,
                max_attempts=3,
                lang=lang,
                country=country,
            )
        except Exception as exc:
            raise ServiceError(NETWORK_ERROR_MESSAGE) from exc
        return result

    def chart(
        self,
        chart_type: str,
        category: str | None = None,
        country: str = "us",
        lang: str = "en",
        limit: int = 100,
    ) -> list[ChartItem]:
        raise ServiceError(_FEATURE_RETIRED_MESSAGE)

    def list_analyze(
        self,
        chart_type: str,
        category: str | None = None,
        country: str = "us",
        lang: str = "en",
        limit: int = 100,
    ) -> list[ChartItem]:
        if self._gplay_scraper is None:
            return self.chart(
                chart_type=chart_type, category=category, country=country, lang=lang, limit=limit
            )
        normalized_type, _ = self._normalize_chart_type(chart_type)
        collection = normalized_type.upper()  # top_free -> TOP_FREE
        normalized_category = self._normalize_chart_category(category)
        fetch_limit = max(1, min(limit, 500))
        try:
            raw_items = self._gplay_scraper.list_analyze(
                collection=collection,
                category=normalized_category,
                count=fetch_limit,
                lang=lang,
                country=country,
            )
        except Exception as exc:
            raise ServiceError(NETWORK_ERROR_MESSAGE) from exc
        if not raw_items:
            raise ServiceError(EMPTY_RESULT_MESSAGE)
        items: list[ChartItem] = []
        for index, raw in enumerate(raw_items[:limit], start=1):
            app_id = raw.get("appId")
            if not app_id:
                continue
            items.append(
                ChartItem(
                    rank=index,
                    chart_type=normalized_type,
                    category=raw.get("genre") or normalized_category,
                    country=country,
                    lang=lang,
                    app_id=app_id,
                    title=raw.get("title"),
                    developer=raw.get("developer"),
                    rating=raw.get("score"),
                    score_text=raw.get("scoreText"),
                    installs=raw.get("installs"),
                    price=raw.get("price"),
                    free=raw.get("free"),
                    currency=raw.get("currency"),
                    icon_url=raw.get("icon"),
                    store_url=raw.get("url"),
                    screenshots=raw.get("screenshots") or [],
                    description=raw.get("description"),
                    raw={"source": raw},
                )
            )
        if not items:
            raise ServiceError(EMPTY_RESULT_MESSAGE)
        return items

    def _map_detail(self, raw: dict[str, Any]) -> AppDetail:
        detail = normalize_app_detail(raw)
        if detail.android_version is None:
            detail.android_version = raw.get("androidVersionText")
        return detail

    def _map_review(self, app_id: str, raw: dict[str, Any]) -> ReviewItem:
        return normalize_review(raw, app_id)

    def _build_store_url(self, app_id: str, country: str, lang: str) -> str:
        return f"{self._PLAY_BASE_URL}/store/apps/details?{urlencode({'id': app_id, 'hl': lang, 'gl': country})}"

    def _request_text(
        self,
        url: str,
        method: str = "GET",
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        proxy: str | None = None,
    ) -> str:
        request_headers = headers or {"User-Agent": "Mozilla/5.0"}
        request = Request(
            url,
            data=data,
            headers=request_headers,
            method=method,
        )
        with urlopen_proxied(request, timeout=30, proxy=proxy) as response:
            return response.read().decode("utf-8")

    def _normalize_chart_type(self, chart_type: str) -> tuple[str, str]:
        normalized = (chart_type or "top_free").strip().lower()
        collection_map = {
            "top_free": "topselling_free",
            "top_paid": "topselling_paid",
            "top_grossing": "topgrossing",
            "grossing": "topgrossing",
        }
        collection = collection_map.get(normalized)
        if collection is None:
            raise ServiceError("chart_type 仅支持 top_free / top_paid / top_grossing。")
        normalized_key = {
            "topselling_free": "top_free",
            "topselling_paid": "top_paid",
            "topgrossing": "top_grossing",
        }[collection]
        return normalized_key, collection

    def _normalize_chart_category(self, category: str | None) -> str:
        if not category:
            return "APPLICATION"
        return category.strip().upper().replace(" ", "_")

    def _run_with_retry(self, fn, *args, **kwargs):
        max_attempts = kwargs.pop("max_attempts", 2)
        last_error = None
        for attempt in range(max_attempts):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                last_error = exc
                if attempt < max_attempts - 1:
                    time.sleep(self.request_delay_seconds * (2**attempt))
                    continue
                raise
        raise last_error
