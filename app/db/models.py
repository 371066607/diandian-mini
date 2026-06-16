from __future__ import annotations

from sqlalchemy import Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AppModel(Base):
    __tablename__ = "apps"
    __table_args__ = (UniqueConstraint("platform", "app_id", "country", "lang"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String, default="google_play", nullable=False)
    app_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String)
    developer: Mapped[str | None] = mapped_column(String)
    developer_id: Mapped[str | None] = mapped_column(String)
    category: Mapped[str | None] = mapped_column(String)
    genre: Mapped[str | None] = mapped_column(String)
    icon_url: Mapped[str | None] = mapped_column(Text)
    store_url: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str] = mapped_column(String, default="us")
    lang: Mapped[str] = mapped_column(String, default="en")
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class AppSnapshotModel(Base):
    __tablename__ = "app_snapshots"
    __table_args__ = (
        Index("ix_app_snapshots_lookup", "app_id", "country", "lang", "captured_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String, default="google_play", nullable=False)
    app_id: Mapped[str] = mapped_column(String, nullable=False)
    country: Mapped[str] = mapped_column(String, default="us")
    lang: Mapped[str] = mapped_column(String, default="en")
    captured_at: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String)
    developer: Mapped[str | None] = mapped_column(String)
    category: Mapped[str | None] = mapped_column(String)
    rating: Mapped[float | None] = mapped_column(Float)
    ratings_count: Mapped[int | None] = mapped_column(Integer)
    reviews_count: Mapped[int | None] = mapped_column(Integer)
    installs: Mapped[str | None] = mapped_column(String)
    min_installs: Mapped[int | None] = mapped_column(Integer)
    max_installs: Mapped[int | None] = mapped_column(Integer)
    real_installs: Mapped[int | None] = mapped_column(Integer)
    price: Mapped[str | None] = mapped_column(String)
    free: Mapped[int | None] = mapped_column(Integer)
    has_iap: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[str | None] = mapped_column(String)
    updated: Mapped[str | None] = mapped_column(String)
    released: Mapped[str | None] = mapped_column(String)
    android_version: Mapped[str | None] = mapped_column(String)
    content_rating: Mapped[str | None] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    changelog: Mapped[str | None] = mapped_column(Text)
    icon_url: Mapped[str | None] = mapped_column(Text)
    screenshots_json: Mapped[str | None] = mapped_column(Text)
    # --- Extended monetization / monitoring fields (AppDetail parity) ---
    contains_ads: Mapped[int | None] = mapped_column(Integer)
    ad_supported: Mapped[int | None] = mapped_column(Integer)
    daily_installs: Mapped[int | None] = mapped_column(Integer)
    min_daily_installs: Mapped[int | None] = mapped_column(Integer)
    real_daily_installs: Mapped[int | None] = mapped_column(Integer)
    monthly_installs: Mapped[int | None] = mapped_column(Integer)
    min_monthly_installs: Mapped[int | None] = mapped_column(Integer)
    real_monthly_installs: Mapped[int | None] = mapped_column(Integer)
    app_age_days: Mapped[int | None] = mapped_column(Integer)
    genre_id: Mapped[str | None] = mapped_column(String)
    developer_id: Mapped[str | None] = mapped_column(String)
    currency: Mapped[str | None] = mapped_column(String)
    sale: Mapped[int | None] = mapped_column(Integer)
    original_price: Mapped[float | None] = mapped_column(Float)
    developer_email: Mapped[str | None] = mapped_column(String)
    developer_website: Mapped[str | None] = mapped_column(Text)
    developer_address: Mapped[str | None] = mapped_column(Text)
    developer_phone: Mapped[str | None] = mapped_column(String)
    publisher_country: Mapped[str | None] = mapped_column(String)
    privacy_policy: Mapped[str | None] = mapped_column(Text)
    header_image: Mapped[str | None] = mapped_column(Text)
    video: Mapped[str | None] = mapped_column(Text)
    content_rating_description: Mapped[str | None] = mapped_column(Text)
    available: Mapped[int | None] = mapped_column(Integer)
    max_android_api: Mapped[int | None] = mapped_column(Integer)
    min_android_api: Mapped[int | None] = mapped_column(Integer)
    app_bundle: Mapped[str | None] = mapped_column(String)
    histogram_json: Mapped[str | None] = mapped_column(Text)
    categories_json: Mapped[str | None] = mapped_column(Text)
    permissions_json: Mapped[str | None] = mapped_column(Text)
    data_safety_json: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[str | None] = mapped_column(Text)


class ReviewModel(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("platform", "app_id", "review_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String, default="google_play", nullable=False)
    app_id: Mapped[str] = mapped_column(String, nullable=False)
    country: Mapped[str] = mapped_column(String, default="us")
    lang: Mapped[str] = mapped_column(String, default="en")
    review_id: Mapped[str | None] = mapped_column(String)
    user_name: Mapped[str | None] = mapped_column(String)
    rating: Mapped[int | None] = mapped_column(Integer)
    content: Mapped[str | None] = mapped_column(Text)
    app_version: Mapped[str | None] = mapped_column(String)
    helpful_count: Mapped[int | None] = mapped_column(Integer)
    review_created_at: Mapped[str | None] = mapped_column(String)
    captured_at: Mapped[str] = mapped_column(String, nullable=False)
    raw_json: Mapped[str | None] = mapped_column(Text)


class ChartSnapshotModel(Base):
    __tablename__ = "chart_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String, default="google_play", nullable=False)
    chart_type: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str | None] = mapped_column(String)
    country: Mapped[str] = mapped_column(String, default="us")
    lang: Mapped[str] = mapped_column(String, default="en")
    captured_at: Mapped[str] = mapped_column(String, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    app_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String)
    developer: Mapped[str | None] = mapped_column(String)
    rating: Mapped[float | None] = mapped_column(Float)
    installs: Mapped[str | None] = mapped_column(String)
    icon_url: Mapped[str | None] = mapped_column(Text)
    raw_json: Mapped[str | None] = mapped_column(Text)


class KeywordRankModel(Base):
    __tablename__ = "keyword_ranks"
    __table_args__ = (
        Index(
            "ix_keyword_ranks_lookup",
            "keyword",
            "app_id",
            "country",
            "lang",
            "captured_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String, default="google_play", nullable=False)
    keyword: Mapped[str] = mapped_column(String, nullable=False)
    app_id: Mapped[str] = mapped_column(String, nullable=False)
    country: Mapped[str] = mapped_column(String, default="us")
    lang: Mapped[str] = mapped_column(String, default="en")
    rank: Mapped[int | None] = mapped_column(Integer)
    found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checked_limit: Mapped[int | None] = mapped_column(Integer)
    captured_at: Mapped[str] = mapped_column(String, nullable=False)
    raw_json: Mapped[str | None] = mapped_column(Text)


class KeywordCorpusModel(Base):
    """Self-accumulating keyword pool, scoped per (platform, country, lang). Every
    coverage scan both feeds this table (candidates, competitor terms, soup hits) and
    reads from it (token-overlapping rows enrich later scans) — so the candidate pool
    grows richer the more apps in a locale get scanned. ``confirmed`` marks a keyword
    that was actually validated as a real coverage hit (highest-value seed)."""

    __tablename__ = "keyword_corpus"
    __table_args__ = (
        UniqueConstraint("platform", "country", "lang", "keyword"),
        Index("ix_keyword_corpus_lookup", "platform", "country", "lang", "confirmed"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String, default="google_play", nullable=False)
    country: Mapped[str] = mapped_column(String, default="us", nullable=False)
    lang: Mapped[str] = mapped_column(String, default="en", nullable=False)
    keyword: Mapped[str] = mapped_column(String, nullable=False)
    # where it first entered the pool: seed / autocomplete / soup / similar / covered
    source: Mapped[str | None] = mapped_column(String)
    # 1 once the keyword was verified to actually surface an app within the rank limit
    confirmed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # how many scans have surfaced this keyword — a cheap relevance/popularity signal
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_seen_at: Mapped[str] = mapped_column(String, nullable=False)
    last_seen_at: Mapped[str] = mapped_column(String, nullable=False)


class ChartRankSnapshotModel(Base):
    __tablename__ = "chart_rank_snapshots"
    __table_args__ = (
        Index(
            "ix_chart_ranks_lookup",
            "app_id",
            "collection",
            "category",
            "country",
            "lang",
            "captured_at",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String, default="google_play", nullable=False)
    app_id: Mapped[str] = mapped_column(String, nullable=False)
    collection: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str | None] = mapped_column(String)
    country: Mapped[str] = mapped_column(String, default="us")
    lang: Mapped[str] = mapped_column(String, default="en")
    rank: Mapped[int | None] = mapped_column(Integer)
    found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checked_limit: Mapped[int | None] = mapped_column(Integer)
    captured_at: Mapped[str] = mapped_column(String, nullable=False)
    raw_json: Mapped[str | None] = mapped_column(Text)


class TrackedAppModel(Base):
    __tablename__ = "tracked_apps"
    __table_args__ = (
        UniqueConstraint("platform", "app_id", "country", "lang"),
        Index("ix_tracked_apps_enabled", "enabled"),
        Index("ix_tracked_apps_synced", "last_synced_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String, default="google_play", nullable=False)
    app_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String)
    country: Mapped[str] = mapped_column(String, default="us")
    lang: Mapped[str] = mapped_column(String, default="en")
    frequency: Mapped[str] = mapped_column(String, default="daily")
    tag: Mapped[str | None] = mapped_column(String)
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_synced_at: Mapped[str | None] = mapped_column(String)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_failed_at: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class TrackedKeywordModel(Base):
    __tablename__ = "tracked_keywords"
    __table_args__ = (
        UniqueConstraint("platform", "app_id", "keyword", "country", "lang"),
        Index("ix_tracked_keywords_enabled", "enabled"),
        Index("ix_tracked_keywords_synced", "last_synced_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String, default="google_play", nullable=False)
    app_id: Mapped[str] = mapped_column(String, nullable=False)
    keyword: Mapped[str] = mapped_column(String, nullable=False)
    country: Mapped[str] = mapped_column(String, default="us")
    lang: Mapped[str] = mapped_column(String, default="en")
    frequency: Mapped[str] = mapped_column(String, default="daily")
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_synced_at: Mapped[str | None] = mapped_column(String)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_failed_at: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class TrackedChartAppModel(Base):
    __tablename__ = "tracked_chart_apps"
    __table_args__ = (
        UniqueConstraint(
            "platform", "app_id", "collection", "category", "country", "lang"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String, default="google_play", nullable=False)
    app_id: Mapped[str] = mapped_column(String, nullable=False)
    collection: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str | None] = mapped_column(String)
    country: Mapped[str] = mapped_column(String, default="us")
    lang: Mapped[str] = mapped_column(String, default="en")
    frequency: Mapped[str] = mapped_column(String, default="daily")
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_synced_at: Mapped[str | None] = mapped_column(String)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_failed_at: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class AlertModel(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_app_created", "app_id", "created_at"),
        Index("ix_alerts_is_read", "is_read"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    app_id: Mapped[str | None] = mapped_column(String)
    title: Mapped[str | None] = mapped_column(String)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[str | None] = mapped_column(Text)
    is_read: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class SettingModel(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
