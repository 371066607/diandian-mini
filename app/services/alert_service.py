from __future__ import annotations

import json
from dataclasses import dataclass

from app.constants import DEFAULT_SETTINGS
from app.db.repositories import AlertRepository
from app.utils.install_parser import parse_install_range


def _parse_histogram(value) -> list[int] | None:
    """Coerce a rating histogram (stored JSON string or list) into a 5-int list
    [1★,2★,3★,4★,5★], or None if missing/malformed/all-zero — callers skip on None."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return None
    if not isinstance(value, list) or len(value) != 5:
        return None
    try:
        counts = [int(x) for x in value]
    except (TypeError, ValueError):
        return None
    return counts if sum(counts) > 0 else None


@dataclass(frozen=True)
class NewAlert:
    """A session-independent record of an alert created this sync, so callers (the
    notification pipeline) can act on fresh alerts without touching detached ORM rows."""

    type: str
    severity: str
    title: str
    message: str
    app_id: str | None

# Real-install milestones (突破即告警). Crossing any of these upward emits one
# installs_milestone alert for the highest milestone crossed in a single sync.
INSTALL_MILESTONES = [
    1_000_000,
    5_000_000,
    10_000_000,
    50_000_000,
    100_000_000,
    500_000_000,
    1_000_000_000,
]


def _format_percent(delta: float) -> str:
    return f"{delta * 100:.1f}%"


def _ads_flag(contains_ads, ad_supported):
    """Resolve a tri-state ads flag to a bool, preferring ``contains_ads`` and
    falling back to ``ad_supported``. Returns None when neither is set."""
    for value in (contains_ads, ad_supported):
        if value is not None:
            return bool(value)
    return None


class AlertService:
    def __init__(self, database, settings_service=None):
        self.database = database
        self.settings_service = settings_service
        self.repository = AlertRepository()

    def _threshold(self, key: str) -> float:
        """Read a numeric alert threshold from settings, falling back to the default.
        Never raises — a malformed stored value degrades to the shipped default."""
        raw = DEFAULT_SETTINGS.get(key)
        if self.settings_service is not None:
            raw = self.settings_service.get(key, raw)
        try:
            return float(raw)
        except (TypeError, ValueError):
            return float(DEFAULT_SETTINGS[key])

    def unread_count(self) -> int:
        with self.database.session() as session:
            return self.repository.unread_count(session)

    def mark_all_read(self) -> int:
        with self.database.session() as session:
            return self.repository.mark_all_read(session)

    def recent_alerts(self, limit: int = 10, severity: str | None = None):
        with self.database.session() as session:
            return self.repository.list_recent(session, limit=limit, severity=severity)

    def list_alerts(
        self,
        app_id: str | None = None,
        alert_type: str | None = None,
        severity: str | None = None,
        is_read: int | None = None,
        limit: int = 200,
    ):
        with self.database.session() as session:
            return self.repository.list_filtered(
                session,
                app_id=app_id,
                alert_type=alert_type,
                severity=severity,
                is_read=is_read,
                limit=limit,
            )

    def distinct_alert_apps(self) -> list[str]:
        with self.database.session() as session:
            return self.repository.distinct_app_ids(session)

    def mark_read(self, ids: list[int]) -> int:
        with self.database.session() as session:
            return self.repository.mark_read_by_ids(session, ids)

    def create_snapshot_alerts(self, session, previous_snapshot, detail) -> list[NewAlert]:
        if previous_snapshot is None:
            return []

        created: list[NewAlert] = []
        title = detail.title or previous_snapshot.title or detail.app_id
        rating_drop_threshold = self._threshold("alert_rating_drop")
        growth_threshold = self._threshold("alert_growth_percent") / 100.0

        def emit(alert_type: str, severity: str, message: str, **payload) -> None:
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
            created.append(NewAlert(alert_type, severity, title, message, detail.app_id))

        previous_rating = previous_snapshot.rating or 0
        current_rating = detail.rating or 0
        rating_drop = previous_rating - current_rating
        if previous_rating and current_rating and rating_drop >= rating_drop_threshold:
            emit(
                "rating_drop",
                "high",
                f"{title} 评分下降 {previous_rating:.1f} -> {current_rating:.1f}",
                previous=previous_rating,
                current=current_rating,
            )

        # Rating-histogram diffs: an earlier口碑 signal than the (lagging) mean rating.
        prev_hist = _parse_histogram(getattr(previous_snapshot, "histogram_json", None))
        curr_hist = _parse_histogram(detail.histogram)
        if prev_hist is not None and curr_hist is not None:
            prev_total, curr_total = sum(prev_hist), sum(curr_hist)
            # Surge of negative (1-2★) reviews among the ratings added since last snapshot.
            new_ratings = curr_total - prev_total
            if new_ratings > 0:
                new_negative = (curr_hist[0] + curr_hist[1]) - (prev_hist[0] + prev_hist[1])
                negative_share = new_negative / new_ratings
                surge_threshold = self._threshold("alert_negative_review_surge_percent") / 100.0
                if negative_share >= surge_threshold:
                    emit(
                        "negative_review_surge",
                        "high",
                        f"{title} 差评激增：近期新增评分中 {_format_percent(negative_share)} 为 1-2 星",
                        previous=prev_hist[0] + prev_hist[1],
                        current=curr_hist[0] + curr_hist[1],
                    )
            # Absolute drop in the positive (4-5★) share of all ratings.
            prev_positive = (prev_hist[3] + prev_hist[4]) / prev_total
            curr_positive = (curr_hist[3] + curr_hist[4]) / curr_total
            positive_drop = prev_positive - curr_positive
            drop_threshold = self._threshold("alert_positive_ratio_drop") / 100.0
            if positive_drop >= drop_threshold:
                emit(
                    "positive_ratio_drop",
                    "high",
                    f"{title} 好评率下降 {_format_percent(prev_positive)} -> {_format_percent(curr_positive)}",
                    previous=round(prev_positive, 4),
                    current=round(curr_positive, 4),
                )

        previous_ratings_count = previous_snapshot.ratings_count or 0
        current_ratings_count = detail.ratings_count or 0
        if previous_ratings_count > 0 and current_ratings_count > previous_ratings_count:
            growth = (current_ratings_count - previous_ratings_count) / previous_ratings_count
            if growth >= growth_threshold:
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
            if growth >= growth_threshold:
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

        # 真实安装量里程碑：跨越某个里程碑时，对最高被跨越的里程碑发一条。
        previous_real_installs = previous_snapshot.real_installs
        current_real_installs = detail.real_installs
        if previous_real_installs is not None and current_real_installs is not None:
            crossed = [
                milestone
                for milestone in INSTALL_MILESTONES
                if previous_real_installs < milestone <= current_real_installs
            ]
            if crossed:
                highest = max(crossed)
                emit(
                    "installs_milestone",
                    "medium",
                    f"{title} 真实安装量突破 {highest:,}",
                    previous=previous_real_installs,
                    current=current_real_installs,
                )

        # 含广告变化：contains_ads 优先，回退 ad_supported。
        previous_ads = _ads_flag(previous_snapshot.contains_ads, previous_snapshot.ad_supported)
        current_ads = _ads_flag(detail.contains_ads, detail.ad_supported)
        if previous_ads is not None and current_ads is not None and previous_ads != current_ads:
            change = "无→有" if current_ads else "有→无"
            emit(
                "ads_changed",
                "high",
                f"{title} 广告状态变化：{change}",
                previous=previous_ads,
                current=current_ads,
            )

        # 促销/价格变化：促销优先，同次最多一条 price_changed。
        previous_sale = previous_snapshot.sale
        current_sale = detail.sale
        previous_price = (previous_snapshot.price or "").strip()
        current_price = (detail.price or "").strip()
        if previous_sale is not None and current_sale is not None and not previous_sale and current_sale:
            emit(
                "price_changed",
                "medium",
                f"{title} 开始促销",
                previous=bool(previous_sale),
                current=bool(current_sale),
            )
        elif previous_price and current_price and previous_price != current_price:
            emit(
                "price_changed",
                "medium",
                f"{title} 价格变化 {previous_price} -> {current_price}",
                previous=previous_price,
                current=current_price,
            )

        # 开发者联系方式变化：邮箱/官网，合并为一条。
        previous_email = (previous_snapshot.developer_email or "").strip()
        current_email = (detail.developer_email or "").strip()
        previous_website = (previous_snapshot.developer_website or "").strip()
        current_website = (detail.developer_website or "").strip()
        contact_changes = []
        if previous_email and current_email and previous_email != current_email:
            contact_changes.append(f"邮箱 {previous_email} -> {current_email}")
        if previous_website and current_website and previous_website != current_website:
            contact_changes.append(f"官网 {previous_website} -> {current_website}")
        if contact_changes:
            emit(
                "developer_contact_changed",
                "low",
                f"{title} 开发者联系方式变化：" + "；".join(contact_changes),
                previous={"email": previous_email, "website": previous_website},
                current={"email": current_email, "website": current_website},
            )

        return created

    def create_keyword_alerts(self, session, previous, result) -> list[NewAlert]:
        """Diff the previous keyword-rank snapshot against the freshly-fetched ``result``
        and emit alerts for meaningful movement. ``previous`` is a ``KeywordRankModel``
        (or None on the first sync); ``result`` is a ``KeywordRankResult`` schema.

        One alert at most per sync, by priority: enter/leave the tracked range >
        cross the top-N band > a significant move inside the band. The first sync only
        establishes a baseline (no alert). Returns the created alerts (0 or 1)."""
        if previous is None:
            return []

        keyword = result.keyword
        app_id = result.app_id
        title = f"关键词 {keyword}"
        top_band = int(self._threshold("alert_keyword_top_band"))
        move_threshold = int(self._threshold("alert_keyword_move"))

        prev_found = bool(previous.found) and previous.rank is not None
        curr_found = bool(result.found) and result.rank is not None
        prev_rank = previous.rank
        curr_rank = result.rank

        def emit(
            alert_type: str, severity: str, message: str, previous=None, current=None
        ) -> list[NewAlert]:
            self.repository.create(
                session,
                alert_type,
                severity,
                message,
                app_id=app_id,
                title=title,
                keyword=keyword,
                previous=previous,
                current=current,
            )
            return [NewAlert(alert_type, severity, title, message, app_id)]

        # Entered the tracked range (was beyond checked_limit / not found, now ranked).
        if not prev_found and curr_found:
            severity = "high" if curr_rank <= top_band else "medium"
            return emit(
                "keyword_entered",
                severity,
                f"{title} 进入榜单，排名 #{curr_rank}",
                current=curr_rank,
            )

        # Dropped out of the tracked range entirely.
        if prev_found and not curr_found:
            return emit(
                "keyword_dropped",
                "high",
                f"{title} 跌出监控范围（上次 #{prev_rank}）",
                previous=prev_rank,
            )

        # Still unranked both times — nothing to report.
        if not prev_found and not curr_found:
            return []

        # Both ranked: measure movement (positive delta = rose toward #1).
        delta = prev_rank - curr_rank

        crossed_into_top = prev_rank > top_band and curr_rank <= top_band
        crossed_out_of_top = prev_rank <= top_band and curr_rank > top_band
        if crossed_into_top:
            return emit(
                "keyword_top_entered",
                "high",
                f"{title} 升入前 {top_band}：#{prev_rank} -> #{curr_rank}",
                previous=prev_rank,
                current=curr_rank,
            )
        if crossed_out_of_top:
            return emit(
                "keyword_top_dropped",
                "high",
                f"{title} 跌出前 {top_band}：#{prev_rank} -> #{curr_rank}",
                previous=prev_rank,
                current=curr_rank,
            )

        if abs(delta) >= move_threshold:
            if delta > 0:
                return emit(
                    "keyword_rank_up",
                    "medium",
                    f"{title} 排名上升 {delta} 位：#{prev_rank} -> #{curr_rank}",
                    previous=prev_rank,
                    current=curr_rank,
                )
            return emit(
                "keyword_rank_down",
                "medium",
                f"{title} 排名下降 {abs(delta)} 位：#{prev_rank} -> #{curr_rank}",
                previous=prev_rank,
                current=curr_rank,
            )

        return []

    def create_chart_alerts(self, session, previous, result) -> list[NewAlert]:
        """Diff the previous chart-rank snapshot against the freshly-fetched ``result`` and
        emit alerts for meaningful movement within a chart. ``previous`` is a
        ``ChartRankSnapshotModel`` (or None on the first sync); ``result`` is a
        ``ChartRankResult`` schema. Reuses the keyword top-band / move thresholds.

        One alert at most per sync, by priority: enter/leave the chart > cross the top-N
        band > a significant move inside the chart. The first sync only establishes a
        baseline (no alert). Returns the created alerts (0 or 1)."""
        if previous is None:
            return []

        app_id = result.app_id
        title = f"榜单 {result.collection}/{result.category or '-'}"
        top_band = int(self._threshold("alert_keyword_top_band"))
        move_threshold = int(self._threshold("alert_keyword_move"))

        prev_found = bool(previous.found) and previous.rank is not None
        curr_found = bool(result.found) and result.rank is not None
        prev_rank = previous.rank
        curr_rank = result.rank

        def emit(
            alert_type: str, severity: str, message: str, previous=None, current=None
        ) -> list[NewAlert]:
            self.repository.create(
                session,
                alert_type,
                severity,
                message,
                app_id=app_id,
                title=title,
                collection=result.collection,
                category=result.category,
                previous=previous,
                current=current,
            )
            return [NewAlert(alert_type, severity, title, message, app_id)]

        # Entered the chart (was beyond checked_limit / not found, now ranked).
        if not prev_found and curr_found:
            severity = "high" if curr_rank <= top_band else "medium"
            return emit(
                "chart_entered",
                severity,
                f"{title} 进入榜单，排名 #{curr_rank}",
                current=curr_rank,
            )

        # Dropped off the chart entirely.
        if prev_found and not curr_found:
            return emit(
                "chart_dropped",
                "high",
                f"{title} 跌出榜单（上次 #{prev_rank}）",
                previous=prev_rank,
            )

        # Still unranked both times — nothing to report.
        if not prev_found and not curr_found:
            return []

        # Both ranked: measure movement (positive delta = rose toward #1).
        delta = prev_rank - curr_rank

        crossed_into_top = prev_rank > top_band and curr_rank <= top_band
        crossed_out_of_top = prev_rank <= top_band and curr_rank > top_band
        if crossed_into_top:
            return emit(
                "chart_top_entered",
                "high",
                f"{title} 升入前 {top_band}：#{prev_rank} -> #{curr_rank}",
                previous=prev_rank,
                current=curr_rank,
            )
        if crossed_out_of_top:
            return emit(
                "chart_top_dropped",
                "high",
                f"{title} 跌出前 {top_band}：#{prev_rank} -> #{curr_rank}",
                previous=prev_rank,
                current=curr_rank,
            )

        if abs(delta) >= move_threshold:
            if delta > 0:
                return emit(
                    "chart_rank_up",
                    "medium",
                    f"{title} 排名上升 {delta} 位：#{prev_rank} -> #{curr_rank}",
                    previous=prev_rank,
                    current=curr_rank,
                )
            return emit(
                "chart_rank_down",
                "medium",
                f"{title} 排名下降 {abs(delta)} 位：#{prev_rank} -> #{curr_rank}",
                previous=prev_rank,
                current=curr_rank,
            )

        return []

    def record_fetch_failure(
        self,
        app_id: str,
        message: str,
        *,
        title: str | None = None,
        country: str | None = None,
        lang: str | None = None,
        failure_count: int = 1,
    ) -> NewAlert:
        """Record a sync failure, escalating by consecutive-failure count so a transient
        blip stays a quiet (medium) record while a *persistent* failure pushes once.

        - count < escalate_after → ``fetch_failed`` (medium): logged, not pushed.
        - count == escalate_after → ``fetch_failed_persistent`` (high): the one loud push.
        - count >  escalate_after → ``fetch_failed_persistent`` (medium): stays quiet so a
          dead monitor doesn't re-notify every sync."""
        escalate_after = int(self._threshold("alert_fetch_escalate_after"))
        name = title or app_id
        if failure_count < escalate_after:
            alert_type, severity = "fetch_failed", "medium"
            full_message = f"{name} 获取失败：{message}"
        else:
            alert_type = "fetch_failed_persistent"
            severity = "high" if failure_count == escalate_after else "medium"
            full_message = f"{name} 已连续 {failure_count} 次抓取失败：{message}"
        with self.database.session() as session:
            self.repository.create(
                session,
                alert_type,
                severity,
                full_message,
                app_id=app_id,
                title=title,
                country=country,
                lang=lang,
                error=message,
                failure_count=failure_count,
            )
        return NewAlert(alert_type, severity, name, full_message, app_id)

    def record_fetch_recovered(
        self,
        app_id: str,
        *,
        title: str | None = None,
        previous_failures: int = 0,
        country: str | None = None,
        lang: str | None = None,
    ) -> NewAlert:
        """Emit a recovery alert after a monitor that had escalated starts succeeding."""
        name = title or app_id
        message = f"{name} 抓取已恢复（此前连续失败 {previous_failures} 次）"
        with self.database.session() as session:
            self.repository.create(
                session,
                "fetch_recovered",
                "medium",
                message,
                app_id=app_id,
                title=title,
                country=country,
                lang=lang,
                previous=previous_failures,
            )
        return NewAlert("fetch_recovered", "medium", name, message, app_id)

    def create_review_alerts(
        self, app_id: str, title: str | None, new_negative_reviews
    ) -> list[NewAlert]:
        """Emit one alert when this sync brought in ``>= alert_review_min`` new low-star
        reviews — surfacing the actual complaint text, not just an aggregate dip."""
        min_count = int(self._threshold("review_alert_min_count"))
        count = len(new_negative_reviews)
        if count < min_count:
            return []
        name = title or app_id
        sample = (new_negative_reviews[0].content or "").strip().replace("\n", " ")
        if len(sample) > 40:
            sample = sample[:40] + "…"
        message = f"{name} 新增 {count} 条差评" + (f"，例：「{sample}」" if sample else "")
        with self.database.session() as session:
            self.repository.create(
                session,
                "review_negative_spike",
                "high",
                message,
                app_id=app_id,
                title=title,
                current=count,
            )
        return [NewAlert("review_negative_spike", "high", name, message, app_id)]
