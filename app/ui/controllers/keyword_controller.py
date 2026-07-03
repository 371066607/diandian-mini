from __future__ import annotations

from typing import Any

# How many search-result positions a keyword-rank check looks through before
# giving up and reporting "not found". Also referenced by QmlBridge's keyword
# result formatting (the summary text quotes this same number).
KEYWORD_RANK_CHECK_LIMIT = 30


class KeywordController:
    """Domain logic for checking/saving a keyword rank, shared between API
    mode (cache-or-refresh-job) and legacy/offline mode (per-platform local
    keyword_service). Needs a reference to the bridge for the shared
    _request_api_refresh helper. QmlBridge owns the Slot surface, async
    dispatch (_run), keyword state, and signal emission.
    """

    def __init__(self, bridge) -> None:
        self.bridge = bridge

    def fetch_rank_api(
        self, api, keyword: str, app_id: str, country: str, lang: str, platform: str
    ) -> dict[str, Any]:
        result = api.cached_keyword_rank(
            keyword, app_id, country=country, lang=lang, limit=KEYWORD_RANK_CHECK_LIMIT, platform=platform
        )
        if result is None:
            self.bridge._request_api_refresh(
                api,
                "keyword_rank",
                keyword=keyword,
                app_id=app_id,
                country=country,
                lang=lang,
                limit=KEYWORD_RANK_CHECK_LIMIT,
                platform=platform,
            )
            result = api.cached_keyword_rank(
                keyword,
                app_id,
                country=country,
                lang=lang,
                limit=KEYWORD_RANK_CHECK_LIMIT,
                platform=platform,
            )
        if result is None:
            raise RuntimeError("服务器没有返回可用的关键词排名数据。")
        return {"result": result, "queued": False}

    def fetch_rank_legacy(self, keyword: str, app_id: str, country: str, lang: str, platform: str):
        # Strict lookup: a missing platform service must fail loudly, not
        # silently answer with Google Play data labeled as the other store.
        keyword_service = self.bridge.services[
            "keyword_service_app_store" if platform == "app_store" else "keyword_service"
        ]
        return keyword_service.rank(
            keyword, app_id, country=country, lang=lang, limit=KEYWORD_RANK_CHECK_LIMIT
        )

    def save_legacy(self, result) -> Any:
        return self.bridge.services["keyword_service"].save_result(result)
