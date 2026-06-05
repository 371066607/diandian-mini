"""Monitoring-UX regression guards (offscreen, no network):

- TrackingPage._next_sync_label: the pure next-sync-time formatter.
- AppDetailPage's per-app "最近告警" section: async load fills the small table
  with this app's alerts, rendered with Chinese type/severity labels.
"""

import logging
import os
import time
from datetime import datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

import app.ui.pages.base_page as base_page
from app.db.database import Database
from app.db.migrations import migrate
from app.db.repositories import AlertRepository
from app.schemas.app_schema import AppDetail
from app.services.alert_service import AlertService
from app.services.export_service import ExportService
from app.services.monetization_service import MonetizationService
from app.services.review_service import ReviewService
from app.services.settings_service import SettingsService
from app.ui.pages.tracking_page import TrackingPage


# ---- A) _next_sync_label pure logic -------------------------------------------------

def test_next_sync_label_manual():
    assert TrackingPage._next_sync_label(None, "manual") == "手动"
    assert TrackingPage._next_sync_label("2026-06-01T09:00:00", "manual") == "手动"


def test_next_sync_label_never_synced():
    assert TrackingPage._next_sync_label(None, "daily") == "待首次同步"
    assert TrackingPage._next_sync_label("", "weekly") == "待首次同步"


def test_next_sync_label_recent_daily_shows_future_time():
    now = datetime(2026, 6, 5, 12, 0, 0)
    last = "2026-06-05T10:00:00"  # synced 2h ago, daily interval is 20h
    label = TrackingPage._next_sync_label(last, "daily", now=now)
    assert label != "已到期"
    # projected = last + 20h => 06-06 06:00
    assert label == "06-06 06:00"


def test_next_sync_label_stale_daily_is_due():
    now = datetime(2026, 6, 5, 12, 0, 0)
    last = "2026-06-01T09:00:00"  # days ago — well past the 20h daily interval
    assert TrackingPage._next_sync_label(last, "daily", now=now) == "已到期"


# ---- B) AppDetailPage 最近告警 section ----------------------------------------------

class _FakeGooglePlayService:
    def app_detail(self, app_id, country="us", lang="en"):
        return AppDetail(app_id=app_id, title="WhatsApp", icon_url=None, screenshots=[])

    def similar(self, app_id, country="us", lang="en", limit=20):
        return []


def _detail_services(db):
    settings_service = SettingsService(db)
    settings_service.ensure_defaults()
    return {
        "google_play_service": _FakeGooglePlayService(),
        "tracking_service": object(),
        "monetization_service": MonetizationService(),
        "alert_service": AlertService(db),
        "settings_service": settings_service,
        "export_service": ExportService(db),
        "review_service": ReviewService(db, _FakeGooglePlayService()),
    }


def _wait_idle(app, timeout=5.0):
    deadline = time.time() + timeout
    for _ in range(3):
        app.processEvents()
    QThreadPool.globalInstance().waitForDone(int(timeout * 1000))
    while time.time() < deadline:
        app.processEvents()
        if QThreadPool.globalInstance().activeThreadCount() == 0:
            break
        time.sleep(0.01)
    for _ in range(5):
        app.processEvents()


def test_detail_page_alerts_section_populates(tmp_path, monkeypatch):
    try:
        app = QApplication.instance() or QApplication([])
    except Exception:  # pragma: no cover - no Qt platform
        pytest.skip("no Qt platform available")

    monkeypatch.setattr(base_page, "show_info", lambda *a, **k: None)
    monkeypatch.setattr(base_page, "show_error", lambda *a, **k: None)

    db = Database(str(tmp_path / "alerts.sqlite3"))
    migrate(db)

    repo = AlertRepository()
    with db.session() as session:
        repo.create(
            session, "rating_drop", "high", "评分由 4.5 降至 4.1",
            app_id="com.whatsapp", title="WhatsApp",
        )
        repo.create(
            session, "version_changed", "low", "版本由 2.23 升至 2.24",
            app_id="com.whatsapp", title="WhatsApp",
        )
        # An alert for a different app must NOT appear in this app's section.
        repo.create(
            session, "reviews_growth", "medium", "评论数增长",
            app_id="com.other", title="Other",
        )

    from app.ui.pages.app_detail_page import AppDetailPage

    page = AppDetailPage(
        _detail_services(db),
        window_api=object(),
        logger=logging.getLogger("ux-test"),
    )

    # Drive the async loader directly (same path _on_detail_finished uses).
    page._detail_gen = 1
    page._load_alerts_async("com.whatsapp", gen=1)
    _wait_idle(app)

    assert page.alerts_table.rowCount() == 2  # only this app's alerts
    types = {
        page.alerts_table.item(r, 2).text() for r in range(page.alerts_table.rowCount())
    }
    assert "评分下降" in types  # Chinese type label, not raw "rating_drop"
    assert "版本变化" in types


def test_detail_page_alerts_section_core_filters_and_localizes(tmp_path):
    db = Database(str(tmp_path / "alerts2.sqlite3"))
    migrate(db)
    repo = AlertRepository()
    with db.session() as session:
        repo.create(
            session, "rating_drop", "high", "评分下降啦",
            app_id="com.whatsapp", title="WhatsApp",
        )

    services = _detail_services(db)
    # Exercise the sync core (no Qt needed) so the row mapping itself is covered.
    from app.ui.pages.app_detail_page import AppDetailPage

    rows = AppDetailPage._collect_alert_rows.__get__(
        type("S", (), {"alert_service": services["alert_service"]})()
    )("com.whatsapp")
    assert len(rows) == 1
    row = rows[0]
    assert row["severity"] == "高"
    assert row["type"] == "评分下降"
    assert AppDetailPage._alert_row_tint(row) == "#DC2626"
