import pytest
from sqlalchemy import inspect, text

from app.db.database import Database
from app.db.migrations import migrate

pytestmark = pytest.mark.legacy


def test_migrate_creates_all_tables(tmp_path):
    database = Database(str(tmp_path / "m.sqlite3"))
    migrate(database)
    tables = set(inspect(database.engine).get_table_names())
    assert {
        "tracked_apps",
        "tracked_keywords",
        "app_snapshots",
        "alerts",
        "settings",
        "keyword_ranks",
        "reviews",
        "chart_snapshots",
    } <= tables


def test_migrate_adds_missing_columns(tmp_path):
    database = Database(str(tmp_path / "m2.sqlite3"))
    # Simulate an older schema: tracked_apps exists but is missing newer columns.
    with database.engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE tracked_apps ("
                "id INTEGER PRIMARY KEY, app_id TEXT NOT NULL, "
                "created_at TEXT, updated_at TEXT)"
            )
        )

    migrate(database)

    columns = {c["name"] for c in inspect(database.engine).get_columns("tracked_apps")}
    for expected in [
        "platform",
        "title",
        "country",
        "lang",
        "frequency",
        "enabled",
        "last_synced_at",
    ]:
        assert expected in columns


def test_migrate_adds_real_installs_to_existing_snapshots(tmp_path):
    database = Database(str(tmp_path / "snap-mig.sqlite3"))
    # an existing app_snapshots table from before the real_installs column existed
    with database.engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE app_snapshots ("
                "id INTEGER PRIMARY KEY, app_id TEXT NOT NULL, captured_at TEXT)"
            )
        )

    migrate(database)

    columns = {c["name"] for c in inspect(database.engine).get_columns("app_snapshots")}
    assert "real_installs" in columns
    assert "min_installs" in columns


def test_migrate_is_idempotent(tmp_path):
    database = Database(str(tmp_path / "m3.sqlite3"))
    migrate(database)
    before = {c["name"] for c in inspect(database.engine).get_columns("tracked_apps")}
    migrate(database)  # a second run must neither raise nor change the schema
    after = {c["name"] for c in inspect(database.engine).get_columns("tracked_apps")}
    assert before == after
