from __future__ import annotations

from app.constants import DEFAULT_SETTINGS
from app.db.repositories import AlertRepository


class AlertService:
    def __init__(self, database, settings_service=None):
        self.database = database
        self.settings_service = settings_service
        self.repository = AlertRepository()

    def _threshold(self, key: str) -> float:
        """Read a numeric alert threshold from settings, falling back to the default.
        Never raises — a malformed stored value degrades to the shipped default."""
        raw = DEFAULT_SETTINGS.get(key)
        if self.settings_service is not None:
            raw = self.settings_service.get(key, raw)
        try:
            return float(raw)
        except (TypeError, ValueError):
            return float(DEFAULT_SETTINGS[key])

    def unread_count(self) -> int:
        with self.database.session() as session:
            return self.repository.unread_count(session)

    def mark_all_read(self) -> int:
        with self.database.session() as session:
            return self.repository.mark_all_read(session)

    def recent_alerts(self, limit: int = 10, severity: str | None = None):
        with self.database.session() as session:
            return self.repository.list_recent(session, limit=limit, severity=severity)

    def list_alerts(
        self,
        app_id: str | None = None,
        alert_type: str | None = None,
        severity: str | None = None,
        is_read: int | None = None,
        limit: int = 200,
    ):
        with self.database.session() as session:
            return self.repository.list_filtered(
                session,
                app_id=app_id,
                alert_type=alert_type,
                severity=severity,
                is_read=is_read,
                limit=limit,
            )

    def distinct_alert_apps(self) -> list[str]:
        with self.database.session() as session:
            return self.repository.distinct_app_ids(session)

    def mark_read(self, ids: list[int]) -> int:
        with self.database.session() as session:
            return self.repository.mark_read_by_ids(session, ids)
