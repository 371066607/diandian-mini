from __future__ import annotations

import logging

from sqlalchemy import Float, Integer, inspect, text

from app.db.database import Database
from app.db.models import Base

logger = logging.getLogger(__name__)

# Indexes to ensure on every startup. ``create_all`` only attaches these to *newly*
# created tables, so an older database whose tables already exist never gets them.
# Each entry is (index_name, table_name, (columns...)) and is created idempotently
# with ``CREATE INDEX IF NOT EXISTS`` below. Keep in sync with the ``Index`` defs in
# app/db/models.py.
TIME_SERIES_INDEXES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("ix_app_snapshots_lookup", "app_snapshots", ("app_id", "country", "lang", "captured_at")),
    (
        "ix_keyword_ranks_lookup",
        "keyword_ranks",
        ("keyword", "app_id", "country", "lang", "captured_at"),
    ),
    (
        "ix_chart_ranks_lookup",
        "chart_rank_snapshots",
        ("app_id", "collection", "category", "country", "lang", "captured_at"),
    ),
    ("ix_alerts_app_created", "alerts", ("app_id", "created_at")),
    ("ix_alerts_is_read", "alerts", ("is_read",)),
)


def _sqlite_type(column) -> str:
    column_type = column.type
    if isinstance(column_type, Integer):
        return "INTEGER"
    if isinstance(column_type, Float):
        return "REAL"
    return "TEXT"


def migrate(database: Database) -> None:
    """Create missing tables, then additively add any missing columns.

    ``create_all`` only creates whole tables; it never alters an existing one, so a
    column added to a model would silently never appear on an older database. This
    fills that gap with ``ALTER TABLE ... ADD COLUMN`` for the missing columns only
    (never dropping or retyping). Each statement is isolated and best-effort: a
    failure is logged but never propagates, so a migration problem can't brick
    startup the way the old code paths could.
    """
    database.create_all()

    inspector = inspect(database.engine)
    existing_tables = set(inspector.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # freshly created by create_all() with the full, current schema
        existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing_columns:
                continue
            ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {_sqlite_type(column)}'
            try:
                with database.engine.begin() as connection:
                    connection.execute(text(ddl))
                logger.info("migrate: added column %s.%s", table.name, column.name)
            except Exception:
                logger.exception("migrate: failed to add column %s.%s", table.name, column.name)

    # Backfill ``platform`` on legacy keyword rows. The additive column add above leaves
    # NULL on rows that predate the column, but keyword reads/updates now filter on
    # platform — NULL rows would silently vanish from history and monitors. Everything
    # written before the column existed was Google Play by definition. Idempotent and
    # best-effort, same tolerance as the column adds.
    for table_name in ("tracked_keywords", "keyword_ranks"):
        ddl = (
            f'UPDATE "{table_name}" SET platform = \'google_play\' '
            "WHERE platform IS NULL OR platform = ''"
        )
        try:
            with database.engine.begin() as connection:
                result = connection.execute(text(ddl))
                if result.rowcount:
                    logger.info(
                        "migrate: backfilled platform on %s rows in %s",
                        result.rowcount,
                        table_name,
                    )
        except Exception:
            logger.exception("migrate: platform backfill failed for %s", table_name)

    # Ensure time-series / lookup indexes exist on pre-existing tables (create_all only
    # attaches indexes to tables it freshly creates). Idempotent and best-effort: each in
    # its own transaction, failures logged not raised — same tolerance as the column adds.
    for index_name, table_name, columns in TIME_SERIES_INDEXES:
        cols = ", ".join(f'"{col}"' for col in columns)
        ddl = f'CREATE INDEX IF NOT EXISTS "{index_name}" ON "{table_name}" ({cols})'
        try:
            with database.engine.begin() as connection:
                connection.execute(text(ddl))
        except Exception:
            logger.exception("migrate: failed to create index %s on %s", index_name, table_name)
