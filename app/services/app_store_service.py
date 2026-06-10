from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.constants import EMPTY_RESULT_MESSAGE, NETWORK_ERROR_MESSAGE, NOT_FOUND_MESSAGE
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
    ) -> list[AppSummary]:
        data = self._get_json(
            self._SEARCH_URL,
            {"term": keyword, "country": country, "entity": "software", "limit": min(limit, 200)},
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

    def _get_json(self, url: str, params: dict) -> dict:
        if params:
            url = f"{url}?{urlencode(params)}"
        req = Request(url, headers=self._HEADERS)
        try:
            if self.request_delay_seconds > 0:
                time.sleep(self.request_delay_seconds)
            with urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise ServiceError(NETWORK_ERROR_MESSAGE) from exc
