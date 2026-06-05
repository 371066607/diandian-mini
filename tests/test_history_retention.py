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
from app.utils.time_utils import now_iso

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


def test_cleanup_deletes_expired_beyond_min_keep_and_keeps_newest(tmp_path):
    db = _db(tmp_path)
    settings = _settings(db, retention_enabled="true", snapshot_retention_days="180",
                         retention_min_keep="2")
    recent = now_iso()
    with db.session() as session:
        # 4 old rows + 2 recent rows for the same app
        for ts in (OLDER, OLD, "2020-02-01T00:00:00", "2020-03-01T00:00:00"):
            _add_snapshot(session, "com.a", ts)
        _add_snapshot(session, "com.a", recent)
        _add_snapshot(session, "com.a", "2021-01-01T00:00:00")

    svc = HistoryRetentionService(db, settings_service=settings)
    result = svc.cleanup()
    assert result["snapshots"] > 0

    with db.session() as session:
        rows = session.execute(
            text("SELECT captured_at FROM app_snapshots ORDER BY captured_at DESC")
        ).fetchall()
    kept = [r[0] for r in rows]
    # min_keep=2 → newest 2 always kept; they are the two most recent
    assert len(kept) >= 2
    assert kept[0] == recent
    assert kept[1] == "2021-01-01T00:00:00"
    # the very old rows are gone
    assert OLDER not in kept
    assert OLD not in kept


def test_disabled_is_noop(tmp_path):
    db = _db(tmp_path)
    settings = _settings(db, retention_enabled="false", retention_min_keep="1")
    with db.session() as session:
        _add_snapshot(session, "com.a", OLD)
        _add_snapshot(session, "com.a", OLDER)

    svc = HistoryRetentionService(db, settings_service=settings)
    assert svc.cleanup() == {
        "snapshots": 0,
        "keywords": 0,
        "charts": 0,
        "alerts": 0,
        "reviews": 0,
    }
    with db.session() as session:
        count = session.execute(text("SELECT COUNT(*) FROM app_snapshots")).scalar()
    assert count == 2


def test_all_expired_but_within_min_keep_not_deleted(tmp_path):
    db = _db(tmp_path)
    settings = _settings(db, retention_enabled="true", snapshot_retention_days="180",
                         retention_min_keep="30")
    with db.session() as session:
        # all old, but only 3 rows ≤ min_keep=30 → none deleted, trend stays
        _add_snapshot(session, "com.a", OLDER)
        _add_snapshot(session, "com.a", OLD)
        _add_snapshot(session, "com.a", "2020-06-01T00:00:00")

    svc = HistoryRetentionService(db, settings_service=settings)
    result = svc.cleanup()
    assert result["snapshots"] == 0
    with db.session() as session:
        count = session.execute(text("SELECT COUNT(*) FROM app_snapshots")).scalar()
    assert count == 3


def test_keyword_cleanup_partitions_by_object(tmp_path):
    db = _db(tmp_path)
    settings = _settings(db, retention_enabled="true", keyword_retention_days="180",
                         retention_min_keep="1")
    with db.session() as session:
        for ts in (OLDER, OLD, "2020-05-01T00:00:00"):
            _add_keyword(session, "game", "com.a", ts)
        # a different keyword object — its single old row is within min_keep, kept
        _add_keyword(session, "puzzle", "com.a", OLD)

    svc = HistoryRetentionService(db, settings_service=settings)
    result = svc.cleanup()
    assert result["keywords"] == 2  # 3 'game' rows - min_keep 1 = 2 deleted
    with db.session() as session:
        game = session.execute(
            text("SELECT COUNT(*) FROM keyword_ranks WHERE keyword='game'")
        ).scalar()
        puzzle = session.execute(
            text("SELECT COUNT(*) FROM keyword_ranks WHERE keyword='puzzle'")
        ).scalar()
    assert game == 1
    assert puzzle == 1


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


def test_chart_cleanup_reuses_keyword_window(tmp_path):
    db = _db(tmp_path)
    # charts reuse keyword_retention_days; min_keep=1 keeps the newest only.
    settings = _settings(db, retention_enabled="true", keyword_retention_days="180",
                         retention_min_keep="1")
    with db.session() as session:
        for ts in (OLDER, OLD, "2020-05-01T00:00:00"):
            _add_chart(session, "com.a", ts)

    svc = HistoryRetentionService(db, settings_service=settings)
    result = svc.cleanup()
    assert result["charts"] == 2  # 3 rows - min_keep 1 = 2 deleted
    with db.session() as session:
        count = session.execute(
            text("SELECT COUNT(*) FROM chart_rank_snapshots")
        ).scalar()
    assert count == 1


def test_unread_alerts_never_deleted(tmp_path):
    db = _db(tmp_path)
    settings = _settings(db, retention_enabled="true", alert_retention_days="365",
                         retention_min_keep="1")
    with db.session() as session:
        # unread + old → must survive
        _add_alert(session, "com.a", OLDER, is_read=0)
        _add_alert(session, "com.a", OLD, is_read=0)
        # read + old + beyond min_keep → deleted
        _add_alert(session, "com.a", "2020-02-01T00:00:00", is_read=1)
        _add_alert(session, "com.a", "2020-03-01T00:00:00", is_read=1)
        # recent read → kept (newest, within min_keep)
        _add_alert(session, "com.a", now_iso(), is_read=1)

    svc = HistoryRetentionService(db, settings_service=settings)
    result = svc.cleanup()
    assert result["alerts"] >= 1

    with db.session() as session:
        unread = session.execute(
            text("SELECT COUNT(*) FROM alerts WHERE is_read=0")
        ).scalar()
        old_read = session.execute(
            text("SELECT COUNT(*) FROM alerts WHERE is_read=1 AND created_at < '2021-01-01'")
        ).scalar()
    assert unread == 2  # both unread olds preserved
    assert old_read == 0  # old read alerts (beyond min_keep) cleaned


def test_now_is_injectable(tmp_path):
    db = _db(tmp_path)
    settings = _settings(db, retention_enabled="true", snapshot_retention_days="1",
                         retention_min_keep="1")
    with db.session() as session:
        _add_snapshot(session, "com.a", "2020-01-01T00:00:00")
        _add_snapshot(session, "com.a", "2020-01-02T00:00:00")

    svc = HistoryRetentionService(db, settings_service=settings)
    # with now pinned to 2020-01-10, the 2020-01-01 row is older than 1 day cutoff
    result = svc.cleanup(now=datetime(2020, 1, 10))
    assert result["snapshots"] == 1
    with db.session() as session:
        kept = session.execute(
            text("SELECT captured_at FROM app_snapshots")
        ).scalars().all()
    assert kept == ["2020-01-02T00:00:00"]


# --- migration / index tests ------------------------------------------------


def _index_names(database):
    with database.engine.begin() as conn:
        rows = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='index'")
        ).fetchall()
    return {r[0] for r in rows}


def test_migrate_creates_indexes_on_legacy_db(tmp_path):
    database = Database(str(tmp_path / "legacy.sqlite3"))
    # legacy tables WITHOUT the lookup indexes
    with database.engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE app_snapshots (id INTEGER PRIMARY KEY, app_id TEXT, "
            "country TEXT, lang TEXT, captured_at TEXT)"
        ))
        conn.execute(text(
            "CREATE TABLE keyword_ranks (id INTEGER PRIMARY KEY, keyword TEXT, app_id TEXT, "
            "country TEXT, lang TEXT, captured_at TEXT)"
        ))
        conn.execute(text(
            "CREATE TABLE alerts (id INTEGER PRIMARY KEY, app_id TEXT, is_read INTEGER, "
            "created_at TEXT, type TEXT, severity TEXT, message TEXT)"
        ))

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
        plan = conn.execute(text(
            "EXPLAIN QUERY PLAN SELECT * FROM app_snapshots "
            "WHERE app_id=:a AND country=:c AND lang=:l ORDER BY captured_at DESC"
        ), {"a": "com.a", "c": "us", "l": "en"}).fetchall()
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
