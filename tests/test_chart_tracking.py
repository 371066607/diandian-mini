import pytest

from app.db.database import Database
from app.schemas.chart_rank_schema import ChartRankResult
from app.schemas.chart_schema import ChartItem
from app.services.alert_service import AlertService
from app.services.chart_rank_service import ChartRankService
from app.services.settings_service import SettingsService
from app.services.tracking_service import TrackingService

_YESTERDAY = "2020-01-01T08:00:00"
COLLECTION = "top_free"
CATEGORY = "APPLICATION"
TARGET = "com.whatsapp"


def _seed_yesterday_rank(ts, rank):
    """Write a prior-day chart rank so today's sync has a real day-over-day baseline."""
    with ts.database.session() as session:
        ts.tracking_repository.add_chart_app(
            session, TARGET, COLLECTION, CATEGORY, "us", "en"
        )
        ts.chart_rank_service.repository.upsert_for_day(
            session,
            ChartRankResult(
                app_id=TARGET, collection=COLLECTION, category=CATEGORY,
                country="us", lang="en", found=rank is not None, rank=rank,
                checked_limit=100, captured_at=_YESTERDAY,
            ),
            now=_YESTERDAY,
        )


class ScriptedChartService:
    """list_analyze returns a 20-app list with TARGET at a scripted 1-based position on
    each successive call (None = absent / not ranked)."""

    def __init__(self, positions):
        self._positions = list(positions)
        self._call = 0

    def list_analyze(self, collection, category=None, country="us", lang="en", limit=100):
        pos = self._positions[self._call]
        self._call += 1
        items = []
        for i in range(1, 21):
            app_id = TARGET if (pos is not None and i == pos) else f"com.filler{i}"
            items.append(ChartItem(app_id=app_id, title=app_id, rank=i, chart_type=collection))
        return items


class FailingChartService:
    def list_analyze(self, *a, **k):
        raise RuntimeError("chart unavailable")

    def chart(self, *a, **k):
        raise RuntimeError("chart unavailable")


def _build(tmp_path, name, positions, settings_overrides=None):
    database = Database(str(tmp_path / f"{name}.sqlite3"))
    database.create_all()
    settings_service = SettingsService(database)
    settings_service.ensure_defaults()
    if settings_overrides:
        settings_service.set_many(settings_overrides)
    alert_service = AlertService(database, settings_service=settings_service)
    chart_rank_service = ChartRankService(ScriptedChartService(positions), database=database)
    tracking_service = TrackingService(
        database=database,
        google_play_service=None,
        alert_service=alert_service,
        settings_service=settings_service,
        chart_rank_service=chart_rank_service,
    )
    return tracking_service, alert_service


def test_sync_chart_now_persists_and_sets_sync_time(tmp_path):
    database = Database(str(tmp_path / "chart-sync.sqlite3"))
    database.create_all()
    settings_service = SettingsService(database)
    settings_service.ensure_defaults()
    chart_rank_service = ChartRankService(ScriptedChartService([2]), database=database)
    tracking_service = TrackingService(
        database=database,
        google_play_service=None,
        settings_service=settings_service,
        chart_rank_service=chart_rank_service,
    )
    tracking_service.add_chart_app(TARGET, COLLECTION, CATEGORY, "us", "en")
    result = tracking_service.sync_chart_now(TARGET, COLLECTION, CATEGORY, "us", "en")
    charts = tracking_service.list_chart_apps()
    history = chart_rank_service.history(TARGET, COLLECTION, CATEGORY, "us", "en")

    assert result.rank == 2
    assert charts[0].last_synced_at is not None
    assert len(history) == 1
    assert history[0].rank == 2


def test_chart_alerts_cover_key_transitions(tmp_path):
    cases = [
        ("rise_in_band", 8, 3, "chart_rank_up"),
        ("fall_in_band", 3, 9, "chart_rank_down"),
        ("into_top", 14, 6, "chart_top_entered"),
        ("out_of_top", 5, 18, "chart_top_dropped"),
        ("entered", None, 7, "chart_entered"),
        ("dropped", 4, None, "chart_dropped"),
    ]
    for name, baseline, today, expected_type in cases:
        ts, alerts = _build(tmp_path, name, [today])
        _seed_yesterday_rank(ts, baseline)
        ts.sync_chart_now(TARGET, COLLECTION, CATEGORY, "us", "en")
        recent = alerts.recent_alerts(limit=5)
        assert len(recent) == 1, f"{name}: expected one alert, got {len(recent)}"
        assert recent[0].type == expected_type, f"{name}: got {recent[0].type}"
        assert recent[0].app_id == TARGET


def test_chart_first_sync_only_baselines(tmp_path):
    # No prior-day row -> first sync establishes a baseline, no alert.
    ts, alerts = _build(tmp_path, "chart_first", [3])
    ts.add_chart_app(TARGET, COLLECTION, CATEGORY, "us", "en")
    ts.sync_chart_now(TARGET, COLLECTION, CATEGORY, "us", "en")
    assert alerts.unread_count() == 0


def test_chart_same_day_resync_does_not_realert(tmp_path):
    ts, alerts = _build(tmp_path, "chart_sameday", [3, 3])
    _seed_yesterday_rank(ts, 8)
    ts.sync_chart_now(TARGET, COLLECTION, CATEGORY, "us", "en")  # 8 -> 3 rise
    assert alerts.unread_count() == 1
    ts.sync_chart_now(TARGET, COLLECTION, CATEGORY, "us", "en")  # same day, no new alert
    assert alerts.unread_count() == 1
    # yesterday seed + ONE today row
    assert len(ts.chart_rank_service.history(TARGET, COLLECTION, CATEGORY, "us", "en")) == 2


def test_sync_chart_now_records_fetch_failure_alert(tmp_path):
    database = Database(str(tmp_path / "chart-fail.sqlite3"))
    database.create_all()
    alert_service = AlertService(database)
    tracking_service = TrackingService(
        database=database,
        google_play_service=None,
        alert_service=alert_service,
        chart_rank_service=ChartRankService(FailingChartService(), database=database),
    )
    tracking_service.add_chart_app(TARGET, COLLECTION, CATEGORY, "us", "en")
    with pytest.raises(RuntimeError):
        tracking_service.sync_chart_now(TARGET, COLLECTION, CATEGORY, "us", "en")

    alerts = alert_service.recent_alerts(limit=5)
    assert len(alerts) == 1
    assert alerts[0].type == "fetch_failed"
    # failure is non-fatal to the run but is recorded against the tracked row
    charts = tracking_service.list_chart_apps()
    assert charts[0].consecutive_failures == 1


def test_sync_all_returns_charts_count(tmp_path):
    ts, _alerts = _build(tmp_path, "chart_syncall", [2])
    ts.add_chart_app(TARGET, COLLECTION, CATEGORY, "us", "en")
    result = ts.sync_all()
    assert result["charts"] == 1
    assert "apps" in result and "keywords" in result
