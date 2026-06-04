from __future__ import annotations

import logging

from sqlalchemy import Float, Integer, inspect, text

from app.db.database import Database
from app.db.models import Base

logger = logging.getLogger(__name__)


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
