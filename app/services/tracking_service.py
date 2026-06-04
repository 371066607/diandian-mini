from __future__ import annotations

import logging

from app.db.repositories import SnapshotRepository, TrackingRepository
from app.utils.time_utils import now_iso


class TrackingService:
    def __init__(
        self,
        database,
        google_play_service,
        keyword_service=None,
        alert_service=None,
        settings_service=None,
    ):
        self.database = database
        self.google_play_service = google_play_service
        self.keyword_service = keyword_service
        self.alert_service = alert_service
        self.settings_service = settings_service
        self.tracking_repository = TrackingRepository()
        self.snapshot_repository = SnapshotRepository()
        self.logger = logging.getLogger(__name__)

    def add_app(self, app_id: str, country: str = "us", lang: str = "en") -> None:
        with self.database.session() as session:
            self.tracking_repository.add_app(session, app_id, None, country, lang)

    def remove_app(self, app_id: str, country: str = "us", lang: str = "en") -> None:
        with self.database.session() as session:
            self.tracking_repository.remove_app(session, app_id, country, lang)

    def list_apps(self):
        with self.database.session() as session:
            return self.tracking_repository.list_apps(session)

    def add_keyword(self, keyword: str, app_id: str, country: str = "us", lang: str = "en") -> None:
        with self.database.session() as session:
            self.tracking_repository.add_keyword(session, keyword, app_id, country, lang)

    def list_keywords(self):
        with self.database.session() as session:
            return self.tracking_repository.list_keywords(session)

    def remove_keyword(self, keyword: str, app_id: str, country: str = "us", lang: str = "en") -> int:
        with self.database.session() as session:
            return self.tracking_repository.remove_keyword(session, keyword, app_id, country, lang)

    def toggle_app(self, app_id: str, country: str = "us", lang: str = "en") -> bool:
        with self.database.session() as session:
            apps = self.tracking_repository.list_apps(session)
            current = next(
                (
                    item
                    for item in apps
                    if item.app_id == app_id and item.country == country and item.lang == lang
                ),
                None,
            )
            next_enabled = not bool(current.enabled) if current is not None else True
            return self.tracking_repository.set_app_enabled(
                session,
                app_id,
                country,
                lang,
                next_enabled,
            )

    def toggle_keyword(
        self,
        keyword: str,
        app_id: str,
        country: str = "us",
        lang: str = "en",
    ) -> bool:
        with self.database.session() as session:
            keywords = self.tracking_repository.list_keywords(session)
            current = next(
                (
                    item
                    for item in keywords
                    if item.keyword == keyword
                    and item.app_id == app_id
                    and item.country == country
                    and item.lang == lang
                ),
                None,
            )
            next_enabled = not bool(current.enabled) if current is not None else True
            return self.tracking_repository.set_keyword_enabled(
                session,
                keyword,
                app_id,
                country,
                lang,
                next_enabled,
            )

    def sync_app_now(self, app_id: str, country: str = "us", lang: str = "en"):
        try:
            detail = self.google_play_service.app_detail(app_id, country=country, lang=lang)
        except Exception as exc:
            self.logger.exception(
                "sync_app_now failed for %s (%s/%s)",
                app_id,
                country,
                lang,
            )
            if self.alert_service is not None:
                self.alert_service.record_fetch_failure(
                    app_id,
                    str(exc),
                    country=country,
                    lang=lang,
                )
            raise
        with self.database.session() as session:
            previous_snapshot = self.snapshot_repository.latest(session, app_id, country, lang)
            self.tracking_repository.add_app(session, app_id, detail.title, country, lang)
            self.snapshot_repository.save_detail(session, detail, country, lang)
            self.tracking_repository.update_sync_time(session, app_id, country, lang, now_iso())
            if self.alert_service is not None:
                self.alert_service.create_snapshot_alerts(session, previous_snapshot, detail)
        return detail

    def sync_all_apps(self) -> int:
        tracked_apps = self.list_apps()
        count = 0
        for item in tracked_apps:
            if not item.enabled:
                continue
            try:
                self.sync_app_now(item.app_id, country=item.country, lang=item.lang)
                count += 1
            except Exception:
                self.logger.exception(
                    "sync_all_apps failed for %s (%s/%s)",
                    item.app_id,
                    item.country,
                    item.lang,
                )
                continue
        return count

    def sync_keyword_now(
        self,
        keyword: str,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        limit: int | None = None,
    ):
        if self.keyword_service is None:
            raise RuntimeError("KeywordService 未注入。")
        effective_limit = limit or self._default_keyword_limit()
        try:
            result = self.keyword_service.rank(
                keyword,
                app_id,
                country=country,
                lang=lang,
                limit=effective_limit,
            )
        except Exception as exc:
            self.logger.exception(
                "sync_keyword_now failed for %s / %s (%s/%s)",
                keyword,
                app_id,
                country,
                lang,
            )
            if self.alert_service is not None:
                self.alert_service.record_fetch_failure(
                    app_id,
                    str(exc),
                    title=f"关键词 {keyword}",
                    country=country,
                    lang=lang,
                )
            raise
        with self.database.session() as session:
            self.tracking_repository.add_keyword(session, keyword, app_id, country, lang)
            self.tracking_repository.update_keyword_sync_time(
                session,
                keyword,
                app_id,
                country,
                lang,
                now_iso(),
            )
        return result

    def sync_all_keywords(self) -> int:
        tracked_keywords = self.list_keywords()
        count = 0
        for item in tracked_keywords:
            if not item.enabled:
                continue
            try:
                self.sync_keyword_now(
                    item.keyword,
                    item.app_id,
                    country=item.country,
                    lang=item.lang,
                )
                count += 1
            except Exception:
                self.logger.exception(
                    "sync_all_keywords failed for %s / %s (%s/%s)",
                    item.keyword,
                    item.app_id,
                    item.country,
                    item.lang,
                )
                continue
        return count

    def sync_all(self) -> dict[str, int]:
        return {
            "apps": self.sync_all_apps(),
            "keywords": self.sync_all_keywords(),
        }

    def get_history(self, app_id: str, country: str = "us", lang: str = "en"):
        with self.database.session() as session:
            return self.snapshot_repository.get_history(session, app_id, country, lang)

    def _default_keyword_limit(self) -> int:
        if self.settings_service is None:
            return 100
        raw = self.settings_service.get("default_limit", "100") or "100"
        try:
            return int(raw)
        except ValueError:
            return 100
