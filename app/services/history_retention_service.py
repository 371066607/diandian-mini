from __future__ import annotations

from datetime import datetime


class HistoryRetentionService:
    """Prunes append-only time-series history (snapshots / keyword ranks / read alerts).

    Retention is now a structural no-op: scraping is retired and nothing writes new
    history into the tables this service used to prune, so there is nothing left to
    delete. Kept only so existing callers can still construct and call it.
    """

    def __init__(self, database, settings_service=None):
        self.database = database
        self.settings_service = settings_service

    def cleanup(self, now: datetime | None = None) -> dict[str, int]:
        """No-op: always returns a zero count per category.

        ``now`` is accepted for backward compatibility but unused.
        """
        return {"snapshots": 0, "keywords": 0, "charts": 0, "alerts": 0, "reviews": 0}
