from __future__ import annotations

import html
import json
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request

from app.constants import EMPTY_RESULT_MESSAGE, NETWORK_ERROR_MESSAGE, NOT_FOUND_MESSAGE
from app.utils.network import urlopen_proxied
from app.schemas.app_schema import AppDetail, AppSummary
from app.schemas.chart_schema import ChartItem
from app.schemas.review_schema import ReviewItem


class ServiceError(RuntimeError):
    pass


class AppStoreService:
    _SEARCH_URL = "https://itunes.apple.com/search"
    _LOOKUP_URL = "https://itunes.apple.com/lookup"
    _REVIEWS_URL = "https://itunes.apple.com/{country}/rss/customerreviews/page={page}/id={app_id}/sortBy=mostRecent/json"
    _CHART_URLS = {
        "top_free": "https://itunes.apple.com/{country}/rss/topfreeapplications/limit={limit}/json",
        "top_paid": "https://itunes.apple.com/{country}/rss/toppaidapplications/limit={limit}/json",
        "top_grossing": "https://itunes.apple.com/{country}/rss/topgrossingapplications/limit={limit}/json",
    }
    _HINTS_URL = "https://search.itunes.apple.com/WebObjects/MZSearchHints.woa/wa/hints"
    # App Store autocomplete needs an X-Apple-Store-Front header to localize hints.
    # country -> storefront id (the "-1,29" lang/platform suffix is appended at use).
    _STOREFRONTS = {
        "us": "143441", "gb": "143444", "ca": "143455", "au": "143460",
        "de": "143443", "fr": "143442", "jp": "143462", "cn": "143465",
        "kr": "143466", "hk": "143463", "tw": "143470", "sg": "143464",
        "in": "143467", "br": "143503", "mx": "143468", "es": "143454",
        "it": "143450", "ru": "143469", "nl": "143452",
    }
    _HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
    }

    def __init__(self, request_delay_seconds: float = 0.5) -> None:
        self.request_delay_seconds = max(0.0, request_delay_seconds)

    def search(
        self,
        keyword: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 20,
        proxy: str | None = None,
    ) -> list[AppSummary]:
        data = self._get_json(
            self._SEARCH_URL,
            {"term": keyword, "country": country, "entity": "software", "limit": min(limit, 200)},
            proxy=proxy,
        )
        results = data.get("results", [])
        if not results:
            raise ServiceError(EMPTY_RESULT_MESSAGE)
        return [self._map_summary(r) for r in results]

    def app_detail(
        self,
        app_id: str,
        country: str = "us",
        lang: str = "en",
    ) -> AppDetail:
        # numeric = iTunes trackId, otherwise treat as bundleId
        params: dict[str, Any] = {"country": country, "entity": "software"}
        if app_id.lstrip("-").isdigit():
            params["id"] = app_id
        else:
            params["bundleId"] = app_id
        data = self._get_json(self._LOOKUP_URL, params)
        results = data.get("results", [])
        if not results:
            raise ServiceError(NOT_FOUND_MESSAGE)
        return self._map_detail(results[0], country=country)

    def reviews(
        self,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        sort: str = "newest",
        continuation_token=None,
    ) -> tuple[list[ReviewItem], object]:
        page = int(continuation_token) if continuation_token else 1
        url = self._REVIEWS_URL.format(country=country, page=page, app_id=app_id)
        try:
            data = self._get_json(url, {})
        except ServiceError:
            return [], None
        feed = data.get("feed", {})
        entries = feed.get("entry", [])
        if not isinstance(entries, list):
            entries = [entries] if entries else []
        items = [self._map_review(app_id, e) for e in entries]
        next_token = None
        for link in feed.get("link", []):
            if isinstance(link, dict) and link.get("attributes", {}).get("rel") == "next":
                next_token = page + 1
                break
        return items, next_token

    def chart(
        self,
        chart_type: str,
        category: str | None = None,
        country: str = "us",
        lang: str = "en",
        limit: int = 100,
    ) -> list[ChartItem]:
        url_tpl = self._CHART_URLS.get(chart_type, self._CHART_URLS["top_free"])
        url = url_tpl.format(country=country, limit=min(limit, 200))
        if category:
            url = url.replace("/json", f"/genre={category}/json")
        data = self._get_json(url, {})
        entries = data.get("feed", {}).get("entry", [])
        if not entries:
            raise ServiceError(EMPTY_RESULT_MESSAGE)
        items = [
            item
            for rank, e in enumerate(entries, 1)
            if (item := self._map_chart_entry(e, rank=rank, chart_type=chart_type, country=country, lang=lang))
        ]
        return items[:limit]

    def similar(
        self,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 20,
    ) -> list[AppSummary]:
        return []

    def permissions(self, app_id: str, country: str = "us", lang: str = "en") -> dict[str, list[str]]:
        return {}

    def suggest(
        self,
        term: str,
        country: str = "us",
        lang: str = "en",
        count: int = 8,
    ) -> list[str]:
        """App Store search autocomplete via MZSearchHints. Best-effort: returns []
        on any failure, since suggestions only enrich the keyword-coverage pool."""
        term = (term or "").strip()
        if not term:
            return []
        storefront = self._STOREFRONTS.get((country or "us").lower(), "143441")
        url = f"{self._HINTS_URL}?clientApplication=Software&term={quote(term)}"
        req = Request(
            url,
            headers={
                "Accept": "text/xml",
                "User-Agent": "iTunes-iPhone/12.0",
                "X-Apple-Store-Front": f"{storefront}-1,29",
            },
        )
        try:
            if self.request_delay_seconds > 0:
                time.sleep(self.request_delay_seconds)
            with urlopen_proxied(req, timeout=15) as resp:
                text = resp.read().decode("utf-8", errors="replace")
        except Exception:
            return []
        # The plist lists alternating <string>hint</string><string>store-url</string>;
        # keep the hint phrases, drop the "Suggestions" title and the URL entries.
        hints: list[str] = []
        for raw in re.findall(r"<string>([^<]*)</string>", text):
            val = html.unescape(raw).strip()
            if not val or val.lower() == "suggestions" or val.startswith("http"):
                continue
            hints.append(val)
            if len(hints) >= count:
                break
        return hints

    # --- internal mapping ---

    def _map_summary(self, raw: dict[str, Any]) -> AppSummary:
        price = raw.get("price")
        # iTunes lookup has no reliable IAP flag — None (unknown) beats a false 否.
        has_iap = bool(raw["inAppPurchase"]) if "inAppPurchase" in raw else None
        return AppSummary(
            platform="app_store",
            app_id=str(raw.get("trackId", raw.get("bundleId", ""))),
            title=raw.get("trackName"),
            developer=raw.get("artistName"),
            developer_id=str(raw.get("artistId", "")),
            category=raw.get("primaryGenreName"),
            summary=(raw.get("description") or "")[:200] or None,
            rating=raw.get("averageUserRating"),
            score_text=f"{raw.get('averageUserRating', ''):.1f}" if raw.get("averageUserRating") else None,
            ratings_count=raw.get("userRatingCount"),
            reviews_count=raw.get("userRatingCount"),
            price="Free" if price == 0 else (f"{raw.get('currency', '')} {price:.2f}".strip() if price else None),
            currency=raw.get("currency"),
            free=price == 0,
            has_iap=has_iap,
            icon_url=raw.get("artworkUrl512") or raw.get("artworkUrl100"),
            store_url=raw.get("trackViewUrl"),
            raw=raw,
        )

    def _map_detail(self, raw: dict[str, Any], country: str = "us") -> AppDetail:
        base = self._map_summary(raw)
        screenshots = raw.get("screenshotUrls") or raw.get("ipadScreenshotUrls") or []
        return AppDetail(
            **base.model_dump(),
            version=raw.get("version"),
            updated=(raw.get("currentVersionReleaseDate") or "")[:10] or None,
            released=(raw.get("releaseDate") or "")[:10] or None,
            content_rating=raw.get("contentAdvisoryRating"),
            description=raw.get("description"),
            changelog=raw.get("releaseNotes"),
            screenshots=screenshots[:12],
            developer_website=raw.get("sellerUrl"),
            header_image=raw.get("artworkUrl512"),
            genre_id=str(raw.get("primaryGenreId", "")),
            categories=raw.get("genres", []),
            available=True,
            app_age_days=self._age_days(raw.get("releaseDate")),
            app_bundle=raw.get("bundleId"),
            content_rating_description=raw.get("contentAdvisoryRating"),
            original_price=raw.get("price") or None,
            developer_address=raw.get("sellerName"),
            publisher_country=country,
        )

    @staticmethod
    def _age_days(release_date: str | None) -> int | None:
        if not release_date:
            return None
        try:
            released = datetime.fromisoformat(release_date.replace("Z", "+00:00"))
        except ValueError:
            return None
        return max(0, (datetime.now(timezone.utc) - released).days)

    def _map_review(self, app_id: str, raw: dict[str, Any]) -> ReviewItem:
        def _lbl(field: Any) -> str | None:
            return field.get("label") if isinstance(field, dict) else None

        return ReviewItem(
            platform="app_store",
            app_id=app_id,
            review_id=_lbl(raw.get("id", {})),
            user_name=_lbl((raw.get("author") or {}).get("name", {})),
            rating=int(_lbl(raw.get("im:rating", {})) or 0) or None,
            content=_lbl(raw.get("content", {})),
            app_version=_lbl(raw.get("im:version", {})),
            review_created_at=_lbl(raw.get("updated", {})),
        )

    def _map_chart_entry(
        self,
        entry: dict[str, Any],
        rank: int,
        chart_type: str,
        country: str,
        lang: str,
    ) -> ChartItem | None:
        def _lbl(field: Any) -> str | None:
            return field.get("label") if isinstance(field, dict) else None

        try:
            numeric_id = entry.get("id", {}).get("attributes", {}).get("im:id", "")
            title = _lbl(entry.get("im:name", {}))
            artist = _lbl(entry.get("im:artist", {}))
            cat_attrs = (entry.get("category") or {}).get("attributes", {})
            category = cat_attrs.get("label") if cat_attrs else None
            images = entry.get("im:image", [])
            icon_url = _lbl(images[-1]) if images else None
            price_attrs = (entry.get("im:price") or {}).get("attributes", {})
            price_amt = price_attrs.get("amount")
            currency = price_attrs.get("currency")
            free = price_amt == "0.00" if price_amt is not None else None
            price = "Free" if free else (f"{currency} {price_amt}".strip() if price_amt else None)
            return ChartItem(
                platform="app_store",
                app_id=str(numeric_id),
                title=title,
                developer=artist,
                category=category,
                price=price,
                free=free,
                icon_url=icon_url,
                rank=rank,
                chart_type=chart_type,
                country=country,
                lang=lang,
            )
        except Exception:
            return None

    def _get_json(self, url: str, params: dict, proxy: str | None = None) -> dict:
        if params:
            url = f"{url}?{urlencode(params)}"
        req = Request(url, headers=self._HEADERS)
        try:
            if self.request_delay_seconds > 0:
                time.sleep(self.request_delay_seconds)
            with urlopen_proxied(req, timeout=20, proxy=proxy) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise ServiceError(NETWORK_ERROR_MESSAGE) from exc
