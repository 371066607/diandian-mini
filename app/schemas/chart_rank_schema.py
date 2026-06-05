from __future__ import annotations

from pydantic import BaseModel


class ChartRankResult(BaseModel):
    platform: str = "google_play"
    app_id: str
    collection: str
    category: str | None = None
    country: str = "us"
    lang: str = "en"
    found: bool
    rank: int | None = None
    checked_limit: int
    captured_at: str
