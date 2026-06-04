from __future__ import annotations

from sqlalchemy import desc, func, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.models import (
    AlertModel,
    AppSnapshotModel,
    ChartSnapshotModel,
    KeywordRankModel,
    ReviewModel,
    SettingModel,
    TrackedAppModel,
    TrackedKeywordModel,
)
from app.schemas.app_schema import AppDetail
from app.schemas.chart_schema import ChartItem
from app.schemas.keyword_schema import KeywordRankResult
from app.schemas.review_schema import ReviewItem
from app.utils.install_parser import parse_install_range
from app.utils.normalize import bool_to_int, dump_json
from app.utils.time_utils import now_iso


class SettingsRepository:
    def get_all(self, session) -> dict[str, str]:
        rows = session.execute(select(SettingModel)).scalars().all()
        return {row.key: row.value or "" for row in rows}

    def upsert(self, session, key: str, value: str) -> None:
        row = session.get(SettingModel, key)
        if row is None:
            row = SettingModel(key=key, value=value, updated_at=now_iso())
            session.add(row)
            return
        row.value = value
        row.updated_at = now_iso()


class AlertRepository:
    def unread_count(self, session) -> int:
        stmt = select(func.count()).select_from(AlertModel).where(AlertModel.is_read == 0)
        return session.scalar(stmt) or 0

    def list_recent(self, session, limit: int = 10) -> list[AlertModel]:
        stmt = select(AlertModel).order_by(desc(AlertModel.created_at)).limit(limit)
        return session.execute(stmt).scalars().all()

    def create(self, session, alert_type: str, severity: str, message: str, **payload) -> None:
        session.add(
            AlertModel(
                type=alert_type,
                severity=severity,
                message=message,
                payload_json=dump_json(payload),
                title=payload.get("title"),
                app_id=payload.get("app_id"),
                created_at=now_iso(),
            )
        )

    def mark_all_read(self, session) -> int:
        result = session.execute(
            update(AlertModel).where(AlertModel.is_read == 0).values(is_read=1)
        )
        return max(result.rowcount, 0)


class SnapshotRepository:
    def count(self, session) -> int:
        return session.scalar(select(func.count()).select_from(AppSnapshotModel)) or 0

    def list_recent(self, session, limit: int = 8) -> list[AppSnapshotModel]:
        stmt = select(AppSnapshotModel).order_by(desc(AppSnapshotModel.captured_at)).limit(limit)
        return session.execute(stmt).scalars().all()

    def save_detail(self, session, detail: AppDetail, country: str, lang: str) -> None:
        min_installs, max_installs = parse_install_range(detail.installs)
        session.add(
            AppSnapshotModel(
                platform=detail.platform,
                app_id=detail.app_id,
                country=country,
                lang=lang,
                captured_at=now_iso(),
                title=detail.title,
                developer=detail.developer,
                category=detail.category,
                rating=detail.rating,
                ratings_count=detail.ratings_count,
                reviews_count=detail.reviews_count,
                installs=detail.installs,
                min_installs=detail.min_installs or min_installs,
                max_installs=max_installs,
                real_installs=detail.real_installs,
                price=detail.price,
                free=bool_to_int(detail.free),
                has_iap=bool_to_int(detail.has_iap),
                version=detail.version,
                updated=detail.updated,
                released=detail.released,
                android_version=detail.android_version,
                content_rating=detail.content_rating,
                description=detail.description,
                summary=detail.summary,
                changelog=detail.changelog,
                icon_url=detail.icon_url,
                screenshots_json=dump_json(detail.screenshots),
                raw_json=dump_json(detail.raw),
            )
        )

    def get_history(
        self,
        session,
        app_id: str,
        country: str = "us",
        lang: str = "en",
    ) -> list[AppSnapshotModel]:
        stmt = (
            select(AppSnapshotModel)
            .where(
                AppSnapshotModel.app_id == app_id,
                AppSnapshotModel.country == country,
                AppSnapshotModel.lang == lang,
            )
            .order_by(AppSnapshotModel.captured_at.asc())
        )
        return session.execute(stmt).scalars().all()

    def latest(
        self,
        session,
        app_id: str,
        country: str = "us",
        lang: str = "en",
    ) -> AppSnapshotModel | None:
        stmt = (
            select(AppSnapshotModel)
            .where(
                AppSnapshotModel.app_id == app_id,
                AppSnapshotModel.country == country,
                AppSnapshotModel.lang == lang,
            )
            .order_by(desc(AppSnapshotModel.captured_at))
            .limit(1)
        )
        return session.execute(stmt).scalars().first()


class ReviewRepository:
    def save_reviews(
        self,
        session,
        app_id: str,
        country: str,
        lang: str,
        items: list[ReviewItem],
    ) -> int:
        count = 0
        for item in items:
            existing = session.execute(
                select(ReviewModel).where(
                    ReviewModel.platform == item.platform,
                    ReviewModel.app_id == app_id,
                    ReviewModel.review_id == item.review_id,
                )
            ).scalar_one_or_none()
            if existing is not None:
                continue
            # on_conflict_do_nothing guards the race where two concurrent saves of the
            # same review both pass the existence check and then both flush, which would
            # otherwise raise a UNIQUE IntegrityError at commit.
            stmt = (
                sqlite_insert(ReviewModel)
                .values(
                    platform=item.platform,
                    app_id=app_id,
                    country=country,
                    lang=lang,
                    review_id=item.review_id,
                    user_name=item.user_name,
                    rating=item.rating,
                    content=item.content,
                    app_version=item.app_version,
                    helpful_count=item.helpful_count,
                    review_created_at=item.review_created_at,
                    captured_at=now_iso(),
                    raw_json=dump_json(item.raw),
                )
                .on_conflict_do_nothing(index_elements=["platform", "app_id", "review_id"])
            )
            count += max(session.execute(stmt).rowcount, 0)
        return count

    def list_by_app(self, session, app_id: str, limit: int = 100) -> list[ReviewModel]:
        stmt = (
            select(ReviewModel)
            .where(ReviewModel.app_id == app_id)
            .order_by(desc(ReviewModel.review_created_at))
            .limit(limit)
        )
        return session.execute(stmt).scalars().all()


class ChartRepository:
    def save_snapshot(
        self,
        session,
        chart_type: str,
        category: str | None,
        country: str,
        lang: str,
        items: list[ChartItem],
    ) -> int:
        captured_at = now_iso()
        for item in items:
            session.add(
                ChartSnapshotModel(
                    platform=item.platform,
                    chart_type=chart_type,
                    category=category,
                    country=country,
                    lang=lang,
                    captured_at=captured_at,
                    rank=item.rank,
                    app_id=item.app_id,
                    title=item.title,
                    developer=item.developer,
                    rating=item.rating,
                    installs=item.installs,
                    icon_url=item.icon_url,
                    raw_json=dump_json(item.raw),
                )
            )
        return len(items)


class KeywordRankRepository:
    def save(self, session, result: KeywordRankResult) -> None:
        session.add(
            KeywordRankModel(
                platform=result.platform,
                keyword=result.keyword,
                app_id=result.app_id,
                country=result.country,
                lang=result.lang,
                rank=result.rank,
                found=1 if result.found else 0,
                checked_limit=result.checked_limit,
                captured_at=result.captured_at,
                raw_json=dump_json([item.model_dump(mode="json") for item in result.results]),
            )
        )

    def history(
        self,
        session,
        keyword: str,
        app_id: str,
        country: str,
        lang: str,
    ) -> list[KeywordRankModel]:
        stmt = (
            select(KeywordRankModel)
            .where(
                KeywordRankModel.keyword == keyword,
                KeywordRankModel.app_id == app_id,
                KeywordRankModel.country == country,
                KeywordRankModel.lang == lang,
            )
            .order_by(KeywordRankModel.captured_at.asc())
        )
        return session.execute(stmt).scalars().all()

    def latest(
        self,
        session,
        keyword: str,
        app_id: str,
        country: str,
        lang: str,
    ) -> KeywordRankModel | None:
        stmt = (
            select(KeywordRankModel)
            .where(
                KeywordRankModel.keyword == keyword,
                KeywordRankModel.app_id == app_id,
                KeywordRankModel.country == country,
                KeywordRankModel.lang == lang,
            )
            .order_by(desc(KeywordRankModel.captured_at))
            .limit(1)
        )
        return session.execute(stmt).scalars().first()

    def list_recent(self, session, limit: int = 8) -> list[KeywordRankModel]:
        stmt = select(KeywordRankModel).order_by(desc(KeywordRankModel.captured_at)).limit(limit)
        return session.execute(stmt).scalars().all()


class TrackingRepository:
    def add_app(
        self,
        session,
        app_id: str,
        title: str | None,
        country: str,
        lang: str,
    ) -> TrackedAppModel:
        now = now_iso()
        insert_stmt = sqlite_insert(TrackedAppModel).values(
            platform="google_play",
            app_id=app_id,
            title=title,
            country=country,
            lang=lang,
            enabled=1,
            created_at=now,
            updated_at=now,
        )
        # Atomic upsert: a plain check-then-insert races when the daily scheduler
        # sync and a manual "add/sync" touch the same app concurrently, raising a
        # UNIQUE IntegrityError at commit. ON CONFLICT DO UPDATE makes it safe and
        # keeps the existing title/created_at while re-enabling the row.
        upsert = insert_stmt.on_conflict_do_update(
            index_elements=["platform", "app_id", "country", "lang"],
            set_={
                "enabled": 1,
                "title": func.coalesce(insert_stmt.excluded.title, TrackedAppModel.title),
                "updated_at": now,
            },
        )
        session.execute(upsert)
        return session.execute(
            select(TrackedAppModel).where(
                TrackedAppModel.platform == "google_play",
                TrackedAppModel.app_id == app_id,
                TrackedAppModel.country == country,
                TrackedAppModel.lang == lang,
            )
        ).scalar_one()

    def remove_app(self, session, app_id: str, country: str, lang: str) -> int:
        model = session.execute(
            select(TrackedAppModel).where(
                TrackedAppModel.app_id == app_id,
                TrackedAppModel.country == country,
                TrackedAppModel.lang == lang,
            )
        ).scalar_one_or_none()
        if model is None:
            return 0
        session.delete(model)
        return 1

    def list_apps(self, session) -> list[TrackedAppModel]:
        stmt = select(TrackedAppModel).order_by(desc(TrackedAppModel.updated_at))
        return session.execute(stmt).scalars().all()

    def update_sync_time(self, session, app_id: str, country: str, lang: str, value: str) -> None:
        model = session.execute(
            select(TrackedAppModel).where(
                TrackedAppModel.app_id == app_id,
                TrackedAppModel.country == country,
                TrackedAppModel.lang == lang,
            )
        ).scalar_one_or_none()
        if model is None:
            return
        model.last_synced_at = value
        model.updated_at = value

    def set_app_enabled(
        self,
        session,
        app_id: str,
        country: str,
        lang: str,
        enabled: bool,
    ) -> bool:
        model = session.execute(
            select(TrackedAppModel).where(
                TrackedAppModel.app_id == app_id,
                TrackedAppModel.country == country,
                TrackedAppModel.lang == lang,
            )
        ).scalar_one_or_none()
        if model is None:
            return enabled
        model.enabled = 1 if enabled else 0
        model.updated_at = now_iso()
        return bool(model.enabled)

    def add_keyword(
        self,
        session,
        keyword: str,
        app_id: str,
        country: str,
        lang: str,
    ) -> TrackedKeywordModel:
        now = now_iso()
        insert_stmt = sqlite_insert(TrackedKeywordModel).values(
            platform="google_play",
            keyword=keyword,
            app_id=app_id,
            country=country,
            lang=lang,
            enabled=1,
            created_at=now,
            updated_at=now,
        )
        upsert = insert_stmt.on_conflict_do_update(
            index_elements=["platform", "app_id", "keyword", "country", "lang"],
            set_={"enabled": 1, "updated_at": now},
        )
        session.execute(upsert)
        return session.execute(
            select(TrackedKeywordModel).where(
                TrackedKeywordModel.platform == "google_play",
                TrackedKeywordModel.keyword == keyword,
                TrackedKeywordModel.app_id == app_id,
                TrackedKeywordModel.country == country,
                TrackedKeywordModel.lang == lang,
            )
        ).scalar_one()

    def list_keywords(self, session) -> list[TrackedKeywordModel]:
        stmt = select(TrackedKeywordModel).order_by(desc(TrackedKeywordModel.updated_at))
        return session.execute(stmt).scalars().all()

    def remove_keyword(
        self,
        session,
        keyword: str,
        app_id: str,
        country: str,
        lang: str,
    ) -> int:
        model = session.execute(
            select(TrackedKeywordModel).where(
                TrackedKeywordModel.keyword == keyword,
                TrackedKeywordModel.app_id == app_id,
                TrackedKeywordModel.country == country,
                TrackedKeywordModel.lang == lang,
            )
        ).scalar_one_or_none()
        if model is None:
            return 0
        session.delete(model)
        return 1

    def update_keyword_sync_time(
        self,
        session,
        keyword: str,
        app_id: str,
        country: str,
        lang: str,
        value: str,
    ) -> None:
        model = session.execute(
            select(TrackedKeywordModel).where(
                TrackedKeywordModel.keyword == keyword,
                TrackedKeywordModel.app_id == app_id,
                TrackedKeywordModel.country == country,
                TrackedKeywordModel.lang == lang,
            )
        ).scalar_one_or_none()
        if model is None:
            return
        model.last_synced_at = value
        model.updated_at = value

    def set_keyword_enabled(
        self,
        session,
        keyword: str,
        app_id: str,
        country: str,
        lang: str,
        enabled: bool,
    ) -> bool:
        model = session.execute(
            select(TrackedKeywordModel).where(
                TrackedKeywordModel.keyword == keyword,
                TrackedKeywordModel.app_id == app_id,
                TrackedKeywordModel.country == country,
                TrackedKeywordModel.lang == lang,
            )
        ).scalar_one_or_none()
        if model is None:
            return enabled
        model.enabled = 1 if enabled else 0
        model.updated_at = now_iso()
        return bool(model.enabled)
