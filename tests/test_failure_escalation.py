"""Consecutive-failure tracking: counts accumulate per monitor, escalate to a loud
persistent alert at the threshold, and reset (with a recovery alert) on success."""

from __future__ import annotations

import pytest

from app.db.database import Database
from app.schemas.app_schema import AppDetail, AppSummary
from app.services.alert_service import AlertService
from app.services.keyword_service import KeywordService
from app.services.settings_service import SettingsService
from app.services.tracking_service import TrackingService


class FlakyGP:
    """Fails (raises) on the first ``fail_times`` app_detail calls, then succeeds."""

    def __init__(self, fail_times):
        self._fail_times = fail_times
        self._calls = 0

    def app_detail(self, app_id, country="us", lang="en"):
        self._calls += 1
        if self._calls <= self._fail_times:
            raise RuntimeError("store down")
        return AppDetail(
            app_id=app_id, title="App", rating=4.5, ratings_count=10,
            reviews_count=5, version="1.0", installs="1,000,000+",
        )


class NoHitSearch:
    """A successful search that simply doesn't contain the tracked app (未命中)."""

    def search(self, keyword, country="us", lang="en", limit=50):
        return [AppSummary(app_id="com.other", title="Other")]


def _build(tmp_path, name, gp=None, keyword_service=None, overrides=None):
    db = Database(str(tmp_path / f"{name}.sqlite3"))
    db.create_all()
    settings = SettingsService(db)
    settings.ensure_defaults()
    if overrides:
        settings.set_many(overrides)
    alert = AlertService(db, settings_service=settings)
    ts = TrackingService(
        db, gp, keyword_service=keyword_service, alert_service=alert, settings_service=settings
    )
    return db, alert, ts


def _app(ts, app_id="com.x"):
    return next(a for a in ts.list_apps() if a.app_id == app_id)


def test_failures_accumulate_then_escalate(tmp_path):
    _, alert, ts = _build(tmp_path, "esc", FlakyGP(fail_times=5))
    ts.add_app("com.x", "us", "en")

    for _ in range(2):  # below the default threshold of 3
        with pytest.raises(RuntimeError):
            ts.sync_app_now("com.x")
    app = _app(ts)
    assert app.consecutive_failures == 2
    assert app.last_failed_at is not None
    assert {a.type for a in alert.recent_alerts(limit=10)} == {"fetch_failed"}  # all quiet

    with pytest.raises(RuntimeError):  # the 3rd failure escalates
        ts.sync_app_now("com.x")
    assert _app(ts).consecutive_failures == 3
    # created_at is second-granular so order can tie — assert the escalation exists.
    persistent = [a for a in alert.recent_alerts(limit=10) if a.type == "fetch_failed_persistent"]
    assert len(persistent) == 1
    assert persistent[0].severity == "high"
    assert "连续 3" in persistent[0].message


def test_recovery_after_escalation_emits_recovered(tmp_path):
    _, alert, ts = _build(tmp_path, "rec", FlakyGP(fail_times=3))
    ts.add_app("com.x", "us", "en")
    for _ in range(3):
        with pytest.raises(RuntimeError):
            ts.sync_app_now("com.x")
    assert _app(ts).consecutive_failures == 3

    ts.sync_app_now("com.x")  # now succeeds
    assert _app(ts).consecutive_failures == 0
    assert "fetch_recovered" in {a.type for a in alert.recent_alerts(limit=10)}


def test_transient_failure_recovers_quietly(tmp_path):
    # One failure (below threshold) then success: counter resets, but NO recovery alert.
    _, alert, ts = _build(tmp_path, "transient", FlakyGP(fail_times=1))
    ts.add_app("com.x", "us", "en")
    with pytest.raises(RuntimeError):
        ts.sync_app_now("com.x")
    ts.sync_app_now("com.x")
    assert _app(ts).consecutive_failures == 0
    assert "fetch_recovered" not in {a.type for a in alert.recent_alerts(limit=10)}


def test_escalate_after_is_configurable(tmp_path):
    _, alert, ts = _build(
        tmp_path, "cfg", FlakyGP(fail_times=5), overrides={"alert_fetch_escalate_after": "1"}
    )
    ts.add_app("com.x", "us", "en")
    with pytest.raises(RuntimeError):  # first failure already escalates
        ts.sync_app_now("com.x")
    assert alert.recent_alerts(limit=5)[0].type == "fetch_failed_persistent"


def test_keyword_miss_counts_as_success(tmp_path):
    db, alert, ts = _build(tmp_path, "kwmiss", gp=object())
    ts.keyword_service = KeywordService(NoHitSearch(), database=db)
    ts.add_keyword("messenger", "com.x", "us", "en")

    result = ts.sync_keyword_now("messenger", "com.x", "us", "en")
    assert result.found is False  # 未命中
    keyword = next(k for k in ts.list_keywords() if k.keyword == "messenger")
    assert keyword.consecutive_failures == 0
    assert not any(a.type.startswith("fetch") for a in alert.recent_alerts(limit=10))
