from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from app.constants import DEFAULT_SETTINGS, SEVERITY_RANK
from app.db.repositories import AlertRepository, SnapshotRepository, TrackingRepository
from app.utils.time_utils import is_sync_due, now_iso


@dataclass
class MonitorHealth:
    """A per-app health summary for the dashboard's monitor overview board.

    Pure DTO — assembled by ``TrackingService.monitor_overview`` and consumed by the
    UI (``MonitorCard``); holds no DB handles.
    """

    app_id: str
    country: str
    lang: str
    title: str | None
    latest_rating: float | None
    latest_installs: str | None
    rating_trend: str
    installs_trend: str
    reviews_trend: str
    last_alert: dict | None
    unread_count: int
    consecutive_failures: int
    fail_status: str
    last_synced_at: str | None


def _trend(prev, curr, *, eps: float = 0.0) -> str:
    """Compare two numeric values into a trend token.

    Returns ``"none"`` if either side is missing (only 0/1 data points), otherwise
    ``"up"`` / ``"down"`` / ``"flat"``. ``eps`` debounces noise: a difference whose
    absolute value is below ``eps`` is treated as ``"flat"``.
    """
    if prev is None or curr is None:
        return "none"
    try:
        delta = float(curr) - float(prev)
    except (TypeError, ValueError):
        return "none"
    if abs(delta) <= eps:
        return "flat"
    return "up" if delta > 0 else "down"


class TrackingService:
    def __init__(
        self,
        database,
        google_play_service,
        keyword_service=None,
        alert_service=None,
        settings_service=None,
        review_service=None,
        chart_rank_service=None,
    ):
        self.database = database
        self.google_play_service = google_play_service
        self.keyword_service = keyword_service
        self.chart_rank_service = chart_rank_service
        self.alert_service = alert_service
        self.settings_service = settings_service
        self.review_service = review_service
        self.tracking_repository = TrackingRepository()
        self.snapshot_repository = SnapshotRepository()
        self.alert_repository = AlertRepository()
        self.logger = logging.getLogger(__name__)
        # Injected by the composition root after the UI exists: notifier(list[NewAlert]).
        # Stays None for headless/smoke-test runs — the service must work without it.
        self.notifier = None

    def set_notifier(self, notifier) -> None:
        """Register a callback that receives this sync's new alerts (list[NewAlert]).

        The callback is responsible for thread-safe UI delivery; the service only calls
        it from whatever thread the sync ran on. Layering stays clean — no UI import here.
        """
        self.notifier = notifier

    def _dispatch_notifications(self, new_alerts) -> None:
        """Filter the run's new alerts by the user's notification settings and hand the
        qualifying ones to the injected notifier. Never raises into the sync path."""
        if not new_alerts or self.notifier is None:
            return
        min_severity = "high"
        if self.settings_service is not None:
            enabled = (self.settings_service.get("desktop_notifications", "true") or "true").lower()
            if enabled != "true":
                return
            min_severity = self.settings_service.get("notify_min_severity", "high") or "high"
        threshold = SEVERITY_RANK.get(min_severity.lower(), SEVERITY_RANK["high"])
        qualifying = [a for a in new_alerts if SEVERITY_RANK.get(a.severity, 0) >= threshold]
        if not qualifying:
            return
        try:
            self.notifier(qualifying)
        except Exception:
            self.logger.exception("notifier callback failed")

    def add_app(
        self,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        frequency: str | None = None,
    ) -> None:
        with self.database.session() as session:
            self.tracking_repository.add_app(session, app_id, None, country, lang, frequency)

    def add_apps_bulk(
        self,
        app_ids,
        country: str = "us",
        lang: str = "en",
        frequency: str | None = None,
    ) -> dict:
        """Bulk-create app monitors from a list of raw package-name lines.

        Cleans input (strip, drop blanks, de-dup preserving order), validates each
        package name shape, and upserts the valid ones inside a single DB session via
        the idempotent ``TrackingRepository.add_app``. Already-tracked apps are still
        re-enabled but counted as ``existing`` rather than ``added``; invalid or
        erroring lines go into ``failed`` without aborting the batch.

        Returns ``{"added": int, "existing": int, "failed": list[dict], "total": int}``
        where ``total`` is the count of cleaned, de-duplicated candidate package names.
        """
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in app_ids or []:
            app_id = (raw or "").strip()
            if not app_id or app_id in seen:
                continue
            seen.add(app_id)
            cleaned.append(app_id)

        added = 0
        existing = 0
        failed: list[dict] = []
        with self.database.session() as session:
            tracked = self.tracking_repository.list_apps(session)
            existing_keys = {
                (item.app_id, item.country, item.lang) for item in tracked
            }
            for app_id in cleaned:
                if not self._is_valid_package_name(app_id):
                    failed.append({"app_id": app_id, "reason": "包名格式不合法"})
                    continue
                try:
                    already = (app_id, country, lang) in existing_keys
                    self.tracking_repository.add_app(
                        session, app_id, None, country, lang, frequency
                    )
                    if already:
                        existing += 1
                    else:
                        added += 1
                        existing_keys.add((app_id, country, lang))
                except Exception as exc:  # noqa: BLE001 - record and continue
                    self.logger.exception("add_apps_bulk failed for %s", app_id)
                    failed.append({"app_id": app_id, "reason": str(exc)})
        return {
            "added": added,
            "existing": existing,
            "failed": failed,
            "total": len(cleaned),
        }

    @staticmethod
    def _is_valid_package_name(app_id: str) -> bool:
        """Basic Google Play package-name shape check: dot-separated, only
        ``[A-Za-z0-9._]``, at least one dot, no leading/trailing/empty segment."""
        if not app_id or " " in app_id:
            return False
        if not re.fullmatch(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+", app_id):
            return False
        return True

    def set_app_frequency(
        self, app_id: str, country: str, lang: str, frequency: str
    ) -> str:
        with self.database.session() as session:
            return self.tracking_repository.set_app_frequency(
                session, app_id, country, lang, frequency
            )

    def set_app_tag(
        self, app_id: str, country: str, lang: str, tag: str | None
    ) -> str | None:
        with self.database.session() as session:
            return self.tracking_repository.set_app_tag(
                session, app_id, country, lang, tag
            )

    def set_keyword_frequency(
        self, keyword: str, app_id: str, country: str, lang: str, frequency: str
    ) -> str:
        with self.database.session() as session:
            return self.tracking_repository.set_keyword_frequency(
                session, keyword, app_id, country, lang, frequency
            )

    def remove_app(self, app_id: str, country: str = "us", lang: str = "en") -> None:
        with self.database.session() as session:
            self.tracking_repository.remove_app(session, app_id, country, lang)

    def list_apps(self):
        with self.database.session() as session:
            return self.tracking_repository.list_apps(session)

    def monitor_overview(self) -> list[MonitorHealth]:
        """Assemble a per-app health summary for every enabled monitored app.

        Built inside a single DB session — one snapshot-history read and one alert
        read per app. Returns an empty list when nothing is monitored.
        """
        escalate_after = self._escalate_after()
        results: list[MonitorHealth] = []
        with self.database.session() as session:
            apps = self.tracking_repository.list_apps(session)
            for item in apps:
                if not item.enabled:
                    continue
                history = self.snapshot_repository.get_history(
                    session, item.app_id, item.country, item.lang
                )
                latest = history[-1] if history else None
                prev = history[-2] if len(history) >= 2 else None

                latest_rating = latest.rating if latest is not None else None
                latest_installs = latest.installs if latest is not None else None

                rating_trend = _trend(
                    prev.rating if prev is not None else None,
                    latest.rating if latest is not None else None,
                    eps=0.05,
                )
                reviews_trend = _trend(
                    prev.reviews_count if prev is not None else None,
                    latest.reviews_count if latest is not None else None,
                )
                installs_trend = self._installs_trend(prev, latest)

                last_alert_model = self.alert_repository.list_filtered(
                    session, app_id=item.app_id, limit=1
                )
                last_alert = None
                if last_alert_model:
                    a = last_alert_model[0]
                    # Raw type/severity are kept here so the service stays UI-agnostic;
                    # the card resolves the Chinese label and severity color via
                    # app.ui.alert_labels.
                    last_alert = {
                        "type": a.type,
                        "severity": a.severity,
                        "created_at": a.created_at,
                    }
                unread = self.alert_repository.unread_count(session, app_id=item.app_id)

                failures = item.consecutive_failures or 0
                if failures <= 0:
                    fail_status = "normal"
                elif failures >= escalate_after:
                    fail_status = "escalated"
                else:
                    fail_status = "failing"

                results.append(
                    MonitorHealth(
                        app_id=item.app_id,
                        country=item.country,
                        lang=item.lang,
                        title=item.title,
                        latest_rating=latest_rating,
                        latest_installs=latest_installs,
                        rating_trend=rating_trend,
                        installs_trend=installs_trend,
                        reviews_trend=reviews_trend,
                        last_alert=last_alert,
                        unread_count=unread,
                        consecutive_failures=failures,
                        fail_status=fail_status,
                        last_synced_at=item.last_synced_at,
                    )
                )
        return results

    @staticmethod
    def _installs_trend(prev, latest) -> str:
        """Installs trend: prefer numeric min_installs; fall back to the installs string."""
        if prev is None or latest is None:
            return "none"
        prev_min = getattr(prev, "min_installs", None)
        latest_min = getattr(latest, "min_installs", None)
        if prev_min is not None and latest_min is not None:
            return _trend(prev_min, latest_min)
        # No numeric band available — treat any change in the displayed string as movement
        # (direction unknown, so report flat vs. a generic change is impossible; compare
        # equality only).
        if prev.installs == latest.installs:
            return "flat"
        return "none"

    def add_keyword(self, keyword: str, app_id: str, country: str = "us", lang: str = "en") -> None:
        with self.database.session() as session:
            self.tracking_repository.add_keyword(session, keyword, app_id, country, lang)

    def add_keywords_bulk(
        self, keywords, app_id: str, country: str = "us", lang: str = "en"
    ) -> dict:
        """Bulk-create keyword monitors for one target app from raw keyword lines.

        Cleans input (strip, drop blanks, de-dup preserving order) and upserts each via
        the idempotent ``add_keyword`` inside a single session. The target ``app_id`` is
        validated once up front; an invalid package fails the whole batch. Already-tracked
        keywords are re-enabled but counted as ``existing``. Returns
        ``{"added", "existing", "failed", "total"}``.
        """
        if not self._is_valid_package_name((app_id or "").strip()):
            cleaned_all = [k.strip() for k in (keywords or []) if k and k.strip()]
            return {
                "added": 0,
                "existing": 0,
                "failed": [{"keyword": k, "reason": "目标包名格式不合法"} for k in cleaned_all],
                "total": len(cleaned_all),
            }
        app_id = app_id.strip()
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in keywords or []:
            keyword = (raw or "").strip()
            if not keyword or keyword in seen:
                continue
            seen.add(keyword)
            cleaned.append(keyword)

        added = 0
        existing = 0
        failed: list[dict] = []
        with self.database.session() as session:
            tracked = self.tracking_repository.list_keywords(session)
            existing_keys = {
                (item.keyword, item.app_id, item.country, item.lang) for item in tracked
            }
            for keyword in cleaned:
                try:
                    already = (keyword, app_id, country, lang) in existing_keys
                    self.tracking_repository.add_keyword(session, keyword, app_id, country, lang)
                    if already:
                        existing += 1
                    else:
                        added += 1
                        existing_keys.add((keyword, app_id, country, lang))
                except Exception as exc:  # noqa: BLE001 - record and continue
                    self.logger.exception("add_keywords_bulk failed for %s", keyword)
                    failed.append({"keyword": keyword, "reason": str(exc)})
        return {"added": added, "existing": existing, "failed": failed, "total": len(cleaned)}

    def list_keywords(self):
        with self.database.session() as session:
            return self.tracking_repository.list_keywords(session)

    def remove_keyword(self, keyword: str, app_id: str, country: str = "us", lang: str = "en") -> int:
        with self.database.session() as session:
            return self.tracking_repository.remove_keyword(session, keyword, app_id, country, lang)

    def toggle_app(self, app_id: str, country: str = "us", lang: str = "en") -> bool:
        with self.database.session() as session:
            apps = self.tracking_repository.list_apps(session)
            current = next(
                (
                    item
                    for item in apps
                    if item.app_id == app_id and item.country == country and item.lang == lang
                ),
                None,
            )
            next_enabled = not bool(current.enabled) if current is not None else True
            return self.tracking_repository.set_app_enabled(
                session,
                app_id,
                country,
                lang,
                next_enabled,
            )

    def toggle_keyword(
        self,
        keyword: str,
        app_id: str,
        country: str = "us",
        lang: str = "en",
    ) -> bool:
        with self.database.session() as session:
            keywords = self.tracking_repository.list_keywords(session)
            current = next(
                (
                    item
                    for item in keywords
                    if item.keyword == keyword
                    and item.app_id == app_id
                    and item.country == country
                    and item.lang == lang
                ),
                None,
            )
            next_enabled = not bool(current.enabled) if current is not None else True
            return self.tracking_repository.set_keyword_enabled(
                session,
                keyword,
                app_id,
                country,
                lang,
                next_enabled,
            )

    def _escalate_after(self) -> int:
        """Consecutive-failure count at which a monitor is treated as persistently failing."""
        raw = DEFAULT_SETTINGS["alert_fetch_escalate_after"]
        if self.settings_service is not None:
            raw = self.settings_service.get("alert_fetch_escalate_after", raw) or raw
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            return int(DEFAULT_SETTINGS["alert_fetch_escalate_after"])

    def _handle_new_alerts(self, alerts, collector) -> None:
        """Either hand the run's new alerts to an aggregating collector (so the caller
        notifies once at the end) or, for a standalone sync, dispatch them immediately."""
        if not alerts:
            return
        if collector is not None:
            collector.extend(alerts)  # list.extend is atomic under the GIL — thread-safe
        else:
            self._dispatch_notifications(alerts)

    def sync_app_now(self, app_id: str, country: str = "us", lang: str = "en", collector=None):
        try:
            detail = self.google_play_service.app_detail(app_id, country=country, lang=lang)
        except Exception as exc:
            self.logger.exception(
                "sync_app_now failed for %s (%s/%s)",
                app_id,
                country,
                lang,
            )
            if self.alert_service is not None:
                with self.database.session() as session:
                    count = self.tracking_repository.record_app_failure(
                        session, app_id, country, lang, now_iso()
                    )
                failure = self.alert_service.record_fetch_failure(
                    app_id,
                    str(exc),
                    country=country,
                    lang=lang,
                    failure_count=count,
                )
                self._handle_new_alerts([failure], collector)
            raise
        new_alerts: list = []
        prior_failures = 0
        with self.database.session() as session:
            # Diff against the last *different-day* snapshot, and keep one row per day.
            # Gating alerts on first-sync-of-day means repeated same-day syncs refresh the
            # data without re-emitting yesterday-vs-today alerts they already produced.
            previous_snapshot = self.snapshot_repository.previous_distinct_day(
                session, app_id, country, lang
            )
            self.tracking_repository.add_app(session, app_id, detail.title, country, lang)
            first_of_day = self.snapshot_repository.upsert_for_day(
                session, detail, country, lang
            )
            self.tracking_repository.update_sync_time(session, app_id, country, lang, now_iso())
            prior_failures = self.tracking_repository.record_app_success(
                session, app_id, country, lang
            )
            if self.alert_service is not None and first_of_day:
                new_alerts = self.alert_service.create_snapshot_alerts(
                    session, previous_snapshot, detail
                )
        # A monitor that had escalated and is now succeeding earns one recovery alert.
        if self.alert_service is not None and prior_failures >= self._escalate_after():
            new_alerts = list(new_alerts) + [
                self.alert_service.record_fetch_recovered(
                    app_id,
                    title=detail.title,
                    previous_failures=prior_failures,
                    country=country,
                    lang=lang,
                )
            ]
        # Reviews are an ENHANCEMENT to the snapshot sync: fetch the latest, persist them,
        # and alert on new low-star ones. Only on the day's first sync (avoids re-fetch /
        # re-alert), and any failure here is logged, NOT counted as a sync failure.
        if first_of_day:
            review_alerts = self._monitor_reviews(app_id, country, lang, detail.title)
            if review_alerts:
                new_alerts = list(new_alerts) + review_alerts
        self._handle_new_alerts(new_alerts, collector)
        return detail

    def _monitor_reviews(self, app_id, country, lang, title) -> list:
        """Fetch + persist latest reviews and build alerts for new low-star ones. Returns
        [] (never raises) when reviews are disabled, unconfigured, or the fetch errors."""
        if self.review_service is None or self.alert_service is None:
            return []
        if not self._setting_bool("review_monitor_enabled", True):
            return []
        try:
            limit = int(float(self._setting("review_monitor_limit", "50")))
            max_rating = int(float(self._setting("review_alert_max_rating", "2")))
            new_negative = self.review_service.monitor_reviews(
                app_id, country=country, lang=lang, limit=limit, max_rating=max_rating
            )
            return self.alert_service.create_review_alerts(app_id, title, new_negative)
        except Exception:
            self.logger.exception("review monitor failed for %s (non-fatal)", app_id)
            return []

    def _setting(self, key, default):
        if self.settings_service is None:
            return default
        return self.settings_service.get(key, default) or default

    def _setting_bool(self, key, default: bool) -> bool:
        raw = self._setting(key, "true" if default else "false")
        return str(raw).strip().lower() == "true"

    def sync_all_apps(self, due_only: bool = False, collector=None) -> int:
        apps = [
            item
            for item in self.list_apps()
            if item.enabled
            and (not due_only or is_sync_due(item.last_synced_at, item.frequency))
        ]
        if not apps:
            return 0

        # When no external collector is passed (standalone call) accumulate locally and
        # notify once at the end; when sync_all drives us, append into its shared sink.
        own = collector is None
        sink = [] if own else collector

        def sync_one(item) -> bool:
            try:
                self.sync_app_now(
                    item.app_id, country=item.country, lang=item.lang, collector=sink
                )
                return True
            except Exception:
                self.logger.exception(
                    "sync_all_apps failed for %s (%s/%s)", item.app_id, item.country, item.lang
                )
                return False

        # Fetch every app's detail in parallel (network-bound); the brief DB writes are
        # serialized by SQLite's busy timeout.
        with ThreadPoolExecutor(max_workers=min(6, len(apps))) as executor:
            count = sum(executor.map(sync_one, apps))
        if own:
            self._dispatch_notifications(sink)
        return count

    def sync_keyword_now(
        self,
        keyword: str,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        limit: int | None = None,
        collector=None,
    ):
        if self.keyword_service is None:
            raise RuntimeError("KeywordService 未注入。")
        effective_limit = limit or self._default_keyword_limit()
        # Before fetching, capture the prior *different-day* rank as the alert baseline and
        # whether today's row already exists. rank() upserts one row per day, so a same-day
        # re-sync must NOT re-diff (first_of_day gates it) and must NOT baseline on its own
        # earlier-today row (previous_distinct_rank skips today). Reads never derail the sync.
        previous_rank = None
        first_of_day = True
        if self.alert_service is not None:
            try:
                previous_rank = self.keyword_service.previous_distinct_rank(
                    keyword, app_id, country, lang
                )
                latest = self.keyword_service.latest_rank(keyword, app_id, country, lang)
                today = now_iso()[:10]
                first_of_day = latest is None or (latest.captured_at or "")[:10] != today
            except Exception:
                self.logger.exception(
                    "could not load previous rank for %s / %s", keyword, app_id
                )
        try:
            result = self.keyword_service.rank(
                keyword,
                app_id,
                country=country,
                lang=lang,
                limit=effective_limit,
            )
        except Exception as exc:
            self.logger.exception(
                "sync_keyword_now failed for %s / %s (%s/%s)",
                keyword,
                app_id,
                country,
                lang,
            )
            if self.alert_service is not None:
                with self.database.session() as session:
                    count = self.tracking_repository.record_keyword_failure(
                        session, keyword, app_id, country, lang, now_iso()
                    )
                failure = self.alert_service.record_fetch_failure(
                    app_id,
                    str(exc),
                    title=f"关键词 {keyword}",
                    country=country,
                    lang=lang,
                    failure_count=count,
                )
                self._handle_new_alerts([failure], collector)
            raise
        new_alerts: list = []
        prior_failures = 0
        with self.database.session() as session:
            self.tracking_repository.add_keyword(session, keyword, app_id, country, lang)
            self.tracking_repository.update_keyword_sync_time(
                session,
                keyword,
                app_id,
                country,
                lang,
                now_iso(),
            )
            # A returned result (even "未命中"/found=False) is a successful fetch.
            prior_failures = self.tracking_repository.record_keyword_success(
                session, keyword, app_id, country, lang
            )
            # Only diff on the first sync of the day — a same-day re-sync already compared
            # against the prior day, so re-diffing would re-emit the same rank-change alert.
            if self.alert_service is not None and first_of_day:
                new_alerts = self.alert_service.create_keyword_alerts(
                    session, previous_rank, result
                )
        if self.alert_service is not None and prior_failures >= self._escalate_after():
            new_alerts = list(new_alerts) + [
                self.alert_service.record_fetch_recovered(
                    app_id,
                    title=f"关键词 {keyword}",
                    previous_failures=prior_failures,
                    country=country,
                    lang=lang,
                )
            ]
        self._handle_new_alerts(new_alerts, collector)
        return result

    def sync_all_keywords(self, due_only: bool = False, collector=None) -> int:
        keywords = [
            item
            for item in self.list_keywords()
            if item.enabled
            and (not due_only or is_sync_due(item.last_synced_at, item.frequency))
        ]
        if not keywords:
            return 0

        own = collector is None
        sink = [] if own else collector

        def sync_one(item) -> bool:
            try:
                self.sync_keyword_now(
                    item.keyword, item.app_id, country=item.country, lang=item.lang, collector=sink
                )
                return True
            except Exception:
                self.logger.exception(
                    "sync_all_keywords failed for %s / %s (%s/%s)",
                    item.keyword,
                    item.app_id,
                    item.country,
                    item.lang,
                )
                return False

        with ThreadPoolExecutor(max_workers=min(6, len(keywords))) as executor:
            count = sum(executor.map(sync_one, keywords))
        if own:
            self._dispatch_notifications(sink)
        return count

    # --- Chart-rank monitors (mirror keyword monitors) -------------------------

    def add_chart_app(
        self,
        app_id: str,
        collection: str,
        category: str | None = "APPLICATION",
        country: str = "us",
        lang: str = "en",
        frequency: str | None = None,
    ) -> None:
        with self.database.session() as session:
            self.tracking_repository.add_chart_app(
                session, app_id, collection, category, country, lang, frequency
            )

    def list_chart_apps(self):
        with self.database.session() as session:
            return self.tracking_repository.list_chart_apps(session)

    def remove_chart_app(
        self,
        app_id: str,
        collection: str,
        category: str | None = "APPLICATION",
        country: str = "us",
        lang: str = "en",
    ) -> int:
        with self.database.session() as session:
            return self.tracking_repository.remove_chart_app(
                session, app_id, collection, category, country, lang
            )

    def toggle_chart_app(
        self,
        app_id: str,
        collection: str,
        category: str | None = "APPLICATION",
        country: str = "us",
        lang: str = "en",
    ) -> bool:
        with self.database.session() as session:
            charts = self.tracking_repository.list_chart_apps(session)
            current = next(
                (
                    item
                    for item in charts
                    if item.app_id == app_id
                    and item.collection == collection
                    and item.category == category
                    and item.country == country
                    and item.lang == lang
                ),
                None,
            )
            next_enabled = not bool(current.enabled) if current is not None else True
            return self.tracking_repository.set_chart_app_enabled(
                session, app_id, collection, category, country, lang, next_enabled
            )

    def sync_chart_now(
        self,
        app_id: str,
        collection: str,
        category: str | None = "APPLICATION",
        country: str = "us",
        lang: str = "en",
        limit: int | None = None,
        collector=None,
    ):
        if self.chart_rank_service is None:
            raise RuntimeError("ChartRankService 未注入。")
        effective_limit = limit or self._default_keyword_limit()
        # Mirror sync_keyword_now: capture the prior *different-day* rank as the alert
        # baseline and whether today's row already exists. rank() upserts one row per day,
        # so a same-day re-sync must NOT re-diff (first_of_day gates it).
        previous_rank = None
        first_of_day = True
        if self.alert_service is not None:
            try:
                previous_rank = self.chart_rank_service.previous_distinct_rank(
                    app_id, collection, category, country, lang
                )
                latest = self.chart_rank_service.latest_rank(
                    app_id, collection, category, country, lang
                )
                today = now_iso()[:10]
                first_of_day = latest is None or (latest.captured_at or "")[:10] != today
            except Exception:
                self.logger.exception(
                    "could not load previous chart rank for %s / %s", app_id, collection
                )
        try:
            result = self.chart_rank_service.rank(
                app_id,
                collection,
                category=category,
                country=country,
                lang=lang,
                limit=effective_limit,
            )
        except Exception as exc:
            self.logger.exception(
                "sync_chart_now failed for %s / %s (%s/%s)",
                app_id,
                collection,
                country,
                lang,
            )
            if self.alert_service is not None:
                with self.database.session() as session:
                    count = self.tracking_repository.record_chart_failure(
                        session, app_id, collection, category, country, lang, now_iso()
                    )
                failure = self.alert_service.record_fetch_failure(
                    app_id,
                    str(exc),
                    title=f"榜单 {collection}/{category or '-'}",
                    country=country,
                    lang=lang,
                    failure_count=count,
                )
                self._handle_new_alerts([failure], collector)
            raise
        new_alerts: list = []
        prior_failures = 0
        with self.database.session() as session:
            self.tracking_repository.add_chart_app(
                session, app_id, collection, category, country, lang
            )
            self.tracking_repository.update_chart_sync_time(
                session, app_id, collection, category, country, lang, now_iso()
            )
            # A returned result (even "未命中"/found=False) is a successful fetch.
            prior_failures = self.tracking_repository.record_chart_success(
                session, app_id, collection, category, country, lang
            )
            if self.alert_service is not None and first_of_day:
                new_alerts = self.alert_service.create_chart_alerts(
                    session, previous_rank, result
                )
        if self.alert_service is not None and prior_failures >= self._escalate_after():
            new_alerts = list(new_alerts) + [
                self.alert_service.record_fetch_recovered(
                    app_id,
                    title=f"榜单 {collection}/{category or '-'}",
                    previous_failures=prior_failures,
                    country=country,
                    lang=lang,
                )
            ]
        self._handle_new_alerts(new_alerts, collector)
        return result

    def sync_all_charts(self, due_only: bool = False, collector=None) -> int:
        charts = [
            item
            for item in self.list_chart_apps()
            if item.enabled
            and (not due_only or is_sync_due(item.last_synced_at, item.frequency))
        ]
        if not charts:
            return 0

        own = collector is None
        sink = [] if own else collector

        def sync_one(item) -> bool:
            try:
                self.sync_chart_now(
                    item.app_id,
                    item.collection,
                    category=item.category,
                    country=item.country,
                    lang=item.lang,
                    collector=sink,
                )
                return True
            except Exception:
                self.logger.exception(
                    "sync_all_charts failed for %s / %s (%s/%s)",
                    item.app_id,
                    item.collection,
                    item.country,
                    item.lang,
                )
                return False

        with ThreadPoolExecutor(max_workers=min(6, len(charts))) as executor:
            count = sum(executor.map(sync_one, charts))
        if own:
            self._dispatch_notifications(sink)
        return count

    def sync_all(self, due_only: bool = False) -> dict[str, int]:
        # Run the app, keyword and chart groups concurrently (each is itself parallel).
        # ``due_only`` is set by the scheduler so each item honors its own cadence; the
        # manual "同步全部" button leaves it False to force-sync everything.
        # A shared collector aggregates every new alert across all groups so we push a
        # single, de-duplicated notification batch at the end instead of one per item.
        collected = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            apps_future = executor.submit(self.sync_all_apps, due_only, collected)
            keywords_future = executor.submit(self.sync_all_keywords, due_only, collected)
            charts_future = executor.submit(self.sync_all_charts, due_only, collected)
            result = {
                "apps": apps_future.result(),
                "keywords": keywords_future.result(),
                "charts": charts_future.result(),
            }
        self._dispatch_notifications(collected)
        return result

    def get_history(self, app_id: str, country: str = "us", lang: str = "en"):
        with self.database.session() as session:
            return self.snapshot_repository.get_history(session, app_id, country, lang)

    # Numeric snapshot fields that get a signed delta vs. the previous row.
    _DIFF_NUMERIC_FIELDS = ("rating", "ratings_count", "reviews_count", "real_installs")
    # Discrete snapshot fields that get a "changed" boolean vs. the previous row.
    _DIFF_DISCRETE_FIELDS = ("version", "price")

    def history_with_diffs(
        self,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        start: str | None = None,
        end: str | None = None,
    ) -> list[dict]:
        """Per-day snapshot history with field-level day-over-day diffs — pure local
        computation, no network and no writes.

        Reads ``get_history`` (one row per calendar day, ascending by ``captured_at``)
        inside a single session, optionally slicing to ``start <= captured_at <= end``
        (ISO-string comparison; either bound may be omitted). For every row it emits a
        flat dict carrying the current values of the key fields plus, against the
        *previous kept row*:
          - ``<field>_delta`` for each numeric field (rating/ratings_count/
            reviews_count/real_installs) — ``None`` on the first row;
          - ``<field>_changed`` boolean for each discrete field (version/price) —
            ``False`` on the first row.

        Returns ``[]`` when there is no history (or none in range).
        """
        with self.database.session() as session:
            history = self.snapshot_repository.get_history(session, app_id, country, lang)

        rows = [
            snap
            for snap in history
            if (start is None or (snap.captured_at or "") >= start)
            and (end is None or (snap.captured_at or "") <= end)
        ]

        results: list[dict] = []
        previous = None
        for snap in rows:
            row: dict = {
                "captured_at": snap.captured_at,
                "rating": snap.rating,
                "ratings_count": snap.ratings_count,
                "reviews_count": snap.reviews_count,
                "real_installs": snap.real_installs,
                "installs": snap.installs,
                "version": snap.version,
                "price": snap.price,
                "contains_ads": snap.contains_ads,
            }
            for field in self._DIFF_NUMERIC_FIELDS:
                row[f"{field}_delta"] = self._numeric_delta(
                    getattr(previous, field, None) if previous is not None else None,
                    getattr(snap, field, None),
                )
            for field in self._DIFF_DISCRETE_FIELDS:
                if previous is None:
                    row[f"{field}_changed"] = False
                else:
                    row[f"{field}_changed"] = getattr(previous, field, None) != getattr(
                        snap, field, None
                    )
            results.append(row)
            previous = snap
        return results

    @staticmethod
    def _numeric_delta(prev, curr):
        """Signed ``curr - prev`` as a float, or ``None`` if either side is missing
        or non-numeric (so the UI shows no arrow for the first row / unknown values)."""
        if prev is None or curr is None:
            return None
        try:
            return float(curr) - float(prev)
        except (TypeError, ValueError):
            return None

    def _default_keyword_limit(self) -> int:
        if self.settings_service is None:
            return 100
        raw = self.settings_service.get("default_limit", "100") or "100"
        try:
            return int(raw)
        except ValueError:
            return 100
