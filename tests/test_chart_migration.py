from sqlalchemy import text

from app.db.database import Database
from app.db.migrations import migrate


def _table_names(database):
    with database.engine.begin() as conn:
        rows = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        ).fetchall()
    return {r[0] for r in rows}


def _index_names(database):
    with database.engine.begin() as conn:
        rows = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='index'")
        ).fetchall()
    return {r[0] for r in rows}


def test_migrate_creates_chart_tables_and_index_on_fresh_db(tmp_path):
    database = Database(str(tmp_path / "fresh.sqlite3"))
    migrate(database)
    tables = _table_names(database)
    assert "tracked_chart_apps" in tables
    assert "chart_rank_snapshots" in tables
    assert "ix_chart_ranks_lookup" in _index_names(database)


def test_migrate_adds_chart_index_on_legacy_db(tmp_path):
    database = Database(str(tmp_path / "legacy.sqlite3"))
    # Legacy chart_rank_snapshots table WITHOUT the lookup index.
    with database.engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE chart_rank_snapshots (id INTEGER PRIMARY KEY, app_id TEXT, "
            "collection TEXT, category TEXT, country TEXT, lang TEXT, rank INTEGER, "
            "found INTEGER, checked_limit INTEGER, captured_at TEXT)"
        ))

    migrate(database)
    assert "ix_chart_ranks_lookup" in _index_names(database)
    # tracked_chart_apps was missing entirely -> create_all adds it
    assert "tracked_chart_apps" in _table_names(database)

    # idempotent: a second run must not raise and the index is still present
    migrate(database)
    assert "ix_chart_ranks_lookup" in _index_names(database)
