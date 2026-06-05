"""Notification pipeline: TrackingService aggregates each sync's new alerts and hands
the ones passing the user's notification settings to an injected notifier callback.

Snapshots are now one-per-day, so a day-over-day change is modeled by seeding a
"yesterday" snapshot and then doing a single sync "today" (not two same-day syncs)."""

from __future__ import annotations

import pytest

from app.db.database import Database
from app.schemas.app_schema import AppDetail
from app.services.alert_service import AlertService
from app.services.settings_service import SettingsService
from app.services.tracking_service import TrackingService

YESTERDAY = "2020-01-01T08:00:00"


class FixedGP:
    """app_detail returns one fixed AppDetail — the 'today' state of the app."""

    def __init__(self, **detail_kwargs):
        self._kw = detail_kwargs

    def app_detail(self, app_id, country="us", lang="en"):
        return AppDetail(app_id=app_id, title="App", installs="1,000,000+", **self._kw)


class FailGP:
    def app_detail(self, app_id, country="us", lang="en"):
        raise RuntimeError("boom")


def _build(tmp_path, name, gp, overrides=None):
    db = Database(str(tmp_path / f"{name}.sqlite3"))
    db.create_all()
    settings = SettingsService(db)
    settings.ensure_defaults()
    if overrides:
        settings.set_many(overrides)
    alert = AlertService(db, settings_service=settings)
    ts = TrackingService(db, gp, alert_service=alert, settings_service=settings)
    captured = []
    ts.set_notifier(lambda alerts: captured.append(list(alerts)))
    return ts, captured


def _seed_yesterday(ts, app_id, **detail_kwargs):
    """Write a prior-day snapshot so today's sync has a real day-over-day baseline."""
    with ts.database.session() as session:
        ts.tracking_repository.add_app(session, app_id, "App", "us", "en")
        ts.snapshot_repository.upsert_for_day(
            session,
            AppDetail(app_id=app_id, title="App", installs="1,000,000+", **detail_kwargs),
            "us",
            "en",
            now=YESTERDAY,
        )


def test_high_alert_is_dispatched_to_notifier(tmp_path):
    ts, captured = _build(
        tmp_path, "high", FixedGP(rating=4.2, ratings_count=100, reviews_count=10, version="1.0")
    )
    _seed_yesterday(ts, "com.x", rating=4.8, ratings_count=100, reviews_count=10, version="1.0")
    ts.sync_app_now("com.x")  # today: 4.8 -> 4.2 = high rating_drop
    assert len(captured) == 1
    assert any(a.type == "rating_drop" and a.severity == "high" for a in captured[0])


def test_disabled_notifications_suppress_dispatch(tmp_path):
    ts, captured = _build(
        tmp_path,
        "off",
        FixedGP(rating=4.2, ratings_count=100, reviews_count=10, version="1.0"),
        {"desktop_notifications": "false"},
    )
    _seed_yesterday(ts, "com.x", rating=4.8, ratings_count=100, reviews_count=10, version="1.0")
    ts.sync_app_now("com.x")
    assert captured == []


def test_min_severity_filters_medium_alert(tmp_path):
    # default notify_min_severity=high -> a medium-only sync (ratings_growth) must NOT notify.
    ts, captured = _build(
        tmp_path, "med_high", FixedGP(rating=4.5, ratings_count=120, reviews_count=10, version="1.0")
    )
    _seed_yesterday(ts, "com.x", rating=4.5, ratings_count=100, reviews_count=10, version="1.0")
    ts.sync_app_now("com.x")  # ratings_growth = medium, below high threshold
    assert captured == []


def test_min_severity_medium_allows_medium_alert(tmp_path):
    ts, captured = _build(
        tmp_path,
        "med_med",
        FixedGP(rating=4.5, ratings_count=120, reviews_count=10, version="1.0"),
        {"notify_min_severity": "medium"},
    )
    _seed_yesterday(ts, "com.x", rating=4.5, ratings_count=100, reviews_count=10, version="1.0")
    ts.sync_app_now("com.x")
    assert len(captured) == 1
    assert any(a.type == "ratings_growth" and a.severity == "medium" for a in captured[0])


def test_persistent_fetch_failure_dispatches_high_alert(tmp_path):
    # With escalate_after=1 the very first failure is already "persistent" -> high -> pushed.
    ts, captured = _build(tmp_path, "fail", FailGP(), {"alert_fetch_escalate_after": "1"})
    ts.add_app("com.x", "us", "en")
    with pytest.raises(RuntimeError):
        ts.sync_app_now("com.x")
    assert captured
    assert captured[0][0].type == "fetch_failed_persistent"
    assert captured[0][0].severity == "high"


def test_sync_all_aggregates_into_single_dispatch(tmp_path):
    # Two apps both dropping rating day-over-day -> ONE aggregated batch, not two.
    ts, captured = _build(
        tmp_path, "agg", FixedGP(rating=4.0, ratings_count=100, reviews_count=10, version="1.0")
    )
    for app_id in ("com.a", "com.b"):
        _seed_yesterday(ts, app_id, rating=4.8, ratings_count=100, reviews_count=10, version="1.0")
    ts.sync_all()  # both drop 4.8 -> 4.0 today -> two rating_drops in a SINGLE dispatch
    assert len(captured) == 1, "sync_all must notify once, not per item"
    assert len(captured[0]) == 2
