from __future__ import annotations

from typing import Any


class ChartController:
    """Domain logic for fetching/saving chart rankings, shared between API
    mode (cache-or-refresh-job) and legacy/offline mode (local chart_service).
    Needs a reference to the bridge for the shared _store_intel_api/
    _request_api_refresh helpers. QmlBridge owns the Slot surface, async
    dispatch (_run), chart state, and signal emission.
    """

    def __init__(self, bridge) -> None:
        self.bridge = bridge

    def fetch(self, ctx: dict[str, Any], limit_value: int) -> dict[str, Any]:
        api = self.bridge._store_intel_api(ctx["platform"])
        if api is None:
            return {
                "items": self.bridge.services["chart_service"].fetch(
                    ctx["chart_type"],
                    ctx["category"],
                    ctx["country"],
                    ctx["lang"],
                    limit_value,
                    platform=ctx["platform"],
                ),
                "queued": False,
            }
        try:
            items = api.fetch_chart_cached(
                ctx["chart_type"],
                ctx["category"],
                ctx["country"],
                ctx["lang"],
                limit_value,
                platform=ctx["platform"],
            )
        except Exception:
            items = []
        queued = False
        if not items:
            self.bridge._request_api_refresh(
                api,
                "chart",
                collection=ctx["chart_type"],
                category=ctx["category"],
                country=ctx["country"],
                lang=ctx["lang"],
                limit=limit_value,
                platform=ctx["platform"],
            )
            items = api.fetch_chart_cached(
                ctx["chart_type"],
                ctx["category"],
                ctx["country"],
                ctx["lang"],
                limit_value,
                platform=ctx["platform"],
            )
        if not items:
            raise RuntimeError("服务器没有返回可用的榜单数据。")
        return {"items": items, "queued": queued}

    def save_legacy(self, ctx: dict[str, Any], items: list[Any]) -> int:
        """Persist a chart snapshot locally — legacy/offline mode only (API
        mode maintains snapshots server-side, see QmlBridge.saveChartSnapshot)."""
        return self.bridge.services["chart_service"].save(
            ctx["chart_type"], ctx["category"], ctx["country"], ctx["lang"], items
        )
