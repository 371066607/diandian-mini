"""Per-day snapshot dedup: at most one snapshot per calendar day per app, the alert
diff baselines on the previous *different* day, and same-day re-syncs don't re-alert."""

from __future__ import annotations

from app.db.database import Database
from app.db.repositories import SnapshotRepository
from app.schemas.app_schema import AppDetail
from app.services.alert_service import AlertService
from app.services.settings_service import SettingsService
from app.services.tracking_service import TrackingService
from app.utils.time_utils import now_iso


class FixedGP:
    def __init__(self, **kw):
        self._kw = kw

    def app_detail(self, app_id, country="us", lang="en"):
        return AppDetail(app_id=app_id, title="App", installs="1,000,000+", **self._kw)


def _build(tmp_path, name, gp):
    db = Database(str(tmp_path / f"{name}.sqlite3"))
    db.create_all()
    settings = SettingsService(db)
    settings.ensure_defaults()
    alert = AlertService(db, settings_service=settings)
    ts = TrackingService(db, gp, alert_service=alert, settings_service=settings)
    return db, alert, ts


def test_same_day_syncs_keep_one_row(tmp_path):
    _, _, ts = _build(tmp_path, "sameday", FixedGP(rating=4.5, version="1.0"))
    ts.add_app("com.x", "us", "en")
    ts.sync_app_now("com.x")
    ts.sync_app_now("com.x")
    ts.sync_app_now("com.x")
    assert len(ts.get_history("com.x", "us", "en")) == 1


def test_upsert_for_day_updates_same_day_inserts_new_day(tmp_path):
    db = Database(str(tmp_path / "upsert.sqlite3"))
    db.create_all()
    repo = SnapshotRepository()
    with db.session() as s:
        assert repo.upsert_for_day(
            s, AppDetail(app_id="com.x", rating=4.0), "us", "en", now="2020-01-01T08:00:00"
        ) is True
        # same calendar day -> update, returns False
        assert repo.upsert_for_day(
            s, AppDetail(app_id="com.x", rating=4.5), "us", "en", now="2020-01-01T20:00:00"
        ) is False
        # new day -> insert, returns True
        assert repo.upsert_for_day(
            s, AppDetail(app_id="com.x", rating=4.6), "us", "en", now="2020-01-02T08:00:00"
        ) is True
    with db.session() as s:
        hist = repo.get_history(s, "com.x", "us", "en")
    assert len(hist) == 2
    assert hist[0].rating == 4.5  # day 1 kept the LAST value written that day
    assert hist[1].rating == 4.6


def test_previous_distinct_day_skips_today(tmp_path):
    db = Database(str(tmp_path / "prevday.sqlite3"))
    db.create_all()
    repo = SnapshotRepository()
    with db.session() as s:
        repo.upsert_for_day(
            s, AppDetail(app_id="com.x", rating=4.0), "us", "en", now="2020-01-01T08:00:00"
        )
        repo.upsert_for_day(
            s, AppDetail(app_id="com.x", rating=4.5), "us", "en", now="2020-01-02T08:00:00"
        )
        prev = repo.previous_distinct_day(s, "com.x", "us", "en", before_day="2020-01-02")
    assert prev is not None
    assert prev.rating == 4.0  # the prior day, never today


def test_cross_day_diff_and_no_same_day_duplicate_alert(tmp_path):
    db, alert, ts = _build(tmp_path, "crossday", FixedGP(rating=4.0, version="1.0"))
    # seed yesterday's baseline (rating 4.8) directly
    with db.session() as s:
        ts.tracking_repository.add_app(s, "com.x", "App", "us", "en")
        ts.snapshot_repository.upsert_for_day(
            s, AppDetail(app_id="com.x", title="App", rating=4.8, version="1.0"),
            "us", "en", now="2020-01-01T08:00:00",
        )

    ts.sync_app_now("com.x")  # today: 4.8 -> 4.0 = rating_drop (first of day)
    n1 = len(alert.recent_alerts(limit=50))
    assert any(a.type == "rating_drop" for a in alert.recent_alerts(limit=50))

    ts.sync_app_now("com.x")  # same day again -> NO new alert
    n2 = len(alert.recent_alerts(limit=50))
    assert n2 == n1

    today = now_iso()[:10]
    today_rows = [h for h in ts.get_history("com.x", "us", "en") if h.captured_at[:10] == today]
    assert len(today_rows) == 1
