"""End-to-end GUI regression guard: drives the real Qt widgets/handlers/workers
against fake (network-free) scraping, asserting each button actually persists to DB.

This is the test that was missing — it exercises the click -> handler -> run_task
worker -> service -> repository -> DB path that unit tests of the service layer skip.
"""

import logging
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication
from sqlalchemy import func, select

import app.ui.pages.base_page as base_page
import app.ui.widgets.settings_form as settings_form
from app.db.database import Database
from app.db.migrations import migrate
from app.db.models import AppSnapshotModel, ChartSnapshotModel, KeywordRankModel, ReviewModel
from app.schemas.app_schema import AppDetail, AppSummary
from app.schemas.chart_schema import ChartItem
from app.schemas.review_schema import ReviewItem
from app.services.alert_service import AlertService
from app.services.chart_service import ChartService
from app.services.keyword_service import KeywordService
from app.services.monetization_service import MonetizationService
from app.services.review_service import ReviewService
from app.services.settings_service import SettingsService
from app.services.tracking_service import TrackingService


class FakeGooglePlayService:
    """Returns canned schema objects with icon_url=None so no real network is hit."""

    def search(self, keyword, country="us", lang="en", limit=20):
        return [
            AppSummary(app_id="com.telegram", title="Telegram", icon_url=None),
            AppSummary(app_id="com.whatsapp", title="WhatsApp", icon_url=None),
        ]

    def app_detail(self, app_id, country="us", lang="en"):
        return AppDetail(
            app_id=app_id,
            title="WhatsApp Messenger",
            developer="WhatsApp LLC",
            rating=4.4,
            ratings_count=1000,
            reviews_count=100,
            installs="1,000,000,000+",
            min_installs=1_000_000_000,
            version="2.24",
            free=True,
            has_iap=False,
            icon_url=None,
            screenshots=[],
        )

    def similar(self, app_id, country="us", lang="en", limit=20):
        return [AppSummary(app_id="com.signal", title="Signal", icon_url=None)]

    def reviews(self, app_id, country="us", lang="en", sort="newest", limit=100):
        return [
            ReviewItem(app_id=app_id, review_id=f"r{i}", content="c", rating=5) for i in range(3)
        ]

    def chart(self, chart_type, category, country, lang, limit):
        return [
            ChartItem(
                app_id=f"com.x{i}", title=f"X{i}", rank=i + 1, chart_type=chart_type, icon_url=None
            )
            for i in range(3)
        ]

    def configure(self, **kwargs):
        pass


def _build_services(db):
    settings_service = SettingsService(db)
    settings_service.ensure_defaults()
    gp = FakeGooglePlayService()
    keyword_service = KeywordService(gp, database=db)
    alert_service = AlertService(db)
    tracking_service = TrackingService(
        database=db,
        google_play_service=gp,
        keyword_service=keyword_service,
        alert_service=alert_service,
        settings_service=settings_service,
    )
    return {
        "settings_service": settings_service,
        "google_play_service": gp,
        "keyword_service": keyword_service,
        "review_service": ReviewService(db, gp),
        "chart_service": ChartService(db, gp),
        "monetization_service": MonetizationService(),
        "alert_service": alert_service,
        "tracking_service": tracking_service,
        "scheduler": None,
    }


def _count(db, model):
    with db.session() as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


def _wait_idle(app, page, timeout=10.0):
    deadline = time.time() + timeout
    for _ in range(3):
        app.processEvents()
    while getattr(page, "_workers", []) and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    for _ in range(5):
        app.processEvents()
    assert not page._workers, "a background worker did not finish in time"


def test_gui_button_workflows_persist_to_db(tmp_path, monkeypatch):
    try:
        app = QApplication.instance() or QApplication([])
    except Exception:  # pragma: no cover - no Qt platform in this environment
        pytest.skip("no Qt platform available")

    # dialogs are modal and would block the event loop in a headless run
    monkeypatch.setattr(base_page, "show_info", lambda *a, **k: None)
    monkeypatch.setattr(base_page, "show_error", lambda *a, **k: None)
    monkeypatch.setattr(settings_form, "show_info", lambda *a, **k: None)
    monkeypatch.setattr(settings_form, "show_error", lambda *a, **k: None)

    db = Database(str(tmp_path / "gui.sqlite3"))
    migrate(db)
    services = _build_services(db)

    from app.ui.main_window import MainWindow

    win = MainWindow(database=db, services=services, logger=logging.getLogger("gui-test"))

    # --- app detail: fetch populates labels, save persists a snapshot ---
    win.navigate_to("app_detail")
    detail_page = win.page_objects["app_detail"]
    detail_page.app_id_input.setText("com.whatsapp")
    detail_page.fetch_button.click()
    _wait_idle(app, detail_page)
    assert detail_page.name_label.text() == "WhatsApp Messenger"
    assert detail_page.metric_values["version"].text() == "2.24"
    before = _count(db, AppSnapshotModel)
    detail_page.save_button.click()
    _wait_idle(app, detail_page)
    assert _count(db, AppSnapshotModel) == before + 1

    # --- search: pressing Enter in the keyword field runs the search ---
    win.navigate_to("app_search")
    search_page = win.page_objects["app_search"]
    search_page.keyword_input.setText("messenger")
    search_page.keyword_input.returnPressed.emit()  # Enter-to-submit
    _wait_idle(app, search_page)
    assert search_page.table.rowCount() == 2

    # --- reviews: fetch fills table, save persists ---
    win.navigate_to("reviews")
    reviews_page = win.page_objects["reviews"]
    reviews_page.app_id_input.setText("com.whatsapp")
    reviews_page.fetch_button.click()
    _wait_idle(app, reviews_page)
    assert reviews_page.table.rowCount() == 3
    reviews_page.save_button.click()
    _wait_idle(app, reviews_page)
    assert _count(db, ReviewModel) == 3

    # --- keywords: query computes rank and saves; explicit save adds history ---
    win.navigate_to("keywords")
    keywords_page = win.page_objects["keywords"]
    keywords_page.keyword_input.setText("messenger")
    keywords_page.app_id_input.setText("com.whatsapp")
    keywords_page.fetch_button.click()
    _wait_idle(app, keywords_page)
    assert keywords_page.current_result is not None
    assert keywords_page.current_result.rank == 2
    k0 = _count(db, KeywordRankModel)
    keywords_page.save_button.click()
    _wait_idle(app, keywords_page)
    assert _count(db, KeywordRankModel) == k0 + 1

    # --- charts: fetch fills table, save persists snapshot rows ---
    win.navigate_to("charts")
    charts_page = win.page_objects["charts"]
    charts_page.fetch_button.click()
    _wait_idle(app, charts_page)
    assert charts_page.table.rowCount() == 3
    charts_page.save_button.click()
    _wait_idle(app, charts_page)
    assert _count(db, ChartSnapshotModel) == 3

    # --- tracking: add then sync-all writes a fresh snapshot ---
    win.navigate_to("tracking")
    tracking_page = win.page_objects["tracking"]
    _wait_idle(app, tracking_page)  # on_activated refresh runs in the background
    tracking_page.app_id_input.setText("com.whatsapp")
    tracking_page.add_app_button.click()
    _wait_idle(app, tracking_page)
    assert any(a.app_id == "com.whatsapp" for a in tracking_page.apps)
    s0 = _count(db, AppSnapshotModel)
    tracking_page.sync_all_button.click()
    _wait_idle(app, tracking_page)
    assert _count(db, AppSnapshotModel) > s0

    # --- keyword monitoring surfaces the latest rank ---
    services["tracking_service"].add_keyword("messenger", "com.whatsapp", "us", "en")
    services["tracking_service"].sync_keyword_now("messenger", "com.whatsapp", "us", "en")
    keyword_rows = tracking_page._collect_tracking_data()["keywords_rows"]
    assert any(r["keyword"] == "messenger" and r["rank"] == "#2" for r in keyword_rows)
