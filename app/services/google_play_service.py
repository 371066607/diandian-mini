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

import base64
import gzip
import html
import json
import re
import shutil
import time
from typing import Any
from urllib.parse import quote, urlencode, urljoin
from urllib.request import Request

from app.constants import (
    DATA_ERROR_MESSAGE,
    EMPTY_RESULT_MESSAGE,
    NETWORK_ERROR_MESSAGE,
    NOT_FOUND_MESSAGE,
)
from app.schemas.app_schema import AppDetail, AppSummary
from app.schemas.chart_schema import ChartItem
from app.schemas.review_schema import ReviewItem
from app.utils import proc
from app.utils.install_parser import parse_install_range
from app.utils.network import urlopen_proxied
from app.utils.normalize import (
    normalize_app_detail,
    normalize_app_summary,
    normalize_review,
)


class ServiceError(RuntimeError):
    pass


class GooglePlayService:
    _PLAY_BASE_URL = "https://play.google.com"
    _CHART_URL_TEMPLATE = (
        "https://play.google.com/_/PlayStoreUi/data/batchexecute"
        "?rpcids=vyAe2&source-path=%2Fstore%2Fapps&f.sid=-4178618388443751758"
        "&bl=boq_playuiserver_20220612.08_p0&authuser=0&soc-app=121"
        "&soc-platform=1&soc-device=1&_reqid=82003&rt=c&hl={lang}&gl={country}"
    )
    _CHART_AT_TOKEN = "AFSRYlx8XZfN8-O-IKASbNBDkB6T:1655531200971"
    _CHART_BODY_TEMPLATE_B64 = (
        "H4sIAAAAAAAC/9Vc3W/UOBD/ZyhvIGfGHtsPPLRUJyEkkI57OHiDaqkqllZXtQiE+N8vdjb7QRznvPasz9I2m008vxl7Pm03+fz8fvXPizN1sfkAfPtxvoL++wxeuqO/fPu4Xrvf/ocZzkD0309+3j5+/XWmLt0HXj7cP676r11zkv135/6s6o/anTp67eCtu+5QOt8C/W93oyN3kMofXfNO+WbKt1OuCej+gO4quovWUaC7gZ4jocf2VORxxHB94OkxN6xdS+WaKIehtBcChv7sun4wAv3H99S3Obiz/+NyOyyHGBPEzRksN56Qdqk0v5H+1sv5TvznhvssxkFK47Ig97KM0RaHjfqPV/j+ZWdPGkej6oQ/da2UMxtvidZZmrfDzhvsYFZ2tMZO+CM4Su3sTrpbxlurw/CuM5ifu6vdXekaS9g4wkRWPWC3IKZztRbktE1IaZqQsg/HTZgmNCFmn7GaGM2epAkXMo0MZxNi9mVSE2K24UOWGsnpjcT3NgK8bkTMNiISyUbiO7YhJ7ZRGbtFgSbkpEbGs5WyUzUyD6Y2/B2hkeFspFJqZLYh/v/R0waX5jYrxyDH5WLP3i/yqnFl2C/w4rZwncIiE25o8asIsOWBNTywgfWgMsMLPLiB1FdG3sDEqYzeDJfAPLiBVYMyuEyKs8QVH7gcg8kzNBcuk6GR5HIMZAJGptAemh+VASYuidnCsOJK98RkFQhcAnPFNa6EJBisuNPRylKNtFtc2R3gyhgucgHHass8ZMuEa5hwI+Vl5hADE3AksmVKHKkoMpVn2ERmAo4UmZnAXNqzxBYr2DyEy0U0GzCXvZFk8xDkQkauWB8rNzORiU1mvrCs2KoA4rINBDaR2aIcW44SHNYs5spOGouwAAEmU8wUijESm0pgUgnCNVu0G5BKEXbnKI9wooz23KQzSaUIVzJRiuSuW0q3q3QVJutQp1MkDy/JdBViMgkmO9VMDo2SUDqXI9xEpQchSh4xhHQm6Tac7r4iSSuhGK/GtOC3wvymGdjxaYXtMoZ/DoLGBxuGzTGx3SGjcf9Mh5liFa6BXHMKtrYGU1OD6TRvnkStUIPrNDCdpK/TvHYSazJ1OluD67SeOQnXKuZkqU4crhMmqsQJXYdrFdchWSdMYBW2WCWxB+ruk7ClOr2tlGZVnQKVqlgyQp3O1sk9dUoZcXKvlaHJHY6rgHsTw+GRds/fn+lxc3r3gDuIMD5yMwhM2QpzsMz4hhl/OucqrQJgZjAN8aV7MC04SyvZsHeBmcF01lOaAbeWLbHHInZP43Y1zc6A205JsnsacnNA7pwTmCOU5kDsfeBPC4q9eiFuW0Jg7wJ7VGXPnYLTGzC6hyK3DxLpMClm0Mb2MxaJ7fGk5njSyA7BcnfheNrIMsIy38h65fJYmRzGx9NGVrGXaTMGy1KOPecYR4Z16BzaDCWRzDEOzCDGDPePrUAuE1MO5yw3VjmhljJGGyGHcY4/5QQfcaSWYS4h6pESt0tXvq0JY2AJkJkUmYhiC2CYAhjh7Jk6JFAAJOyIqZKEA37qwJoiohQACefcVJASI2upiO8UsbYS5qaLgJTQMcki1oYlULBEXJrJ5qkoVESWMmFFFckcVEJHCEVEKeLNReKkONZaZt+au327bbd7sfDuP7cPk+/l3Ht0/SuglXsL9JOfV3fr9erq4ebu9tdwaf/ex4fV9d39j/HODgX2JAK4Xt2u7m+u9ps8/fjw4vyPd3++X383f3/4/MY8e/vs1evzd5/eXFx+uaC/zvC8t1+lsAMhrO6e/gtUe9JfsFoAAA=="
    )
    _CHART_COLLECTION_MAP = {
        "top_free": "topselling_free",
        "top_paid": "topselling_paid",
        "top_grossing": "topgrossing",
        "grossing": "topgrossing",
    }

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
            raise ServiceError("缺少 google-play-scraper 依赖，请先安装 requirements.txt。") from exc

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
            self._gplay_scraper, self._gplay_http_client = self._build_gplay_scraper(
                GPlayScraper
            )
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
        # The google_play_scraper library path consistently fails with IncompleteRead
        # against current Play Store responses — skip it and go straight to DOM.
        try:
            raw_items = self._search_via_dom(keyword, country, lang, limit, proxy)
        except Exception as exc:
            raise ServiceError(NETWORK_ERROR_MESSAGE) from exc

        mapped_items = [item for raw in raw_items if (item := self._try_map_summary(raw)) is not None]
        if not mapped_items:
            raise ServiceError(EMPTY_RESULT_MESSAGE)
        return mapped_items

    def _search_via_dom(self, keyword, country, lang, limit, proxy):
        """Fetch + parse the Play Store search results HTML directly (the only search
        path that can run through an explicit proxy)."""
        url = (
            f"{self._PLAY_BASE_URL}/store/search?"
            f"q={quote(keyword)}&c=apps&hl={lang}&gl={country}"
        )
        dom = self._run_with_retry(self._request_text, url, max_attempts=3, proxy=proxy)
        return self._parse_search_dom(dom, n_hits=limit)

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

    def suggest_nested(
        self,
        term: str,
        country: str = "us",
        lang: str = "en",
        count: int = 5,
    ) -> dict[str, list[str]]:
        """Two-level autocomplete expansion: each suggestion mapped to ITS own
        suggestions ("photo editor" -> ["photo editor free", ...]). Yields a much
        deeper keyword set than the flat ``suggest`` at the cost of ~count× more
        requests, so callers opt in for deep mining only. Best-effort: returns {}
        when the gplay_scraper backend or the network is unavailable."""
        term = (term or "").strip()
        if not term or self._gplay_scraper is None:
            return {}
        try:
            nested = self._gplay_scraper.suggest_nested(
                term, count=max(1, count), lang=lang, country=country or ""
            )
        except Exception:
            return {}
        out: dict[str, list[str]] = {}
        for parent, children in (nested or {}).items():
            if not isinstance(parent, str) or not parent.strip():
                continue
            out[parent.strip()] = [
                c.strip() for c in (children or []) if isinstance(c, str) and c.strip()
            ]
        return out

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
        detail = self._map_detail(raw)
        if self._needs_dom_enrichment(detail):
            try:
                dom = dom or self._run_with_retry(
                    self._request_text,
                    url,
                    max_attempts=3,
                )
                self._enrich_detail_from_dom(detail, dom)
            except Exception:
                pass
        return detail

    def similar(
        self,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 20,
    ) -> list[AppSummary]:
        url = self._build_store_url(app_id, country=country, lang=lang)
        try:
            dom = self._run_with_retry(
                self._request_text,
                url,
                max_attempts=3,
            )
        except Exception as exc:
            raise ServiceError(NETWORK_ERROR_MESSAGE) from exc

        items = self._parse_similar_cards(dom, country=country, lang=lang, limit=limit)
        if not items:
            raise ServiceError(EMPTY_RESULT_MESSAGE)
        return items

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
        normalized_type, collection = self._normalize_chart_type(chart_type)
        normalized_category = self._normalize_chart_category(category)
        fetch_limit = max(1, min(limit, 500))
        url = self._CHART_URL_TEMPLATE.format(lang=lang, country=country)
        body = self._build_chart_body(fetch_limit, collection, normalized_category)
        headers = {
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "User-Agent": "Mozilla/5.0",
        }
        try:
            response = self._run_with_retry(
                self._request_text,
                url,
                max_attempts=3,
                method="POST",
                data=body.encode("utf-8"),
                headers=headers,
            )
        except Exception as exc:
            raise ServiceError(NETWORK_ERROR_MESSAGE) from exc

        items = self._parse_chart_response(
            response,
            chart_type=normalized_type,
            category=normalized_category,
            country=country,
            lang=lang,
        )
        if not items:
            raise ServiceError(EMPTY_RESULT_MESSAGE)
        return items[:limit]

    def list_analyze(
        self,
        chart_type: str,
        category: str | None = None,
        country: str = "us",
        lang: str = "en",
        limit: int = 100,
    ) -> list[ChartItem]:
        if self._gplay_scraper is None:
            return self.chart(chart_type=chart_type, category=category, country=country, lang=lang, limit=limit)
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

    def _map_summary(self, raw: dict[str, Any]) -> AppSummary:
        summary = normalize_app_summary(raw)
        if summary.min_installs is None:
            min_installs, _ = parse_install_range(raw.get("installs"))
            summary.min_installs = min_installs
        return summary

    def _try_map_summary(self, raw: dict[str, Any]) -> AppSummary | None:
        app_id = raw.get("appId") or raw.get("app_id")
        if not app_id:
            return None
        return self._map_summary(raw)

    def _map_detail(self, raw: dict[str, Any]) -> AppDetail:
        detail = normalize_app_detail(raw)
        if detail.android_version is None:
            detail.android_version = raw.get("androidVersionText")
        return detail

    def _map_review(self, app_id: str, raw: dict[str, Any]) -> ReviewItem:
        return normalize_review(raw, app_id)

    def _format_price(self, price: Any, currency: str | None, free: bool | None) -> str | None:
        if free:
            return "Free"
        if price in (None, ""):
            return None
        if isinstance(price, (int, float)) and currency:
            return f"{currency} {price:.2f}"
        return str(price)

    def _to_text(self, value: Any) -> str | None:
        if value is None:
            return None
        return str(value)

    def _needs_dom_enrichment(self, detail: AppDetail) -> bool:
        updated = detail.updated or ""
        return updated.isdigit() or not detail.updated or not detail.changelog

    def _enrich_detail_from_dom(self, detail: AppDetail, dom: str) -> None:
        updated_match = re.search(r"Updated on</div><div class=\"xg1aie\">([^<]+)</div>", dom)
        if updated_match:
            detail.updated = html.unescape(updated_match.group(1)).strip()

        whats_new_match = re.search(
            r"(?:What.?s new|What&#39;s new|What\\u0027s new)</(?:div|h2)>.*?"
            r"<div class=\"bARER\">(.*?)</div>",
            dom,
            re.DOTALL,
        )
        if whats_new_match:
            changelog = re.sub(r"<[^>]+>", " ", whats_new_match.group(1))
            detail.changelog = html.unescape(" ".join(changelog.split())).strip() or detail.changelog

    def _parse_search_dom(self, dom: str, n_hits: int) -> list[dict[str, Any]]:
        matches = self._Regex.SCRIPT.findall(dom)
        dataset = {}

        for match in matches:
            key_match = self._Regex.KEY.findall(match)
            value_match = self._Regex.VALUE.findall(match)
            if key_match and value_match:
                dataset[key_match[0]] = json.loads(value_match[0])

        try:
            top_result = dataset["ds:4"][0][1][0][23][16]
        except Exception:
            top_result = None

        search_dataset = None
        for idx in range(len(dataset.get("ds:4", [[[], []]])[0][1])):
            try:
                search_dataset = dataset["ds:4"][0][1][idx][22][0]
                break
            except Exception:
                continue

        if search_dataset is None:
            return []

        limit = min(len(search_dataset), n_hits)
        results = (
            [
                {
                    key: spec.extract_content(top_result)
                    for key, spec in self._ElementSpecs.SearchResultOnTop.items()
                }
            ]
            if top_result
            else []
        )
        for app_idx in range(limit - len(results)):
            app = {}
            for key, spec in self._ElementSpecs.SearchResult.items():
                app[key] = spec.extract_content(search_dataset[app_idx])
            results.append(app)
        return results

    def _json_safe(self, raw: dict[str, Any]) -> dict[str, Any]:
        try:
            return json.loads(json.dumps(raw, default=self._to_text))
        except TypeError as exc:
            raise ServiceError(DATA_ERROR_MESSAGE) from exc

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
        try:
            with urlopen_proxied(request, timeout=30, proxy=proxy) as response:
                return response.read().decode("utf-8")
        except Exception:
            curl = shutil.which("curl")
            if not curl:
                raise
            args = [curl, "-sS", "-L", "--http1.1"]
            if proxy:
                args.extend(["--proxy", proxy])
            args.append(url)
            for key, value in request_headers.items():
                args.extend(["-H", f"{key}: {value}"])
            if method.upper() != "GET":
                args.extend(["-X", method.upper()])
            if data is not None:
                args.extend(["--data-binary", data.decode("utf-8")])
            completed = proc.run(
                args,
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return completed.stdout

    def _parse_similar_cards(
        self,
        dom: str,
        country: str,
        lang: str,
        limit: int,
    ) -> list[AppSummary]:
        section = self._extract_similar_section(dom)
        pattern = re.compile(
            r'<a class="Si6A0c[^"]*" href="/store/apps/details\?id=(?P<app_id>[^"&]+)".*?</a>',
            re.S,
        )
        seen: set[str] = set()
        items: list[AppSummary] = []
        for match in pattern.finditer(section):
            app_id = html.unescape(match.group("app_id"))
            if app_id in seen:
                continue
            seen.add(app_id)
            block = match.group(0)
            items.append(
                AppSummary(
                    app_id=app_id,
                    title=self._search_html_field(block, r'<span class="DdYX5">(.*?)</span>'),
                    developer=self._search_html_field(block, r'<span class="wMUdtb">(.*?)</span>'),
                    rating=self._to_float(self._search_html_field(block, r'<span class="w2kbF">([\d.]+)</span>')),
                    icon_url=self._search_html_field(block, r'<img src="([^"]+)"'),
                    store_url=self._build_store_url(app_id, country=country, lang=lang),
                    raw={
                        "source": "similar_html",
                    },
                )
            )
            if len(items) >= limit:
                break
        return items

    def _extract_similar_section(self, dom: str) -> str:
        markers = (
            "Similar apps</span></h2>",
            "Similar games</span></h2>",
            "Similar apps",
            "Similar games",
        )
        start = -1
        for marker in markers:
            start = dom.find(marker)
            if start != -1:
                break
        if start == -1:
            return dom
        end = dom.find("</section>", start)
        if end == -1:
            end = start + 25000
        return dom[start:end]

    def _build_chart_body(self, limit: int, collection: str, category: str) -> str:
        template = gzip.decompress(base64.b64decode(self._CHART_BODY_TEMPLATE_B64)).decode("utf-8")
        return (
            template.replace("${num}", str(limit))
            .replace("${collection}", collection)
            .replace("${category}", category)
        )

    def _parse_chart_response(
        self,
        response: str,
        chart_type: str,
        category: str,
        country: str,
        lang: str,
    ) -> list[ChartItem]:
        payload = None
        for line in response.splitlines():
            stripped = line.strip()
            if not stripped.startswith("["):
                continue
            try:
                data = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if not data or not isinstance(data[0], list) or len(data[0]) < 3:
                continue
            nested = data[0][2]
            if not isinstance(nested, str):
                continue
            try:
                payload = json.loads(nested)
            except json.JSONDecodeError:
                continue
            break

        if payload is None:
            raise ServiceError(DATA_ERROR_MESSAGE)

        raw_items = self._get_in(payload, [0, 1, 0, 28, 0], default=[])
        items: list[ChartItem] = []
        for index, raw_item in enumerate(raw_items, start=1):
            app_id = self._get_in(raw_item, [0, 0, 0])
            if not app_id:
                continue
            items.append(
                ChartItem(
                    rank=index,
                    chart_type=chart_type,
                    category=category,
                    country=country,
                    lang=lang,
                    app_id=app_id,
                    title=self._get_in(raw_item, [0, 3]),
                    developer=self._get_in(raw_item, [0, 14]),
                    rating=self._to_float(self._get_in(raw_item, [0, 4, 1])),
                    installs=self._get_in(raw_item, [0, 15]),
                    price=self._chart_price(raw_item),
                    free=self._chart_is_free(raw_item),
                    icon_url=self._get_in(raw_item, [0, 1, 3, 2]),
                    store_url=urljoin(self._PLAY_BASE_URL, self._get_in(raw_item, [0, 10, 4, 2], default="")),
                    raw={"payload": raw_item},
                )
            )
        return items

    def _normalize_chart_type(self, chart_type: str) -> tuple[str, str]:
        normalized = (chart_type or "top_free").strip().lower()
        collection = self._CHART_COLLECTION_MAP.get(normalized)
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

    def _chart_price(self, raw_item: list[Any]) -> str | None:
        micros = self._get_in(raw_item, [0, 8, 1, 0, 0])
        currency = self._get_in(raw_item, [0, 8, 1, 0, 1])
        if micros in (None, ""):
            return None
        try:
            value = float(micros) / 1_000_000
        except (TypeError, ValueError):
            return None
        if value == 0:
            return "Free"
        if currency:
            return f"{currency} {value:.2f}"
        return f"{value:.2f}"

    def _chart_is_free(self, raw_item: list[Any]) -> bool | None:
        micros = self._get_in(raw_item, [0, 8, 1, 0, 0])
        if micros is None:
            return None
        try:
            return float(micros) == 0
        except (TypeError, ValueError):
            return None

    def _clean_html_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = re.sub(r"<[^>]+>", "", html.unescape(value))
        return cleaned.strip() or None

    def _search_html_field(self, source: str, pattern: str) -> str | None:
        match = re.search(pattern, source, re.S)
        if not match:
            return None
        return self._clean_html_text(match.group(1))

    def _to_float(self, value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _get_in(self, data: Any, path: list[int], default: Any = None) -> Any:
        current = data
        for key in path:
            try:
                current = current[key]
            except (TypeError, KeyError, IndexError):
                return default
        return current

    def _run_with_retry(self, fn, *args, **kwargs):
        max_attempts = kwargs.pop("max_attempts", 2)
        last_error = None
        for attempt in range(max_attempts):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                last_error = exc
                if attempt < max_attempts - 1:
                    time.sleep(self.request_delay_seconds * (2 ** attempt))
                    continue
                raise
        raise last_error
