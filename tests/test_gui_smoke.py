"""End-to-end GUI regression guard: drives the real Qt widgets/handlers/workers
against fake (network-free) scraping, exercising the click -> handler -> run_task
worker -> service -> repository -> DB path that unit tests of the service layer skip.

The legacy scraper's live-network *write* path has been retired (see
app/services/google_play_service.py's ``_FEATURE_RETIRED_MESSAGE``): snapshot/review/
keyword-rank/chart-rank persistence and the tracking-service sync_*_now methods are now
raising stubs. This test asserts the still-alive fetch/read/CRUD flows continue to work
end-to-end through the real widgets, and that the retired save/sync buttons surface the
"feature retired" error to the user instead of silently succeeding or crashing the UI.
"""

import logging
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

import app.ui.pages.base_page as base_page
import app.ui.widgets.settings_form as settings_form
from app.db.database import Database
from app.db.migrations import migrate
from app.schemas.app_schema import AppDetail, AppSummary
from app.schemas.chart_schema import ChartItem
from app.schemas.review_schema import ReviewItem
from app.services.alert_service import AlertService
from app.services.chart_rank_service import ChartRankService
from app.services.chart_service import ChartService
from app.services.export_service import ExportService
from app.services.google_play_service import _FEATURE_RETIRED_MESSAGE
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

    def reviews(self, app_id, country="us", lang="en", sort="newest", continuation_token=None):
        items = [
            ReviewItem(app_id=app_id, review_id=f"r{i}", content="c", rating=5) for i in range(3)
        ]
        return items, None  # (items, next continuation token) — no further pages

    def chart(self, chart_type, category, country, lang, limit):
        return [
            ChartItem(
                app_id=f"com.x{i}", title=f"X{i}", rank=i + 1, chart_type=chart_type, icon_url=None
            )
            for i in range(3)
        ]

    def list_analyze(self, chart_type, category, country, lang, limit):
        return self.chart(chart_type, category, country, lang, limit)

    def configure(self, **kwargs):
        pass


class FakeUpdateService:
    """No-network stand-in so the smoke test never hits git/GitHub at startup."""

    def current_label(self):
        return "测试版"

    def check(self):
        from app.services.update_service import UpdateResult

        return UpdateResult(mode="patch", up_to_date=True)


def _build_services(db):
    settings_service = SettingsService(db)
    settings_service.ensure_defaults()
    gp = FakeGooglePlayService()
    keyword_service = KeywordService(gp, database=db)
    chart_rank_service = ChartRankService(gp, database=db)
    alert_service = AlertService(db)
    tracking_service = TrackingService(
        database=db,
        google_play_service=gp,
        keyword_service=keyword_service,
        alert_service=alert_service,
        settings_service=settings_service,
        chart_rank_service=chart_rank_service,
    )
    return {
        "settings_service": settings_service,
        "google_play_service": gp,
        "keyword_service": keyword_service,
        "chart_rank_service": chart_rank_service,
        "review_service": ReviewService(db, gp),
        "chart_service": ChartService(db, gp),
        "monetization_service": MonetizationService(),
        "alert_service": alert_service,
        "tracking_service": tracking_service,
        "scheduler": None,
        "update_service": FakeUpdateService(),
        "export_service": ExportService(db),
    }


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


def _seed_keyword_rank(
    db, *, keyword, app_id, rank, country="us", lang="en", platform="google_play"
):
    """Insert a KeywordRankModel row directly — KeywordRankRepository.save/upsert_for_day
    (the write paths KeywordService.save_result used to call) were retired along with the
    live-scrape write path, so tests that need a pre-existing rank row must seed via the
    ORM model instead."""
    from app.db.models import KeywordRankModel
    from app.utils.time_utils import now_iso

    with db.session() as session:
        session.add(
            KeywordRankModel(
                platform=platform,
                keyword=keyword,
                app_id=app_id,
                country=country,
                lang=lang,
                rank=rank,
                found=1,
                checked_limit=100,
                captured_at=now_iso(),
            )
        )
        session.commit()


def _seed_chart_rank(
    db, *, app_id, collection, category, rank, country="us", lang="en", platform="google_play"
):
    """Insert a ChartRankSnapshotModel row directly — see _seed_keyword_rank for why."""
    from app.db.models import ChartRankSnapshotModel
    from app.utils.time_utils import now_iso

    with db.session() as session:
        session.add(
            ChartRankSnapshotModel(
                platform=platform,
                app_id=app_id,
                collection=collection,
                category=category,
                country=country,
                lang=lang,
                rank=rank,
                found=1,
                checked_limit=100,
                captured_at=now_iso(),
            )
        )
        session.commit()


def test_gui_button_workflows_persist_to_db(tmp_path, monkeypatch):
    try:
        app = QApplication.instance() or QApplication([])
    except Exception:  # pragma: no cover - no Qt platform in this environment
        pytest.skip("no Qt platform available")

    # dialogs are modal and would block the event loop in a headless run; capture the
    # messages instead of a pure no-op so retired-feature errors can be asserted on.
    errors: list[str] = []
    monkeypatch.setattr(base_page, "show_info", lambda *a, **k: None)
    monkeypatch.setattr(base_page, "show_error", lambda self, message: errors.append(message))
    monkeypatch.setattr(settings_form, "show_info", lambda *a, **k: None)
    monkeypatch.setattr(settings_form, "show_error", lambda *a, **k: None)

    db = Database(str(tmp_path / "gui.sqlite3"))
    migrate(db)
    services = _build_services(db)

    from app.ui.main_window import MainWindow

    win = MainWindow(database=db, services=services, logger=logging.getLogger("gui-test"))

    # --- app detail: fetch still populates labels from the live (faked) library call ---
    win.navigate_to("app_detail")
    detail_page = win.page_objects["app_detail"]
    detail_page.app_id_input.setText("com.whatsapp")
    detail_page.fetch_button.click()
    _wait_idle(app, detail_page)
    assert detail_page.name_label.text() == "WhatsApp Messenger"
    assert detail_page.metric_values["version"].text() == "2.24"

    # save_snapshot -> tracking_service.sync_app_now is a retired write path: it now always
    # raises ServiceError, surfaced to the user via show_error instead of persisting.
    errors.clear()
    detail_page.save_button.click()
    _wait_idle(app, detail_page)
    assert errors == [_FEATURE_RETIRED_MESSAGE]

    # --- search: pressing Enter in the keyword field runs the search (read-only, unaffected) ---
    win.navigate_to("app_search")
    search_page = win.page_objects["app_search"]
    search_page.keyword_input.setText("messenger")
    search_page.keyword_input.returnPressed.emit()  # Enter-to-submit
    _wait_idle(app, search_page)
    assert search_page.table.rowCount() == 2

    # --- reviews: fetch still fills the table; save is a retired write path ---
    win.navigate_to("reviews")
    reviews_page = win.page_objects["reviews"]
    reviews_page.app_id_input.setText("com.whatsapp")
    reviews_page.fetch_button.click()
    _wait_idle(app, reviews_page)
    assert reviews_page.table.rowCount() == 3
    errors.clear()
    reviews_page.save_button.click()
    _wait_idle(app, reviews_page)
    assert errors == [_FEATURE_RETIRED_MESSAGE]

    # --- keywords: KeywordService.rank() now always raises once a database is configured,
    # since it calls the retired save_result() internally as its last step ---
    win.navigate_to("keywords")
    keywords_page = win.page_objects["keywords"]
    keywords_page.keyword_input.setText("messenger")
    keywords_page.app_id_input.setText("com.whatsapp")
    errors.clear()
    keywords_page.fetch_button.click()
    _wait_idle(app, keywords_page)
    assert errors == [_FEATURE_RETIRED_MESSAGE]
    assert keywords_page.current_result is None

    # --- charts: fetch still fills the table; save is a retired write path ---
    win.navigate_to("charts")
    charts_page = win.page_objects["charts"]
    charts_page.fetch_button.click()
    _wait_idle(app, charts_page)
    assert charts_page.table.rowCount() == 3
    errors.clear()
    charts_page.save_button.click()
    _wait_idle(app, charts_page)
    assert errors == [_FEATURE_RETIRED_MESSAGE]

    # --- tracking: add-app/add-chart/set-tag are user-driven CRUD, not scraped-content
    # writes, and remain fully functional; sync-all wraps the now-always-raising
    # sync_*_now calls in try/except and logs+skips, so it completes without raising ---
    win.navigate_to("tracking")
    tracking_page = win.page_objects["tracking"]
    _wait_idle(app, tracking_page)  # on_activated refresh runs in the background
    tracking_page.app_id_input.setText("com.whatsapp")
    tracking_page.add_app_button.click()
    _wait_idle(app, tracking_page)
    assert any(a.app_id == "com.whatsapp" for a in tracking_page.apps)

    tracking_page.sync_all_button.click()
    _wait_idle(app, tracking_page)
    synced = [a for a in services["tracking_service"].list_apps() if a.app_id == "com.whatsapp"]
    # sync_app_now always raises now, so sync_all logs+skips it: no crash, but also no
    # last_synced_at bump from this call.
    assert synced and synced[0].last_synced_at is None

    # "更多▾" button replaces the old separate sync_due/cleanup buttons; call methods directly
    assert tracking_page.more_button is not None
    tracking_page.sync_due()
    _wait_idle(app, tracking_page)

    # --- tagging: set-tag button and filter dropdown exist and work ---
    assert tracking_page.set_tag_button is not None
    assert tracking_page.tag_filter_combo is not None
    # Select the com.whatsapp app row, type a tag, and apply it.
    tracking_page._set_active_table("app")
    tracking_page.apps_table.selectRow(0)
    tracking_page.tag_input.setText("游戏")
    tracking_page.set_tag_button.click()
    _wait_idle(app, tracking_page)
    tagged = [a for a in services["tracking_service"].list_apps() if a.app_id == "com.whatsapp"]
    assert tagged and tagged[0].tag == "游戏"
    # The table shows the tag and the filter dropdown now offers it.
    tag_rows = tracking_page._collect_tracking_data()["apps_rows"]
    assert any(r["app_id"] == "com.whatsapp" and r["tag"] == "游戏" for r in tag_rows)
    assert "游戏" in [
        tracking_page.tag_filter_combo.itemText(i)
        for i in range(tracking_page.tag_filter_combo.count())
    ]
    # Filtering to a non-existent tag hides all rows; back to 全部 shows them again.
    visible_all = tracking_page.apps_table.rowCount()
    assert visible_all >= 1
    tracking_page.tag_filter_combo.setCurrentText("游戏")
    assert tracking_page.apps_table.rowCount() == 1
    tracking_page.tag_filter_combo.setCurrentText("全部")
    assert tracking_page.apps_table.rowCount() == visible_all

    # --- keyword monitoring still surfaces the latest rank from the DB (read path) ---
    services["tracking_service"].add_keyword("messenger", "com.whatsapp", "us", "en")
    _seed_keyword_rank(db, keyword="messenger", app_id="com.whatsapp", rank=2)
    keyword_rows = tracking_page._collect_tracking_data()["keywords_rows"]
    assert any(r["keyword"] == "messenger" and r["rank"] == "#2" for r in keyword_rows)

    # sync_keyword_now itself is a retired write path and always raises.
    with pytest.raises(Exception, match=_FEATURE_RETIRED_MESSAGE):
        services["tracking_service"].sync_keyword_now("messenger", "com.whatsapp", "us", "en")

    # --- chart monitoring: add control + table exist and add still works (CRUD) ---
    assert tracking_page.chart_table is not None
    assert tracking_page.add_chart_button is not None
    tracking_page.chart_app_id_input.setText("com.x1")
    tracking_page.chart_collection_combo.setCurrentText("top_free")
    tracking_page.chart_category_input.setText("APPLICATION")
    tracking_page.add_chart_button.click()
    _wait_idle(app, tracking_page)
    assert any(c.app_id == "com.x1" for c in tracking_page.chart_apps)

    # the rank display is a read path and still works off a directly-seeded row ...
    _seed_chart_rank(db, app_id="com.x1", collection="top_free", category="APPLICATION", rank=2)
    chart_rows = tracking_page._collect_tracking_data()["chart_rows"]
    assert any(r["app_id"] == "com.x1" and r["rank"] == "#2" for r in chart_rows)

    # ... while sync_chart_now itself is a retired write path and always raises.
    with pytest.raises(Exception, match=_FEATURE_RETIRED_MESSAGE):
        services["tracking_service"].sync_chart_now("com.x1", "top_free", "APPLICATION", "us", "en")
