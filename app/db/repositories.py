from __future__ import annotations

from sqlalchemy import and_, bindparam, desc, func, select, text, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.models import (
    AlertModel,
    AppSnapshotModel,
    ChartRankSnapshotModel,
    KeywordCorpusModel,
    KeywordRankModel,
    ReviewModel,
    SettingModel,
    TrackedAppModel,
    TrackedChartAppModel,
    TrackedKeywordModel,
)
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
    def unread_count(self, session, app_id: str | None = None) -> int:
        stmt = select(func.count()).select_from(AlertModel).where(AlertModel.is_read == 0)
        if app_id is not None:
            stmt = stmt.where(AlertModel.app_id == app_id)
        return session.scalar(stmt) or 0

    def unread_count_bulk(self, session, app_ids: list[str]) -> dict[str, int]:
        """Return {app_id: unread_count} for every app in *app_ids* — one query instead
        of one per app.  Missing keys mean zero unread alerts."""
        if not app_ids:
            return {}
        rows = session.execute(
            select(AlertModel.app_id, func.count().label("cnt"))
            .where(AlertModel.app_id.in_(app_ids), AlertModel.is_read == 0)
            .group_by(AlertModel.app_id)
        ).all()
        return {row.app_id: row.cnt for row in rows}

    def latest_by_app(self, session, app_ids: list[str]) -> dict[str, AlertModel]:
        """Return the single most-recent alert for each app_id — one query."""
        if not app_ids:
            return {}
        # Subquery: max created_at per app_id
        sub = (
            select(
                AlertModel.app_id.label("aid"),
                func.max(AlertModel.created_at).label("max_at"),
            )
            .where(AlertModel.app_id.in_(app_ids))
            .group_by(AlertModel.app_id)
            .alias("_latest_dates")
        )
        stmt = select(AlertModel).join(
            sub,
            and_(
                AlertModel.app_id == sub.c.aid,
                AlertModel.created_at == sub.c.max_at,
            ),
        )
        rows = session.execute(stmt).scalars().all()
        result: dict[str, AlertModel] = {}
        for row in rows:
            # keep highest id when two alerts share the same timestamp
            if row.app_id not in result or row.id > result[row.app_id].id:
                result[row.app_id] = row
        return result

    def list_recent(
        self, session, limit: int = 10, severity: str | None = None
    ) -> list[AlertModel]:
        stmt = select(AlertModel)
        if severity:
            stmt = stmt.where(AlertModel.severity == severity)
        stmt = stmt.order_by(desc(AlertModel.created_at)).limit(limit)
        return session.execute(stmt).scalars().all()

    def mark_all_read(self, session) -> int:
        result = session.execute(
            update(AlertModel).where(AlertModel.is_read == 0).values(is_read=1)
        )
        return max(result.rowcount, 0)

    def list_filtered(
        self,
        session,
        app_id: str | None = None,
        alert_type: str | None = None,
        severity: str | None = None,
        is_read: int | None = None,
        limit: int = 200,
    ) -> list[AlertModel]:
        stmt = select(AlertModel)
        if app_id is not None:
            stmt = stmt.where(AlertModel.app_id == app_id)
        if alert_type is not None:
            stmt = stmt.where(AlertModel.type == alert_type)
        if severity is not None:
            stmt = stmt.where(AlertModel.severity == severity)
        # ``is not None`` is load-bearing: is_read=0 is a valid filter ("未读") and must
        # not be confused with "no filter".
        if is_read is not None:
            stmt = stmt.where(AlertModel.is_read == is_read)
        stmt = stmt.order_by(desc(AlertModel.created_at)).limit(limit)
        return session.execute(stmt).scalars().all()

    def distinct_app_ids(self, session) -> list[str]:
        stmt = (
            select(AlertModel.app_id)
            .where(AlertModel.app_id.is_not(None))
            .distinct()
            .order_by(AlertModel.app_id)
        )
        return [row for row in session.execute(stmt).scalars().all() if row]

    def mark_read_by_ids(self, session, ids: list[int]) -> int:
        if not ids:
            return 0
        result = session.execute(update(AlertModel).where(AlertModel.id.in_(ids)).values(is_read=1))
        return max(result.rowcount, 0)


class SnapshotRepository:
    def count(self, session) -> int:
        return session.scalar(select(func.count()).select_from(AppSnapshotModel)) or 0

    def list_recent(self, session, limit: int = 8) -> list[AppSnapshotModel]:
        stmt = select(AppSnapshotModel).order_by(desc(AppSnapshotModel.captured_at)).limit(limit)
        return session.execute(stmt).scalars().all()

    def previous_distinct_day(
        self, session, app_id: str, country: str, lang: str, before_day: str | None = None
    ) -> AppSnapshotModel | None:
        """The most recent snapshot from a calendar day BEFORE ``before_day`` (default
        today). Used as the alert-diff baseline so a same-day re-sync never self-compares."""
        day = before_day or now_iso()[:10]
        stmt = (
            select(AppSnapshotModel)
            .where(
                AppSnapshotModel.app_id == app_id,
                AppSnapshotModel.country == country,
                AppSnapshotModel.lang == lang,
                func.substr(AppSnapshotModel.captured_at, 1, 10) < day,
            )
            .order_by(desc(AppSnapshotModel.captured_at))
            .limit(1)
        )
        return session.execute(stmt).scalar_one_or_none()

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

    def latest_two_bulk(
        self,
        session,
        app_keys: list[tuple[str, str, str]],
    ) -> dict[tuple[str, str, str], list[AppSnapshotModel]]:
        """Return up to 2 most-recent snapshots per (app_id, country, lang) — one query.

        The index ix_app_snapshots_lookup covers (app_id, country, lang, captured_at),
        so the single IN + ORDER BY is index-only and scales to hundreds of apps.
        Rows arrive oldest-first; we keep a rolling window of 2 per key in Python.
        """
        if not app_keys:
            return {}
        keys_set = set(app_keys)
        app_ids = list({a for a, _c, _l in app_keys})
        stmt = (
            select(AppSnapshotModel)
            .where(AppSnapshotModel.app_id.in_(app_ids))
            .order_by(
                AppSnapshotModel.app_id,
                AppSnapshotModel.country,
                AppSnapshotModel.lang,
                AppSnapshotModel.captured_at.asc(),
            )
        )
        result: dict[tuple, list] = {}
        for row in session.execute(stmt).scalars():
            key = (row.app_id, row.country, row.lang)
            if key not in keys_set:
                continue
            buf = result.setdefault(key, [])
            buf.append(row)
            if len(buf) > 2:
                buf.pop(0)
        return result

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
    def list_by_app(self, session, app_id: str, limit: int = 100) -> list[ReviewModel]:
        stmt = (
            select(ReviewModel)
            .where(ReviewModel.app_id == app_id)
            .order_by(desc(ReviewModel.review_created_at))
            .limit(limit)
        )
        return session.execute(stmt).scalars().all()

    def existing_review_ids(self, session, app_id: str, review_ids: list[str]) -> set[str]:
        """Which of ``review_ids`` are already stored for ``app_id`` — used to tell which
        reviews are NEW this sync (for negative-review alerting)."""
        ids = [r for r in review_ids if r]
        if not ids:
            return set()
        stmt = select(ReviewModel.review_id).where(
            ReviewModel.app_id == app_id, ReviewModel.review_id.in_(ids)
        )
        return set(session.execute(stmt).scalars().all())


class KeywordRankRepository:
    def previous_distinct_day(
        self,
        session,
        keyword: str,
        app_id: str,
        country: str,
        lang: str,
        before_day: str | None = None,
        platform: str = "google_play",
    ) -> KeywordRankModel | None:
        """Most recent rank row from a calendar day BEFORE ``before_day`` (default today),
        used as the alert-diff baseline so a same-day re-sync never self-compares."""
        day = before_day or now_iso()[:10]
        stmt = (
            select(KeywordRankModel)
            .where(
                KeywordRankModel.platform == platform,
                KeywordRankModel.keyword == keyword,
                KeywordRankModel.app_id == app_id,
                KeywordRankModel.country == country,
                KeywordRankModel.lang == lang,
                func.substr(KeywordRankModel.captured_at, 1, 10) < day,
            )
            .order_by(desc(KeywordRankModel.captured_at))
            .limit(1)
        )
        return session.execute(stmt).scalar_one_or_none()

    def history(
        self,
        session,
        keyword: str,
        app_id: str,
        country: str,
        lang: str,
        platform: str = "google_play",
    ) -> list[KeywordRankModel]:
        stmt = (
            select(KeywordRankModel)
            .where(
                KeywordRankModel.platform == platform,
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
        platform: str = "google_play",
    ) -> KeywordRankModel | None:
        stmt = (
            select(KeywordRankModel)
            .where(
                KeywordRankModel.platform == platform,
                KeywordRankModel.keyword == keyword,
                KeywordRankModel.app_id == app_id,
                KeywordRankModel.country == country,
                KeywordRankModel.lang == lang,
            )
            .order_by(desc(KeywordRankModel.captured_at))
            .limit(1)
        )
        return session.execute(stmt).scalars().first()

    def latest_bulk(
        self,
        session,
        keys: list[tuple[str, str, str, str, str]],  # (keyword, app_id, country, lang, platform)
    ) -> dict[tuple[str, str, str, str, str], KeywordRankModel]:
        """Return the most-recent rank row for each key — one query instead of N.

        Uses a window function (ROW_NUMBER) so we get exactly one row per partition
        without a correlated subquery.  SQLite has supported ROW_NUMBER since 3.25
        (Python 3.12 ships with ≥ 3.45).
        """
        if not keys:
            return {}
        keys_set = set(keys)
        # Collect distinct app_ids to narrow the table scan
        app_ids = list({key[1] for key in keys})
        # ``expanding=True`` lets SQLAlchemy expand the list into individual '?, ?, …'
        # placeholders that SQLite understands (raw tuple binding raises OperationalError).
        stmt = text(
            """
            SELECT id, keyword, app_id, country, lang, platform, rank, found,
                   checked_limit, captured_at
            FROM (
                SELECT *,
                    ROW_NUMBER() OVER (
                        PARTITION BY keyword, app_id, country, lang, platform
                        ORDER BY captured_at DESC
                    ) AS _rn
                FROM keyword_ranks
                WHERE app_id IN :app_ids
            ) WHERE _rn = 1
            """
        ).bindparams(bindparam("app_ids", expanding=True))
        rows = session.execute(stmt, {"app_ids": app_ids}).mappings().all()
        result: dict[tuple, KeywordRankModel] = {}
        for row in rows:
            key = (
                row["keyword"],
                row["app_id"],
                row["country"],
                row["lang"],
                row["platform"] or "google_play",
            )
            if key not in keys_set:
                continue
            # Re-hydrate as ORM objects so callers can use .rank / .found normally
            obj = KeywordRankModel(
                id=row["id"],
                platform=row["platform"] or "google_play",
                keyword=row["keyword"],
                app_id=row["app_id"],
                country=row["country"],
                lang=row["lang"],
                rank=row["rank"],
                found=row["found"],
                checked_limit=row["checked_limit"],
                captured_at=row["captured_at"],
            )
            result[key] = obj
        return result

    def list_recent(self, session, limit: int = 8) -> list[KeywordRankModel]:
        stmt = select(KeywordRankModel).order_by(desc(KeywordRankModel.captured_at)).limit(limit)
        return session.execute(stmt).scalars().all()


class ChartRankRepository:
    def previous_distinct_day(
        self,
        session,
        app_id: str,
        collection: str,
        category: str | None,
        country: str,
        lang: str,
        before_day: str | None = None,
    ) -> ChartRankSnapshotModel | None:
        """Most recent rank row from a calendar day BEFORE ``before_day`` (default today),
        used as the alert-diff baseline so a same-day re-sync never self-compares."""
        day = before_day or now_iso()[:10]
        stmt = (
            select(ChartRankSnapshotModel)
            .where(
                ChartRankSnapshotModel.app_id == app_id,
                ChartRankSnapshotModel.collection == collection,
                ChartRankSnapshotModel.category == category,
                ChartRankSnapshotModel.country == country,
                ChartRankSnapshotModel.lang == lang,
                func.substr(ChartRankSnapshotModel.captured_at, 1, 10) < day,
            )
            .order_by(desc(ChartRankSnapshotModel.captured_at))
            .limit(1)
        )
        return session.execute(stmt).scalar_one_or_none()

    def history(
        self,
        session,
        app_id: str,
        collection: str,
        category: str | None,
        country: str,
        lang: str,
    ) -> list[ChartRankSnapshotModel]:
        stmt = (
            select(ChartRankSnapshotModel)
            .where(
                ChartRankSnapshotModel.app_id == app_id,
                ChartRankSnapshotModel.collection == collection,
                ChartRankSnapshotModel.category == category,
                ChartRankSnapshotModel.country == country,
                ChartRankSnapshotModel.lang == lang,
            )
            .order_by(ChartRankSnapshotModel.captured_at.asc())
        )
        return session.execute(stmt).scalars().all()

    def latest(
        self,
        session,
        app_id: str,
        collection: str,
        category: str | None,
        country: str,
        lang: str,
    ) -> ChartRankSnapshotModel | None:
        stmt = (
            select(ChartRankSnapshotModel)
            .where(
                ChartRankSnapshotModel.app_id == app_id,
                ChartRankSnapshotModel.collection == collection,
                ChartRankSnapshotModel.category == category,
                ChartRankSnapshotModel.country == country,
                ChartRankSnapshotModel.lang == lang,
            )
            .order_by(desc(ChartRankSnapshotModel.captured_at))
            .limit(1)
        )
        return session.execute(stmt).scalars().first()


class TrackingRepository:
    def add_app(
        self,
        session,
        app_id: str,
        title: str | None,
        country: str,
        lang: str,
        frequency: str | None = None,
    ) -> TrackedAppModel:
        now = now_iso()
        insert_stmt = sqlite_insert(TrackedAppModel).values(
            platform="google_play",
            app_id=app_id,
            title=title,
            country=country,
            lang=lang,
            frequency=frequency or "daily",
            enabled=1,
            created_at=now,
            updated_at=now,
        )
        # Atomic upsert: a plain check-then-insert races when the daily scheduler
        # sync and a manual "add/sync" touch the same app concurrently, raising a
        # UNIQUE IntegrityError at commit. ON CONFLICT DO UPDATE makes it safe and
        # keeps the existing title/created_at while re-enabling the row. ``frequency`` is
        # only set on a re-add when explicitly given, else the existing cadence is kept.
        frequency_set = insert_stmt.excluded.frequency if frequency else TrackedAppModel.frequency
        upsert = insert_stmt.on_conflict_do_update(
            index_elements=["platform", "app_id", "country", "lang"],
            set_={
                "enabled": 1,
                "title": func.coalesce(insert_stmt.excluded.title, TrackedAppModel.title),
                "frequency": frequency_set,
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

    def set_app_frequency(
        self,
        session,
        app_id: str,
        country: str,
        lang: str,
        frequency: str,
    ) -> str:
        model = session.execute(
            select(TrackedAppModel).where(
                TrackedAppModel.app_id == app_id,
                TrackedAppModel.country == country,
                TrackedAppModel.lang == lang,
            )
        ).scalar_one_or_none()
        if model is None:
            return frequency
        model.frequency = frequency
        model.updated_at = now_iso()
        return model.frequency

    def set_app_tag(
        self,
        session,
        app_id: str,
        country: str,
        lang: str,
        tag: str | None,
    ) -> str | None:
        model = session.execute(
            select(TrackedAppModel).where(
                TrackedAppModel.app_id == app_id,
                TrackedAppModel.country == country,
                TrackedAppModel.lang == lang,
            )
        ).scalar_one_or_none()
        if model is None:
            return None
        # Normalize empty/whitespace-only input to NULL so "clear tag" is a real reset.
        normalized = (tag or "").strip() or None
        model.tag = normalized
        model.updated_at = now_iso()
        return model.tag

    def add_keyword(
        self,
        session,
        keyword: str,
        app_id: str,
        country: str,
        lang: str,
        platform: str = "google_play",
    ) -> TrackedKeywordModel:
        now = now_iso()
        insert_stmt = sqlite_insert(TrackedKeywordModel).values(
            platform=platform,
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
                TrackedKeywordModel.platform == platform,
                TrackedKeywordModel.keyword == keyword,
                TrackedKeywordModel.app_id == app_id,
                TrackedKeywordModel.country == country,
                TrackedKeywordModel.lang == lang,
            )
        ).scalar_one()

    def list_keywords(self, session) -> list[TrackedKeywordModel]:
        stmt = select(TrackedKeywordModel).order_by(desc(TrackedKeywordModel.updated_at))
        return session.execute(stmt).scalars().all()

    def _keyword_row(self, session, keyword, app_id, country, lang, platform):
        """The single monitor row for the full 5-tuple identity. Filtering on platform is
        load-bearing: the unique key includes it, so the same (keyword, app_id, country,
        lang) may legitimately exist once per store."""
        return session.execute(
            select(TrackedKeywordModel).where(
                TrackedKeywordModel.platform == platform,
                TrackedKeywordModel.keyword == keyword,
                TrackedKeywordModel.app_id == app_id,
                TrackedKeywordModel.country == country,
                TrackedKeywordModel.lang == lang,
            )
        ).scalar_one_or_none()

    def remove_keyword(
        self,
        session,
        keyword: str,
        app_id: str,
        country: str,
        lang: str,
        platform: str = "google_play",
    ) -> int:
        model = self._keyword_row(session, keyword, app_id, country, lang, platform)
        if model is None:
            return 0
        session.delete(model)
        return 1

    def set_keyword_enabled(
        self,
        session,
        keyword: str,
        app_id: str,
        country: str,
        lang: str,
        enabled: bool,
        platform: str = "google_play",
    ) -> bool:
        model = self._keyword_row(session, keyword, app_id, country, lang, platform)
        if model is None:
            return enabled
        model.enabled = 1 if enabled else 0
        model.updated_at = now_iso()
        return bool(model.enabled)

    def set_keyword_frequency(
        self,
        session,
        keyword: str,
        app_id: str,
        country: str,
        lang: str,
        frequency: str,
        platform: str = "google_play",
    ) -> str:
        model = self._keyword_row(session, keyword, app_id, country, lang, platform)
        if model is None:
            return frequency
        model.frequency = frequency
        model.updated_at = now_iso()
        return model.frequency

    # --- Chart-app monitors (mirror keyword monitors) --------------------------

    def add_chart_app(
        self,
        session,
        app_id: str,
        collection: str,
        category: str | None,
        country: str,
        lang: str,
        frequency: str | None = None,
    ) -> TrackedChartAppModel:
        now = now_iso()
        insert_stmt = sqlite_insert(TrackedChartAppModel).values(
            platform="google_play",
            app_id=app_id,
            collection=collection,
            category=category,
            country=country,
            lang=lang,
            frequency=frequency or "daily",
            enabled=1,
            created_at=now,
            updated_at=now,
        )
        frequency_set = (
            insert_stmt.excluded.frequency if frequency else TrackedChartAppModel.frequency
        )
        upsert = insert_stmt.on_conflict_do_update(
            index_elements=["platform", "app_id", "collection", "category", "country", "lang"],
            set_={"enabled": 1, "frequency": frequency_set, "updated_at": now},
        )
        session.execute(upsert)
        return session.execute(
            select(TrackedChartAppModel).where(
                TrackedChartAppModel.platform == "google_play",
                TrackedChartAppModel.app_id == app_id,
                TrackedChartAppModel.collection == collection,
                TrackedChartAppModel.category == category,
                TrackedChartAppModel.country == country,
                TrackedChartAppModel.lang == lang,
            )
        ).scalar_one()

    def list_chart_apps(self, session) -> list[TrackedChartAppModel]:
        stmt = select(TrackedChartAppModel).order_by(desc(TrackedChartAppModel.updated_at))
        return session.execute(stmt).scalars().all()

    def remove_chart_app(
        self,
        session,
        app_id: str,
        collection: str,
        category: str | None,
        country: str,
        lang: str,
    ) -> int:
        model = session.execute(
            select(TrackedChartAppModel).where(
                TrackedChartAppModel.app_id == app_id,
                TrackedChartAppModel.collection == collection,
                TrackedChartAppModel.category == category,
                TrackedChartAppModel.country == country,
                TrackedChartAppModel.lang == lang,
            )
        ).scalar_one_or_none()
        if model is None:
            return 0
        session.delete(model)
        return 1

    def set_chart_app_enabled(
        self,
        session,
        app_id: str,
        collection: str,
        category: str | None,
        country: str,
        lang: str,
        enabled: bool,
    ) -> bool:
        model = session.execute(
            select(TrackedChartAppModel).where(
                TrackedChartAppModel.app_id == app_id,
                TrackedChartAppModel.collection == collection,
                TrackedChartAppModel.category == category,
                TrackedChartAppModel.country == country,
                TrackedChartAppModel.lang == lang,
            )
        ).scalar_one_or_none()
        if model is None:
            return enabled
        model.enabled = 1 if enabled else 0
        model.updated_at = now_iso()
        return bool(model.enabled)


class KeywordCorpusRepository:
    """Stateless access to the self-accumulating keyword pool (keyword_corpus)."""

    def fetch(
        self,
        session,
        platform: str,
        country: str,
        lang: str,
        limit: int = 5000,
    ) -> list[KeywordCorpusModel]:
        """Most-relevant-first slice of the locale's pool: confirmed keywords first,
        then by how often they've recurred. Capped so an ever-growing pool can't make
        a scan's reflux step unbounded."""
        stmt = (
            select(KeywordCorpusModel)
            .where(
                KeywordCorpusModel.platform == platform,
                KeywordCorpusModel.country == country,
                KeywordCorpusModel.lang == lang,
            )
            .order_by(
                desc(KeywordCorpusModel.confirmed),
                desc(KeywordCorpusModel.hit_count),
                desc(KeywordCorpusModel.last_seen_at),
            )
            .limit(limit)
        )
        return list(session.execute(stmt).scalars())

    def count(self, session, platform: str, country: str, lang: str) -> int:
        return int(
            session.execute(
                select(func.count())
                .select_from(KeywordCorpusModel)
                .where(
                    KeywordCorpusModel.platform == platform,
                    KeywordCorpusModel.country == country,
                    KeywordCorpusModel.lang == lang,
                )
            ).scalar()
            or 0
        )
