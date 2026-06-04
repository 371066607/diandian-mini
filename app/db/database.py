from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import resolve_database_path


class Database:
    def __init__(self, database_path: str | None = None):
        self.database_path = resolve_database_path(database_path)
        self.engine = create_engine(
            f"sqlite:///{self.database_path}",
            echo=False,
            future=True,
        )
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
