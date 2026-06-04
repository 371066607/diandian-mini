from __future__ import annotations

from app.db.repositories import AlertRepository
from app.utils.install_parser import parse_install_range


def _format_percent(delta: float) -> str:
    return f"{delta * 100:.1f}%"


class AlertService:
    def __init__(self, database):
        self.database = database
        self.repository = AlertRepository()

    def unread_count(self) -> int:
        with self.database.session() as session:
            return self.repository.unread_count(session)

    def mark_all_read(self) -> int:
        with self.database.session() as session:
            return self.repository.mark_all_read(session)

    def recent_alerts(self, limit: int = 10):
        with self.database.session() as session:
            return self.repository.list_recent(session, limit=limit)

    def create_snapshot_alerts(self, session, previous_snapshot, detail) -> int:
        if previous_snapshot is None:
            return 0

        created = 0
        title = detail.title or previous_snapshot.title or detail.app_id

        def emit(alert_type: str, severity: str, message: str, **payload) -> None:
            nonlocal created
            self.repository.create(
                session,
                alert_type,
                severity,
                message,
                app_id=detail.app_id,
                title=title,
                previous=payload.pop("previous", None),
                current=payload.pop("current", None),
                **payload,
            )
            created += 1

        previous_rating = previous_snapshot.rating or 0
        current_rating = detail.rating or 0
        rating_drop = previous_rating - current_rating
        if previous_rating and current_rating and rating_drop >= 0.2:
            emit(
                "rating_drop",
                "high",
                f"{title} 评分下降 {previous_rating:.1f} -> {current_rating:.1f}",
                previous=previous_rating,
                current=current_rating,
            )

        previous_ratings_count = previous_snapshot.ratings_count or 0
        current_ratings_count = detail.ratings_count or 0
        if previous_ratings_count > 0 and current_ratings_count > previous_ratings_count:
            growth = (current_ratings_count - previous_ratings_count) / previous_ratings_count
            if growth >= 0.1:
                emit(
                    "ratings_growth",
                    "medium",
                    f"{title} 评分数增长 {_format_percent(growth)}",
                    previous=previous_ratings_count,
                    current=current_ratings_count,
                )

        previous_reviews_count = previous_snapshot.reviews_count or 0
        current_reviews_count = detail.reviews_count or 0
        if previous_reviews_count > 0 and current_reviews_count > previous_reviews_count:
            growth = (current_reviews_count - previous_reviews_count) / previous_reviews_count
            if growth >= 0.1:
                emit(
                    "reviews_growth",
                    "medium",
                    f"{title} 评论数增长 {_format_percent(growth)}",
                    previous=previous_reviews_count,
                    current=current_reviews_count,
                )

        previous_version = (previous_snapshot.version or "").strip()
        current_version = (detail.version or "").strip()
        if previous_version and current_version and previous_version != current_version:
            emit(
                "version_changed",
                "medium",
                f"{title} 版本变化 {previous_version} -> {current_version}",
                previous=previous_version,
                current=current_version,
            )

        previous_installs = previous_snapshot.installs or ""
        current_installs = detail.installs or ""
        previous_range = parse_install_range(previous_installs)
        current_range = parse_install_range(current_installs)
        if (
            previous_installs
            and current_installs
            and previous_installs != current_installs
            and previous_range != current_range
        ):
            emit(
                "install_band_changed",
                "medium",
                f"{title} 安装量档位变化 {previous_installs} -> {current_installs}",
                previous=previous_installs,
                current=current_installs,
            )

        return created

    def record_fetch_failure(
        self,
        app_id: str,
        message: str,
        *,
        title: str | None = None,
        country: str | None = None,
        lang: str | None = None,
    ) -> None:
        with self.database.session() as session:
            self.repository.create(
                session,
                "fetch_failed",
                "high",
                f"{title or app_id} 获取失败：{message}",
                app_id=app_id,
                title=title,
                country=country,
                lang=lang,
                error=message,
            )
