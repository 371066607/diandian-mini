from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ReviewItem(BaseModel):
    platform: str = "google_play"
    app_id: str
    country: str | None = None
    lang: str | None = None
    review_id: str | None = None
    user_name: str | None = None
    rating: int | None = None
    content: str | None = None
    app_version: str | None = None
    helpful_count: int | None = None
    review_created_at: str | None = None
    captured_at: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
