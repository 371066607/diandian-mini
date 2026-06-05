from __future__ import annotations

from pydantic import Field

from app.schemas.app_schema import AppSummary


class ChartItem(AppSummary):
    rank: int
    chart_type: str
    category: str | None = None
    country: str = "us"
    lang: str = "en"
    screenshots: list[str] = Field(default_factory=list)
    description: str | None = None
