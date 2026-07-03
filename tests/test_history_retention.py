from __future__ import annotations

from datetime import datetime

from sqlalchemy import text

from app.db.database import Database
from app.db.migrations import migrate
from app.db.models import (
    AlertModel,
    AppSnapshotModel,
    ChartRankSnapshotModel,
    KeywordRankModel,
)
from app.services.history_retention_service import HistoryRetentionService
from app.services.settings_service import SettingsService

OLD = "2020-01-01T00:00:00"  # very old, well before any cutoff
OLDER = "2019-01-01T00:00:00"


def _db(tmp_path):
    db = Database(str(tmp_path / "hr.sqlite3"))
    db.create_all()
    return db


def _settings(db, **overrides):
    svc = SettingsService(db)
    svc.ensure_defaults()
    if overrides:
        svc.set_many({k: str(v) for k, v in overrides.items()})
    return svc


def _add_snapshot(session, app_id, captured_at, country="us", lang="en"):
    session.add(
        AppSnapshotModel(
            platform="google_play",
            app_id=app_id,
            country=country,
            lang=lang,
            captured_at=captured_at,
        )
    )


def _add_keyword(session, keyword, app_id, captured_at, country="us", lang="en"):
    session.add(
        KeywordRankModel(
            platform="google_play",
            keyword=keyword,
            app_id=app_id,
            country=country,
            lang=lang,
            found=1,
            captured_at=captured_at,
        )
    )


def _add_alert(session, app_id, created_at, is_read):
    session.add(
        AlertModel(
            type="rating_drop",
            severity="high",
            app_id=app_id,
            message="m",
            is_read=is_read,
            created_at=created_at,
        )
    )


def _add_chart(session, app_id, captured_at, collection="top_free", category="APPLICATION"):
    session.add(
        ChartRankSnapshotModel(
            platform="google_play",
            app_id=app_id,
            collection=collection,
            category=category,
            country="us",
            lang="en",
            found=1,
            captured_at=captured_at,
        )
    )


def test_cleanup_is_a_structural_noop_regardless_of_settings_or_data(tmp_path):
    # Scraping is retired, so nothing writes new history rows anymore and cleanup()
    # has nothing left to prune. It unconditionally returns zero counts and never
    # touches the database, whether retention is enabled/disabled, cutoffs are tight,
    # or old rows exist across every table cleanup used to sweep.
    db = _db(tmp_path)
    settings = _settings(
        db,
        retention_enabled="true",
        snapshot_retention_days="1",
        keyword_retention_days="1",
        alert_retention_days="1",
        retention_min_keep="1",
    )
    with db.session() as session:
        _add_snapshot(session, "com.a", OLD)
        _add_snapshot(session, "com.a", OLDER)
        _add_keyword(session, "game", "com.a", OLD)
        _add_chart(session, "com.a", OLD)
        _add_alert(session, "com.a", OLD, is_read=1)

    svc = HistoryRetentionService(db, settings_service=settings)
    result = svc.cleanup(now=datetime(2020, 1, 10))
    assert result == {
        "snapshots": 0,
        "keywords": 0,
        "charts": 0,
        "alerts": 0,
        "reviews": 0,
    }

    with db.session() as session:
        snapshot_count = session.execute(text("SELECT COUNT(*) FROM app_snapshots")).scalar()
        keyword_count = session.execute(text("SELECT COUNT(*) FROM keyword_ranks")).scalar()
        chart_count = session.execute(text("SELECT COUNT(*) FROM chart_rank_snapshots")).scalar()
        alert_count = session.execute(text("SELECT COUNT(*) FROM alerts")).scalar()
    assert snapshot_count == 2
    assert keyword_count == 1
    assert chart_count == 1
    assert alert_count == 1


# --- migration / index tests ------------------------------------------------


def _index_names(database):
    with database.engine.begin() as conn:
        rows = conn.execute(text("SELECT name FROM sqlite_master WHERE type='index'")).fetchall()
    return {r[0] for r in rows}


def test_migrate_creates_indexes_on_legacy_db(tmp_path):
    database = Database(str(tmp_path / "legacy.sqlite3"))
    # legacy tables WITHOUT the lookup indexes
    with database.engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE app_snapshots (id INTEGER PRIMARY KEY, app_id TEXT, "
                "country TEXT, lang TEXT, captured_at TEXT)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE keyword_ranks (id INTEGER PRIMARY KEY, keyword TEXT, app_id TEXT, "
                "country TEXT, lang TEXT, captured_at TEXT)"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE alerts (id INTEGER PRIMARY KEY, app_id TEXT, is_read INTEGER, "
                "created_at TEXT, type TEXT, severity TEXT, message TEXT)"
            )
        )

    migrate(database)
    names = _index_names(database)
    for expected in (
        "ix_app_snapshots_lookup",
        "ix_keyword_ranks_lookup",
        "ix_alerts_app_created",
        "ix_alerts_is_read",
    ):
        assert expected in names

    # idempotent: a second run must not raise and indexes still present
    migrate(database)
    assert "ix_app_snapshots_lookup" in _index_names(database)


def test_snapshot_lookup_uses_index(tmp_path):
    database = Database(str(tmp_path / "idx.sqlite3"))
    migrate(database)
    with database.engine.begin() as conn:
        plan = conn.execute(
            text(
                "EXPLAIN QUERY PLAN SELECT * FROM app_snapshots "
                "WHERE app_id=:a AND country=:c AND lang=:l ORDER BY captured_at DESC"
            ),
            {"a": "com.a", "c": "us", "l": "en"},
        ).fetchall()
    detail = " ".join(str(row) for row in plan)
    assert "USING INDEX" in detail
    assert "SCAN app_snapshots" not in detail


# --- settings round-trip ----------------------------------------------------


def test_settings_form_retention_roundtrip(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    import app.ui.widgets.settings_form as settings_form
    from app.ui.widgets.settings_form import SettingsFormWidget

    QApplication.instance() or QApplication([])
    monkeypatch.setattr(settings_form, "show_info", lambda *a, **k: None)
    monkeypatch.setattr(settings_form, "show_error", lambda *a, **k: None)

    db = _db(tmp_path)
    settings = _settings(db)
    services = {
        "settings_service": settings,
        "google_play_service": None,
        "scheduler": None,
    }
    widget = SettingsFormWidget(services)

    widget.retention_enabled.setChecked(False)
    widget.snapshot_retention_days.setValue(90)
    widget.keyword_retention_days.setValue(120)
    widget.alert_retention_days.setValue(400)
    widget.retention_min_keep.setValue(15)
    widget.save()

    stored = settings.get_all()
    assert stored["retention_enabled"] == "false"
    assert stored["snapshot_retention_days"] == "90"
    assert stored["keyword_retention_days"] == "120"
    assert stored["alert_retention_days"] == "400"
    assert stored["retention_min_keep"] == "15"
    assert all(isinstance(v, str) for v in stored.values())
