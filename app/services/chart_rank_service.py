from __future__ import annotations

import logging

from app.db.repositories import ChartRankRepository
from app.schemas.chart_rank_schema import ChartRankResult
from app.services.google_play_service import ServiceError, _FEATURE_RETIRED_MESSAGE
from app.utils.time_utils import now_iso

logger = logging.getLogger(__name__)


class ChartRankService:
    """Monitors an app's rank within a Google Play chart (collection + category + country).

    Mirrors KeywordService: ``rank()`` fetches the chart, locates the target app's 1-based
    position, builds a ``ChartRankResult`` and (when a DB is configured) upserts one row per
    calendar day. ``previous_distinct_rank``/``latest_rank``/``history`` read the snapshots.
    """

    def __init__(self, google_play_service, database=None):
        self.google_play_service = google_play_service
        self.database = database
        self.repository = ChartRankRepository()

    def _fetch_chart(self, collection, category, country, lang, limit):
        """Fetch the chart via ``list_analyze``, falling back to ``chart`` on failure.

        Both return ``list[ChartItem]`` ordered by rank; ``list_analyze`` uses the library
        path and ``chart`` the raw batchexecute RPC, so trying the latter recovers when the
        library path is unavailable."""
        try:
            return self.google_play_service.list_analyze(
                collection, category=category, country=country, lang=lang, limit=limit
            )
        except Exception:
            logger.warning(
                "list_analyze failed for %s/%s, falling back to chart()", collection, category
            )
            return self.google_play_service.chart(
                collection, category=category, country=country, lang=lang, limit=limit
            )

    def rank(
        self,
        app_id: str,
        collection: str,
        category: str | None = "APPLICATION",
        country: str = "us",
        lang: str = "en",
        limit: int = 100,
    ) -> ChartRankResult:
        items = self._fetch_chart(collection, category, country, lang, limit)
        rank = None
        for item in items:
            if item.app_id == app_id:
                rank = item.rank
                break

        result = ChartRankResult(
            app_id=app_id,
            collection=collection,
            category=category,
            country=country,
            lang=lang,
            found=rank is not None,
            rank=rank,
            checked_limit=limit,
            captured_at=now_iso(),
        )
        if self.database is not None:
            self.save_result(result)
        return result

    def history(
        self,
        app_id: str,
        collection: str,
        category: str | None = "APPLICATION",
        country: str = "us",
        lang: str = "en",
    ):
        if self.database is None:
            return []
        with self.database.session() as session:
            return self.repository.history(session, app_id, collection, category, country, lang)

    def latest_rank(
        self,
        app_id: str,
        collection: str,
        category: str | None = "APPLICATION",
        country: str = "us",
        lang: str = "en",
    ):
        """The most recent rank snapshot for this chart/app, or None if never synced."""
        if self.database is None:
            return None
        with self.database.session() as session:
            return self.repository.latest(session, app_id, collection, category, country, lang)

    def previous_distinct_rank(
        self,
        app_id: str,
        collection: str,
        category: str | None = "APPLICATION",
        country: str = "us",
        lang: str = "en",
    ):
        """The most recent rank from a *prior* calendar day — the alert-diff baseline that
        a same-day re-sync can't mask."""
        if self.database is None:
            return None
        with self.database.session() as session:
            return self.repository.previous_distinct_day(
                session, app_id, collection, category, country, lang
            )

    def save_result(self, result: ChartRankResult) -> bool:
        """Persist a rank result with per-day dedup. Returns True if it was the first sync
        of the day (a new row), False if it overwrote an existing same-day row."""
        raise ServiceError(_FEATURE_RETIRED_MESSAGE)
