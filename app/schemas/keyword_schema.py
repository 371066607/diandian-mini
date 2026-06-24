from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.app_schema import AppSummary


class KeywordRankResult(BaseModel):
    platform: str = "google_play"
    keyword: str
    app_id: str
    country: str = "us"
    lang: str = "en"
    found: bool
    rank: int | None = None
    checked_limit: int
    requested_limit: int | None = None
    returned_count: int | None = None
    coverage_complete: bool = True
    captured_at: str
    results: list[AppSummary] = Field(default_factory=list)
