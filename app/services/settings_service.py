from __future__ import annotations

from app.constants import DEFAULT_SETTINGS
from app.db.repositories import SettingsRepository


class SettingsService:
    def __init__(self, database):
        self.database = database
        self.repository = SettingsRepository()

    def ensure_defaults(self) -> None:
        with self.database.session() as session:
            current = self.repository.get_all(session)
            for key, value in DEFAULT_SETTINGS.items():
                if key not in current:
                    self.repository.upsert(session, key, value)

    def get_all(self) -> dict[str, str]:
        with self.database.session() as session:
            values = self.repository.get_all(session)
        merged = DEFAULT_SETTINGS.copy()
        merged.update(values)
        return merged

    def get(self, key: str, default: str | None = None) -> str | None:
        return self.get_all().get(key, default)

    def set_many(self, payload: dict[str, str]) -> None:
        with self.database.session() as session:
            for key, value in payload.items():
                self.repository.upsert(session, key, value)
