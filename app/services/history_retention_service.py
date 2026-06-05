from __future__ import annotations

from datetime import datetime, timedelta

from app.constants import DEFAULT_SETTINGS
from app.db.repositories import (
    AlertRepository,
    ChartRankRepository,
    KeywordRankRepository,
    ReviewRepository,
    SnapshotRepository,
)


def _as_int(value, default: int) -> int:
    """Parse an int setting, falling back to ``default`` on any bad value."""
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


class HistoryRetentionService:
    """Prunes append-only time-series history (snapshots / keyword ranks / read alerts).

    Runs only in the background (after the daily sync), never on the UI thread. Always
    keeps the most-recent ``retention_min_keep`` rows per object regardless of age, so
    trends never go empty; unread alerts are never deleted.
    """

    def __init__(self, database, settings_service=None):
        self.database = database
        self.settings_service = settings_service
        self.snapshot_repository = SnapshotRepository()
        self.keyword_repository = KeywordRankRepository()
        self.chart_repository = ChartRankRepository()
        self.alert_repository = AlertRepository()
        self.review_repository = ReviewRepository()

    def cleanup(self, now: datetime | None = None) -> dict[str, int]:
        """Delete expired history per the retention settings.

        Returns the number of rows deleted per category. ``now`` is injectable so tests
        can construct over-age data with handwritten timestamps. A no-op (all zeros) when
        ``retention_enabled`` != "true".
        """
        result = {"snapshots": 0, "keywords": 0, "charts": 0, "alerts": 0, "reviews": 0}

        settings = self.settings_service.get_all() if self.settings_service is not None else {}

        def setting(key: str) -> str:
            value = settings.get(key)
            if value is None:
                return DEFAULT_SETTINGS[key]
            return value

        if str(setting("retention_enabled")).strip().lower() != "true":
            return result

        now = now or datetime.now()
        min_keep = _as_int(setting("retention_min_keep"), int(DEFAULT_SETTINGS["retention_min_keep"]))
        snapshot_days = _as_int(
            setting("snapshot_retention_days"), int(DEFAULT_SETTINGS["snapshot_retention_days"])
        )
        keyword_days = _as_int(
            setting("keyword_retention_days"), int(DEFAULT_SETTINGS["keyword_retention_days"])
        )
        alert_days = _as_int(
            setting("alert_retention_days"), int(DEFAULT_SETTINGS["alert_retention_days"])
        )
        review_days = _as_int(
            setting("review_retention_days"), int(DEFAULT_SETTINGS["review_retention_days"])
        )

        def cutoff(days: int) -> str:
            return (now - timedelta(days=days)).isoformat(timespec="seconds")

        with self.database.session() as session:
            result["snapshots"] = self.snapshot_repository.cleanup(
                session, cutoff(snapshot_days), min_keep
            )
            result["keywords"] = self.keyword_repository.cleanup(
                session, cutoff(keyword_days), min_keep
            )
            # Chart-rank snapshots reuse the keyword retention window (same cadence/volume).
            result["charts"] = self.chart_repository.cleanup(
                session, cutoff(keyword_days), min_keep
            )
            result["alerts"] = self.alert_repository.cleanup(session, cutoff(alert_days), min_keep)
            result["reviews"] = self.review_repository.cleanup(
                session, cutoff(review_days), min_keep
            )

        return result
