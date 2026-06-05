from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from app.db.database import Database
from app.db.repositories import AlertRepository
from app.schemas.app_schema import AppDetail
from app.services.settings_service import SettingsService
from app.services.tracking_service import MonitorHealth, TrackingService, _trend
from app.utils.time_utils import now_iso


def _detail(app_id="com.example", *, title="Example", rating=4.5, reviews=100, installs="1M+"):
    return AppDetail(
        app_id=app_id,
        title=title,
        rating=rating,
        reviews_count=reviews,
        installs=installs,
    )


def _make_service(tmp_path):
    database = Database(str(tmp_path / "monitor.sqlite3"))
    database.create_all()
    settings_service = SettingsService(database)
    settings_service.ensure_defaults()
    service = TrackingService(
        database=database,
        google_play_service=None,
        settings_service=settings_service,
    )
    return database, service


def _save(service, detail, country="us", lang="en"):
    with service.database.session() as session:
        service.snapshot_repository.save_detail(session, detail, country, lang)


# --- _trend pure function ------------------------------------------------


def test_trend_up_down_flat_none():
    assert _trend(4.0, 4.5) == "up"
    assert _trend(4.5, 4.0) == "down"
    # within eps -> flat
    assert _trend(4.50, 4.52, eps=0.05) == "flat"
    # exactly eps -> flat
    assert _trend(4.50, 4.55, eps=0.05) == "flat"
    # just over eps -> up
    assert _trend(4.50, 4.60, eps=0.05) == "up"
    # missing data -> none (single snapshot)
    assert _trend(None, 4.5) == "none"
    assert _trend(4.5, None) == "none"


# --- monitor_overview core -----------------------------------------------


def test_monitor_overview_one_dto_per_enabled_app_with_full_fields(tmp_path):
    database, service = _make_service(tmp_path)
    service.add_app("com.example", "us", "en")
    # Two snapshots build trends: rating up, reviews up, installs band up.
    _save(service, _detail(rating=4.0, reviews=100, installs="500,000+"))
    _save(service, _detail(rating=4.5, reviews=250, installs="1,000,000+"))
    # An unread alert for this app.
    with database.session() as session:
        AlertRepository().create(
            session,
            "rating_drop",
            "high",
            "评分下降",
            app_id="com.example",
            title="Example",
        )

    overview = service.monitor_overview()
    assert len(overview) == 1
    health = overview[0]
    assert isinstance(health, MonitorHealth)
    assert health.app_id == "com.example"
    assert health.latest_rating == 4.5
    assert health.latest_installs == "1,000,000+"
    assert health.rating_trend == "up"
    assert health.reviews_trend == "up"
    assert health.installs_trend == "up"
    assert health.unread_count == 1
    assert health.last_alert is not None
    assert health.last_alert["type"] == "rating_drop"
    assert health.last_alert["severity"] == "high"
    assert "created_at" in health.last_alert
    assert health.fail_status == "normal"
    assert health.consecutive_failures == 0


def test_monitor_overview_single_snapshot_yields_none_trends(tmp_path):
    _, service = _make_service(tmp_path)
    service.add_app("com.single", "us", "en")
    _save(service, _detail(app_id="com.single"))
    health = service.monitor_overview()[0]
    assert health.rating_trend == "none"
    assert health.reviews_trend == "none"
    assert health.installs_trend == "none"
    assert health.last_alert is None
    assert health.unread_count == 0


def test_monitor_overview_excludes_disabled(tmp_path):
    _, service = _make_service(tmp_path)
    service.add_app("com.enabled", "us", "en")
    service.add_app("com.disabled", "us", "en")
    service.toggle_app("com.disabled", "us", "en")  # flips enabled -> disabled
    overview = service.monitor_overview()
    ids = {h.app_id for h in overview}
    assert ids == {"com.enabled"}


def test_monitor_overview_empty_when_no_apps(tmp_path):
    _, service = _make_service(tmp_path)
    assert service.monitor_overview() == []


# --- fail_status three states --------------------------------------------


@pytest.mark.parametrize(
    "failures,expected",
    [(0, "normal"), (1, "failing"), (2, "failing"), (3, "escalated"), (5, "escalated")],
)
def test_fail_status_three_states(tmp_path, failures, expected):
    database, service = _make_service(tmp_path)
    service.add_app("com.fail", "us", "en")
    _save(service, _detail(app_id="com.fail"))
    # escalate_after default is 3.
    assert service._escalate_after() == 3
    with database.session() as session:
        for _ in range(failures):
            service.tracking_repository.record_app_failure(
                session, "com.fail", "us", "en", now_iso()
            )
    health = service.monitor_overview()[0]
    assert health.consecutive_failures == failures
    assert health.fail_status == expected


# --- MonitorCard drill-down ----------------------------------------------


def test_monitor_card_open_passes_app_id(tmp_path):
    from PySide6.QtWidgets import QApplication

    from app.ui.widgets.monitor_card import MonitorCard

    app = QApplication.instance() or QApplication([])
    health = MonitorHealth(
        app_id="com.drill",
        country="us",
        lang="en",
        title="Drill",
        latest_rating=4.2,
        latest_installs="1M+",
        rating_trend="up",
        installs_trend="flat",
        reviews_trend="down",
        last_alert={"type": "rating_drop", "severity": "high", "created_at": now_iso()},
        unread_count=2,
        consecutive_failures=0,
        fail_status="normal",
        last_synced_at=now_iso(),
    )
    captured = {}
    card = MonitorCard(health, lambda app_id: captured.setdefault("app_id", app_id))
    card._handle_open()
    assert captured["app_id"] == "com.drill"
    # status: unread > 0 and normal -> yellow
    assert card._status_color() == "yellow"
    card.deleteLater()
    app.processEvents()
