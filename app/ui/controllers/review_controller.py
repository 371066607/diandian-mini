from __future__ import annotations

from typing import Any


class ReviewController:
    """Domain logic for fetching/saving reviews, shared between API mode
    (the backend's cache-or-refresh-job flow) and legacy/offline mode (the
    per-platform local review services). Needs a reference to the bridge
    rather than just `services`: fetching a page routes through the
    bridge's shared _store_intel_api/_request_api_refresh helpers, which
    every domain uses, not just reviews. QmlBridge owns the actual Slot
    surface, async dispatch (_run), reviews state, and signal emission.
    """

    def __init__(self, bridge) -> None:
        self.bridge = bridge

    def fetch_page(self, ctx: dict[str, str], token) -> tuple[list[Any], Any]:
        """Fetch one reviews page from the platform the context was created
        under, so a mid-flight platform switch can't mix sources."""
        platform = ctx.get("platform") or "google_play"
        api = self.bridge._store_intel_api(platform)
        if api is not None:
            if token is not None:
                return [], None
            items = api.list_cached_reviews(ctx["app_id"], limit=50, platform=platform)
            if not items:
                self.bridge._request_api_refresh(
                    api,
                    "reviews",
                    app_id=ctx["app_id"],
                    country=ctx["country"],
                    lang=ctx["lang"],
                    limit=50,
                    platform=platform,
                )
                items = api.list_cached_reviews(ctx["app_id"], limit=50, platform=platform)
            return items, None
        services = self.bridge.services
        if ctx.get("platform") == "app_store":
            return services["app_store_service"].reviews(
                ctx["app_id"],
                country=ctx["country"],
                lang=ctx["lang"],
                sort=ctx.get("sort", "newest"),
                continuation_token=token,
            )
        return services["review_service"].fetch(
            ctx["app_id"], ctx["country"], ctx["lang"], ctx.get("sort", "newest"), token
        )

    def save(self, app_id: str, country: str, lang: str, items: list[Any], platform: str) -> int:
        api = self.bridge._store_intel_api(platform)
        if api is not None:
            return api.save_reviews(app_id, country, lang, items, platform=platform)
        return self.bridge.services["review_service"].save(app_id, country, lang, items)
