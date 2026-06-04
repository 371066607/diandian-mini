from __future__ import annotations

from app.schemas.app_schema import AppSummary


class ChartItem(AppSummary):
    rank: int
    chart_type: str
    category: str | None = None
    country: str = "us"
    lang: str = "en"
