from __future__ import annotations

from app.db.repositories import KeywordRankRepository
from app.schemas.keyword_schema import KeywordRankResult
from app.utils.time_utils import now_iso


class KeywordService:
    def __init__(self, google_play_service, database=None):
        self.google_play_service = google_play_service
        self.database = database
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
        rank = None
        for index, item in enumerate(results):
            if item.app_id == app_id:
                rank = index + 1
                break

        result = KeywordRankResult(
            keyword=keyword,
            app_id=app_id,
            country=country,
            lang=lang,
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
            return self.repository.history(session, keyword, app_id, country, lang)

    def latest_rank(self, keyword: str, app_id: str, country: str = "us", lang: str = "en"):
        """The most recent rank snapshot for this keyword/app, or None if never synced."""
        if self.database is None:
            return None
        with self.database.session() as session:
            return self.repository.latest(session, keyword, app_id, country, lang)

    def latest_rank_bulk(self, tracked_keywords) -> dict:
        """Return {(keyword, app_id, country, lang): rank_snapshot} for every tracked
        keyword — one DB query instead of one per keyword."""
        if self.database is None or not tracked_keywords:
            return {}
        keys = [(kw.keyword, kw.app_id, kw.country, kw.lang) for kw in tracked_keywords]
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
            return self.repository.previous_distinct_day(session, keyword, app_id, country, lang)

    def save_result(self, result: KeywordRankResult) -> bool:
        """Persist a rank result with per-day dedup. Returns True if it was the first sync
        of the day (a new row), False if it overwrote an existing same-day row."""
        if self.database is None:
            raise RuntimeError("当前 KeywordService 未配置数据库，无法保存结果。")
        with self.database.session() as session:
            return self.repository.upsert_for_day(session, result)
