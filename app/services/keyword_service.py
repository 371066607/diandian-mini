from __future__ import annotations

from app.db.repositories import KeywordRankRepository
from app.schemas.keyword_schema import KeywordRankResult
from app.services.google_play_service import ServiceError, _FEATURE_RETIRED_MESSAGE
from app.utils.normalize import locate_rank
from app.utils.time_utils import now_iso


class KeywordService:
    def __init__(self, google_play_service, database=None, platform: str = "google_play"):
        # ``google_play_service`` is any service exposing ``.search`` — the App Store
        # instance is built with AppStoreService here, hence the ``platform`` tag.
        self.google_play_service = google_play_service
        self.database = database
        self.platform = platform
        self.repository = KeywordRankRepository()

    def search(
        self,
        keyword: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 50,
    ):
        return self.google_play_service.search(keyword, country, lang, limit)

    def rank(
        self,
        keyword: str,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 100,
    ) -> KeywordRankResult:
        results = self.search(keyword, country=country, lang=lang, limit=limit)
        rank = locate_rank(results, app_id)

        result = KeywordRankResult(
            keyword=keyword,
            app_id=app_id,
            country=country,
            lang=lang,
            platform=self.platform,
            found=rank is not None,
            rank=rank,
            checked_limit=limit,
            captured_at=now_iso(),
            results=results,
        )
        if self.database is not None:
            self.save_result(result)
        return result

    def history(self, keyword: str, app_id: str, country: str = "us", lang: str = "en"):
        if self.database is None:
            return []
        with self.database.session() as session:
            return self.repository.history(
                session, keyword, app_id, country, lang, platform=self.platform
            )

    def latest_rank(self, keyword: str, app_id: str, country: str = "us", lang: str = "en"):
        """The most recent rank snapshot for this keyword/app, or None if never synced."""
        if self.database is None:
            return None
        with self.database.session() as session:
            return self.repository.latest(
                session, keyword, app_id, country, lang, platform=self.platform
            )

    def latest_rank_bulk(self, tracked_keywords) -> dict:
        """Return {(keyword, app_id, country, lang, platform): rank_snapshot} for every
        tracked keyword — one DB query instead of one per keyword. Keys carry each row's
        OWN platform (not this service's), so one call serves a mixed-platform list."""
        if self.database is None or not tracked_keywords:
            return {}
        keys = [
            (kw.keyword, kw.app_id, kw.country, kw.lang, kw.platform) for kw in tracked_keywords
        ]
        with self.database.session() as session:
            return self.repository.latest_bulk(session, keys)

    def previous_distinct_rank(
        self, keyword: str, app_id: str, country: str = "us", lang: str = "en"
    ):
        """The most recent rank from a *prior* calendar day — the alert-diff baseline that
        a same-day re-sync can't mask."""
        if self.database is None:
            return None
        with self.database.session() as session:
            return self.repository.previous_distinct_day(
                session, keyword, app_id, country, lang, platform=self.platform
            )

    def save_result(self, result: KeywordRankResult) -> bool:
        raise ServiceError(_FEATURE_RETIRED_MESSAGE)
