"""SnapshotRepository read-path coverage: previous_distinct_day must return the most
recent snapshot from a calendar day strictly before the reference day, never today's."""

from __future__ import annotations

from app.db.database import Database
from app.db.models import AppSnapshotModel
from app.db.repositories import SnapshotRepository


def test_previous_distinct_day_skips_today(tmp_path):
    db = Database(str(tmp_path / "prevday.sqlite3"))
    db.create_all()
    repo = SnapshotRepository()
    with db.session() as s:
        s.add(
            AppSnapshotModel(
                app_id="com.x",
                country="us",
                lang="en",
                captured_at="2020-01-01T08:00:00",
                rating=4.0,
            )
        )
        s.add(
            AppSnapshotModel(
                app_id="com.x",
                country="us",
                lang="en",
                captured_at="2020-01-02T08:00:00",
                rating=4.5,
            )
        )
    with db.session() as s:
        prev = repo.previous_distinct_day(s, "com.x", "us", "en", before_day="2020-01-02")
    assert prev is not None
    assert prev.rating == 4.0  # the prior day, never today
