from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AppSummary(BaseModel):
    platform: str = "google_play"
    app_id: str
    title: str | None = None
    developer: str | None = None
    developer_id: str | None = None
    category: str | None = None
    rating: float | None = None
    ratings_count: int | None = None
    reviews_count: int | None = None
    installs: str | None = None
    min_installs: int | None = None
    price: str | None = None
    free: bool | None = None
    has_iap: bool | None = None
    icon_url: str | None = None
    store_url: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class AppDetail(AppSummary):
    version: str | None = None
    updated: str | None = None
    released: str | None = None
    android_version: str | None = None
    content_rating: str | None = None
    description: str | None = None
    summary: str | None = None
    changelog: str | None = None
    screenshots: list[str] = Field(default_factory=list)
    real_installs: int | None = None
    histogram: list[int] = Field(default_factory=list)
    contains_ads: bool | None = None
    iap_price_range: str | None = None
    developer_email: str | None = None
    developer_website: str | None = None
    privacy_policy: str | None = None
    header_image: str | None = None
