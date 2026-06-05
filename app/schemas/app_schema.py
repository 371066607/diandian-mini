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
    summary: str | None = None
    rating: float | None = None
    score_text: str | None = None
    ratings_count: int | None = None
    reviews_count: int | None = None
    installs: str | None = None
    min_installs: int | None = None
    price: str | None = None
    currency: str | None = None
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
    # --- Extended app_analyze fields (gplay-scraper 57-field parity) ---
    genre_id: str | None = None
    categories: list[str] = Field(default_factory=list)
    available: bool | None = None
    app_age_days: int | None = None
    video: str | None = None
    video_image: str | None = None
    daily_installs: int | None = None
    min_daily_installs: int | None = None
    real_daily_installs: int | None = None
    monthly_installs: int | None = None
    min_monthly_installs: int | None = None
    real_monthly_installs: int | None = None
    ad_supported: bool | None = None
    max_android_api: int | None = None
    min_android_api: int | None = None
    app_bundle: str | None = None
    content_rating_description: str | None = None
    permissions: dict[str, Any] = Field(default_factory=dict)
    data_safety: list[Any] = Field(default_factory=list)
    sale: bool | None = None
    original_price: float | None = None
    developer_address: str | None = None
    developer_phone: str | None = None
    publisher_country: str | None = None
