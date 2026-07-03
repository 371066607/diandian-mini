from __future__ import annotations

import csv
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from app.db.database import Database
from app.db.models import AppSnapshotModel
from app.schemas.app_schema import AppDetail
from app.services.export_service import ExportService
from app.services.tracking_service import TrackingService
from app.utils.install_parser import parse_install_range
from app.utils.normalize import bool_to_int, dump_json


class CountingGooglePlayService:
    """Records every call so tests can assert the offline paths never scrape."""

    def __init__(self):
        self.detail_calls = 0
        self.search_calls = 0

    def app_detail(self, app_id, country="us", lang="en"):  # pragma: no cover - guard
        self.detail_calls += 1
        raise AssertionError("app_detail must not be called by offline history paths")

    def search(self, keyword, country="us", lang="en", limit=50):  # pragma: no cover
        self.search_calls += 1
        raise AssertionError("search must not be called by offline history paths")


def _detail(app_id="com.whatsapp", **overrides) -> AppDetail:
    base = dict(
        app_id=app_id,
        title="WhatsApp",
        rating=4.0,
        ratings_count=100,
        reviews_count=10,
        real_installs=1_000_000,
        installs="1,000,000+",
        version="1.0",
        price="$0.00",
        contains_ads=False,
    )
    base.update(overrides)
    return AppDetail(**base)


def _seed_day(ts, detail, day_iso):
    """Write one snapshot row stamped at the given ISO timestamp (per-day dedup).

    ``SnapshotRepository.upsert_for_day`` (the live scraper's write path) was
    retired along with the rest of the scrape-write pipeline, so tests seed
    history rows by constructing ``AppSnapshotModel`` directly instead -- the
    read paths under test (``history_with_diffs`` / ``export_app_snapshots``)
    are unaffected by the retirement and still need real rows to read.
    """
    min_installs, max_installs = parse_install_range(detail.installs)
    with ts.database.session() as session:
        session.add(
            AppSnapshotModel(
                captured_at=day_iso,
                platform=detail.platform,
                app_id=detail.app_id,
                country="us",
                lang="en",
                title=detail.title,
                developer=detail.developer,
                category=detail.category,
                rating=detail.rating,
                ratings_count=detail.ratings_count,
                reviews_count=detail.reviews_count,
                installs=detail.installs,
                min_installs=detail.min_installs or min_installs,
                max_installs=max_installs,
                real_installs=detail.real_installs,
                price=detail.price,
                free=bool_to_int(detail.free),
                has_iap=bool_to_int(detail.has_iap),
                version=detail.version,
                updated=detail.updated,
                released=detail.released,
                android_version=detail.android_version,
                content_rating=detail.content_rating,
                description=detail.description,
                summary=detail.summary,
                changelog=detail.changelog,
                icon_url=detail.icon_url,
                screenshots_json=dump_json(detail.screenshots),
                contains_ads=bool_to_int(detail.contains_ads),
            )
        )


def _make_tracking(database):
    gp = CountingGooglePlayService()
    ts = TrackingService(database=database, google_play_service=gp)
    return ts, gp


def test_history_with_diffs_empty(tmp_path):
    db = Database(str(tmp_path / "h.sqlite3"))
    db.create_all()
    ts, gp = _make_tracking(db)
    assert ts.history_with_diffs("com.whatsapp", "us", "en") == []
    assert gp.detail_calls == 0


def test_history_with_diffs_deltas_and_changes(tmp_path):
    db = Database(str(tmp_path / "h.sqlite3"))
    db.create_all()
    ts, gp = _make_tracking(db)

    _seed_day(
        ts,
        _detail(
            rating=4.0,
            ratings_count=100,
            reviews_count=10,
            real_installs=1_000_000,
            version="1.0",
            price="$0.00",
        ),
        "2024-01-01T08:00:00",
    )
    _seed_day(
        ts,
        _detail(
            rating=4.5,
            ratings_count=150,
            reviews_count=8,
            real_installs=1_500_000,
            version="1.1",
            price="$0.00",
        ),
        "2024-01-02T08:00:00",
    )
    _seed_day(
        ts,
        _detail(
            rating=4.2,
            ratings_count=120,
            reviews_count=8,
            real_installs=1_400_000,
            version="1.1",
            price="$1.00",
        ),
        "2024-01-03T08:00:00",
    )

    rows = ts.history_with_diffs("com.whatsapp", "us", "en")
    assert len(rows) == 3
    assert gp.detail_calls == 0

    first, second, third = rows
    # First row: every delta is None, discrete fields unchanged.
    assert first["rating_delta"] is None
    assert first["ratings_count_delta"] is None
    assert first["version_changed"] is False
    assert first["price_changed"] is False

    # Second row: positive and negative deltas, version changed.
    assert second["rating_delta"] == pytest.approx(0.5)
    assert second["ratings_count_delta"] == pytest.approx(50)
    assert second["reviews_count_delta"] == pytest.approx(-2)  # negative delta
    assert second["real_installs_delta"] == pytest.approx(500_000)
    assert second["version_changed"] is True
    assert second["price_changed"] is False

    # Third row: rating drop, price change, version unchanged.
    assert third["rating_delta"] == pytest.approx(-0.3)
    assert third["ratings_count_delta"] == pytest.approx(-30)
    assert third["version_changed"] is False
    assert third["price_changed"] is True

    # Current values carried through.
    assert third["rating"] == pytest.approx(4.2)
    assert third["version"] == "1.1"
    assert third["price"] == "$1.00"


def test_history_with_diffs_range_filter(tmp_path):
    db = Database(str(tmp_path / "h.sqlite3"))
    db.create_all()
    ts, _ = _make_tracking(db)
    for day in ("2024-01-01", "2024-01-02", "2024-01-03"):
        _seed_day(ts, _detail(version=day), f"{day}T08:00:00")

    sliced = ts.history_with_diffs(
        "com.whatsapp", "us", "en", start="2024-01-02", end="2024-01-02T23:59:59"
    )
    assert [r["captured_at"][:10] for r in sliced] == ["2024-01-02"]
    # First row in a slice still has no delta baseline.
    assert sliced[0]["rating_delta"] is None


def test_export_app_snapshots_range_and_backcompat(tmp_path):
    db = Database(str(tmp_path / "h.sqlite3"))
    db.create_all()
    ts, _ = _make_tracking(db)
    for day in ("2024-01-01", "2024-01-02", "2024-01-03"):
        _seed_day(ts, _detail(), f"{day}T08:00:00")

    export = ExportService(db)

    # Backward-compatible: no range == full history (regression guard).
    full_path = tmp_path / "full.csv"
    assert export.export_app_snapshots("com.whatsapp", "us", "en", str(full_path)) == 3
    with open(full_path, encoding="utf-8-sig", newline="") as fh:
        assert len(list(csv.reader(fh))) == 4  # header + 3 rows

    # Range slices the rows.
    range_path = tmp_path / "range.csv"
    count = export.export_app_snapshots(
        "com.whatsapp",
        "us",
        "en",
        str(range_path),
        start="2024-01-02",
        end="2024-01-03T23:59:59",
    )
    assert count == 2
    with open(range_path, encoding="utf-8-sig", newline="") as fh:
        assert len(list(csv.reader(fh))) == 3  # header + 2 rows


# --- GUI smoke (offscreen) ---------------------------------------------------

pytest.importorskip("PySide6")


def _build_gui_services(db):
    from app.services.keyword_service import KeywordService
    from app.services.settings_service import SettingsService

    settings_service = SettingsService(db)
    settings_service.ensure_defaults()
    gp = CountingGooglePlayService()
    keyword_service = KeywordService(gp, database=db)
    tracking_service = TrackingService(
        database=db, google_play_service=gp, keyword_service=keyword_service
    )
    return {
        "settings_service": settings_service,
        "tracking_service": tracking_service,
        "keyword_service": keyword_service,
        "export_service": ExportService(db),
    }, gp


def _wait_idle(app, page, timeout=10.0):
    import time

    deadline = time.time() + timeout
    for _ in range(3):
        app.processEvents()
    while getattr(page, "_workers", []) and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    for _ in range(5):
        app.processEvents()


def test_history_page_smoke(tmp_path, monkeypatch):
    import logging

    from PySide6.QtWidgets import QApplication

    try:
        app = QApplication.instance() or QApplication([])
    except Exception:  # pragma: no cover - no Qt platform
        pytest.skip("no Qt platform available")

    import app.ui.pages.base_page as base_page

    monkeypatch.setattr(base_page, "show_error", lambda *a, **k: None)
    monkeypatch.setattr(base_page, "show_info", lambda *a, **k: None)

    db = Database(str(tmp_path / "gui.sqlite3"))
    db.create_all()
    services, gp = _build_gui_services(db)
    ts = services["tracking_service"]
    ts.add_app("com.whatsapp", "us", "en")
    _seed_day(ts, _detail(rating=4.0), "2024-01-01T08:00:00")
    _seed_day(ts, _detail(rating=4.5), "2024-01-02T08:00:00")

    from app.ui.pages.history_page import HistoryPage

    page = HistoryPage(services, _StubWindow(), logging.getLogger("history-test"))
    page.on_activated()
    _wait_idle(app, page)

    assert page.app_combo.count() == 1
    assert page.snapshot_table.rowCount() == 2
    assert gp.detail_calls == 0  # purely offline

    # load_app pre-selects the app id.
    page.load_app("com.whatsapp", "us", "en")
    _wait_idle(app, page)
    assert page.app_combo.currentData() == ("com.whatsapp", "us", "en")
    assert page.snapshot_table.rowCount() == 2
    assert gp.detail_calls == 0


class _StubWindow:
    """Minimal window_api for constructing a page in isolation."""

    def show_loading(self, *a, **k):
        pass

    def hide_loading(self, *a, **k):
        pass

    def show_toast(self, *a, **k):
        pass

    def open_history(self, *a, **k):
        pass
