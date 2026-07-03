from __future__ import annotations

from typing import Any


def has_search_display_data(item) -> bool:
    if item is None or not getattr(item, "app_id", ""):
        return False
    fields = ("developer", "rating", "ratings_count", "installs")
    return all(getattr(item, field, None) not in (None, "", [], {}) for field in fields)


def search_items_signature(items) -> tuple:
    fields = (
        "app_id",
        "title",
        "developer",
        "rating",
        "ratings_count",
        "installs",
        "price",
        "has_iap",
        "category",
        "summary",
        "icon_url",
    )
    return tuple(tuple(getattr(item, field, None) for field in fields) for item in (items or []))


class SearchController:
    """Domain logic for searching apps, shared between API mode (cache-or-
    refresh-job, with an optional background re-refresh when the cache hit
    is display-incomplete) and legacy/offline mode (the per-platform local
    store). Needs a reference to the bridge for the shared _store_intel_api/
    _request_api_refresh/_active_store helpers. QmlBridge owns the Slot
    surface, async dispatch (_run), search state, and signal emission.
    """

    def __init__(self, bridge) -> None:
        self.bridge = bridge

    def search(self, keyword: str, country: str, lang: str, limit: int, platform: str) -> dict[str, Any]:
        api = self.bridge._store_intel_api()
        if api is None:
            store = self.bridge._active_store()
            return {
                "items": store.search(keyword, country=country, lang=lang, limit=limit),
                "queued": False,
            }
        items = api.search_cached(keyword, country=country, lang=lang, limit=limit, platform=platform)
        had_cached_items = bool(items)
        if not items:
            self.bridge._request_api_refresh(
                api, "search", query=keyword, country=country, lang=lang, limit=limit, platform=platform
            )
            items = api.search_cached(keyword, country=country, lang=lang, limit=limit, platform=platform)
        return {
            "items": items,
            "queued": False,
            "refresh_in_background": had_cached_items
            and not all(has_search_display_data(item) for item in items),
        }

    def refresh_cache(self, api, keyword: str, country: str, lang: str, limit: int, platform: str) -> list[Any]:
        """Re-fetches a fresh copy of the search cache after triggering a
        refresh job — used to silently upgrade a display-incomplete cache
        hit in the background (see QmlBridge._refresh_search_cache_in_background)."""
        self.bridge._request_api_refresh(
            api, "search", query=keyword, country=country, lang=lang, limit=limit, platform=platform
        )
        return api.search_cached(keyword, country=country, lang=lang, limit=limit, platform=platform)
