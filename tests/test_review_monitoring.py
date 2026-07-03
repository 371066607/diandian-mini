"""Retirement guard: review monitoring depended on the scrape-persist flow (fetching
reviews live and diffing against persisted rows), which has been removed.
``ReviewService.monitor_reviews`` is now a permanent stub that always raises
``ServiceError``. (The sibling ``sync_app_now`` retirement is already covered by
tests/test_failure_escalation.py.)"""

from __future__ import annotations

import pytest

from app.db.database import Database
from app.services.google_play_service import ServiceError
from app.services.review_service import ReviewService


class ReviewsGP:
    """Minimal google_play_service stub; monitor_reviews raises before using it."""

    def reviews(self, app_id, country="us", lang="en", sort="newest", continuation_token=None):
        return ([], None)


def test_monitor_reviews_raises_retired_error(tmp_path):
    db = Database(str(tmp_path / "unit.sqlite3"))
    db.create_all()
    rs = ReviewService(db, ReviewsGP())
    with pytest.raises(ServiceError):
        rs.monitor_reviews("com.x", "us", "en", max_rating=2)
