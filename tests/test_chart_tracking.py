import pytest

from app.db.database import Database
from app.schemas.chart_schema import ChartItem
from app.services.alert_service import AlertService
from app.services.chart_rank_service import ChartRankService
from app.services.google_play_service import ServiceError
from app.services.settings_service import SettingsService
from app.services.tracking_service import TrackingService

COLLECTION = "top_free"
CATEGORY = "APPLICATION"
TARGET = "com.whatsapp"


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


def test_sync_chart_now_always_raises_retired_error(tmp_path):
    """chart syncing's live-network write path was retired; sync_chart_now is now a stub
    that always raises regardless of the underlying chart service, and records no alert
    or tracked-row state. This guards against an accidental future regression."""
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
    with pytest.raises(ServiceError):
        tracking_service.sync_chart_now(TARGET, COLLECTION, CATEGORY, "us", "en")

    assert alert_service.recent_alerts(limit=5) == []


def test_sync_all_returns_charts_count(tmp_path):
    # sync_chart_now is now a permanently-raising stub, so sync_all_charts' per-item
    # try/except logs and skips every chart -> the aggregate count is always 0.
    ts, _alerts = _build(tmp_path, "chart_syncall", [2])
    ts.add_chart_app(TARGET, COLLECTION, CATEGORY, "us", "en")
    result = ts.sync_all()
    assert result["charts"] == 0
    assert "apps" in result and "keywords" in result
