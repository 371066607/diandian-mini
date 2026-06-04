from __future__ import annotations

from sqlalchemy import Float, Integer, String, Text, UniqueConstraint
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


class TrackedAppModel(Base):
    __tablename__ = "tracked_apps"
    __table_args__ = (UniqueConstraint("platform", "app_id", "country", "lang"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String, default="google_play", nullable=False)
    app_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String)
    country: Mapped[str] = mapped_column(String, default="us")
    lang: Mapped[str] = mapped_column(String, default="en")
    frequency: Mapped[str] = mapped_column(String, default="daily")
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_synced_at: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class TrackedKeywordModel(Base):
    __tablename__ = "tracked_keywords"
    __table_args__ = (UniqueConstraint("platform", "app_id", "keyword", "country", "lang"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String, default="google_play", nullable=False)
    app_id: Mapped[str] = mapped_column(String, nullable=False)
    keyword: Mapped[str] = mapped_column(String, nullable=False)
    country: Mapped[str] = mapped_column(String, default="us")
    lang: Mapped[str] = mapped_column(String, default="en")
    frequency: Mapped[str] = mapped_column(String, default="daily")
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_synced_at: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class AlertModel(Base):
    __tablename__ = "alerts"

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
