from __future__ import annotations

from pydantic import BaseModel


class TrackedApp(BaseModel):
    app_id: str
    title: str | None = None
    country: str = "us"
    lang: str = "en"
    frequency: str = "daily"
    enabled: bool = True
    last_synced_at: str | None = None


class TrackedKeyword(BaseModel):
    keyword: str
    app_id: str
    country: str = "us"
    lang: str = "en"
    frequency: str = "daily"
    enabled: bool = True
    last_synced_at: str | None = None
