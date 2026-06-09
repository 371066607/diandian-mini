from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import resolve_database_path


class Database:
    def __init__(self, database_path: str | None = None):
        self.database_path = resolve_database_path(database_path)
        self.engine = create_engine(
            f"sqlite:///{self.database_path}",
            echo=False,
            future=True,
            # Parallel sync issues concurrent writes; let writers wait for the lock.
            connect_args={"timeout": 30},
        )

        @event.listens_for(self.engine, "connect")
        def _set_pragmas(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            # WAL lets readers and one writer proceed simultaneously (vs. the default
            # DELETE journal which blocks reads while writing).
            cur.execute("PRAGMA journal_mode=WAL")
            # NORMAL skips the final sync-to-disk that FULL requires; safe for a local
            # tool where OS-level crash recovery is acceptable.
            cur.execute("PRAGMA synchronous=NORMAL")
            # 32 MB in-process page cache — keeps hot snapshot/alert rows off disk.
            cur.execute("PRAGMA cache_size=-32768")
            # Spill temp tables to RAM instead of a disk file.
            cur.execute("PRAGMA temp_store=MEMORY")
            cur.close()

        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)

    def create_all(self) -> None:
        from app.db.models import Base

        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Session:
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
