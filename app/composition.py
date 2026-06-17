"""Composition root — every service is constructed here and collaborators injected.

Lives under ``app/`` (not in ``main.py``) ON PURPOSE: the hot-patch overlays a downloaded
``app/`` onto ``sys.path`` but never re-runs the bundled ``main.py`` (it's already the
running ``__main__``). So anything that must reach existing users through a code patch —
notably ADDING A NEW SERVICE to the registry — has to live here, under ``app/``. ``main.py``
is just a thin launcher that imports and calls ``build_services``. Add new services here and
thread them through, same as before.
"""

from __future__ import annotations

from app.db.database import Database
from app.jobs.scheduler import AppScheduler
from app.services.alert_service import AlertService
from app.services.app_store_service import AppStoreService
from app.services.chart_rank_service import ChartRankService
from app.services.chart_service import ChartService
from app.services.export_service import ExportService
from app.services.google_play_service import GooglePlayService
from app.services.history_retention_service import HistoryRetentionService
from app.services.keyword_corpus_service import KeywordCorpusService
from app.services.keyword_coverage_service import KeywordCoverageService
from app.services.keyword_service import KeywordService
from app.services.monetization_service import MonetizationService
from app.services.review_service import ReviewService
from app.services.settings_service import SettingsService
from app.services.tracking_service import TrackingService
from app.services.update_service import UpdateService
from app.utils.network import apply_proxy_env
from app.utils.normalize import safe_float


def build_services(database: Database) -> dict[str, object]:
    settings_service = SettingsService(database)
    settings = settings_service.get_all()
    apply_proxy_env(settings.get("proxy"))
    google_play_service = GooglePlayService(
        request_delay_seconds=safe_float(settings.get("request_delay_seconds"), 1.0)
    )
    app_store_service = AppStoreService()
    keyword_service = KeywordService(google_play_service, database=database)
    keyword_service_app_store = KeywordService(
        app_store_service, database=database, platform="app_store"
    )
    keyword_corpus_service = KeywordCorpusService(database)
    keyword_coverage_service = KeywordCoverageService(
        google_play_service,
        app_store_service=app_store_service,
        keyword_corpus_service=keyword_corpus_service,
    )
    monetization_service = MonetizationService()
    alert_service = AlertService(database, settings_service=settings_service)
    review_service = ReviewService(database=database, google_play_service=google_play_service)
    chart_rank_service = ChartRankService(google_play_service, database=database)
    tracking_service = TrackingService(
        database=database,
        google_play_service=google_play_service,
        keyword_service=keyword_service,
        keyword_service_app_store=keyword_service_app_store,
        alert_service=alert_service,
        settings_service=settings_service,
        review_service=review_service,
        chart_rank_service=chart_rank_service,
    )
    chart_service = ChartService(
        database=database,
        google_play_service=google_play_service,
        app_store_service=app_store_service,
    )
    history_retention_service = HistoryRetentionService(
        database, settings_service=settings_service
    )
    # The scheduler invokes ``sync_tracked_job(tracking_service)`` (its ``args`` are fixed
    # and scheduler.py is not edited here), so the daily cleanup is reached by attaching the
    # retention service to tracking_service; sync_tracked_job picks it up via getattr.
    tracking_service.retention_service = history_retention_service
    scheduler = AppScheduler(settings_service=settings_service, tracking_service=tracking_service)
    update_service = UpdateService()
    export_service = ExportService(database)
    return {
        "settings_service": settings_service,
        "google_play_service": google_play_service,
        "app_store_service": app_store_service,
        "keyword_service": keyword_service,
        "keyword_service_app_store": keyword_service_app_store,
        "keyword_coverage_service": keyword_coverage_service,
        "keyword_corpus_service": keyword_corpus_service,
        "chart_rank_service": chart_rank_service,
        "monetization_service": monetization_service,
        "tracking_service": tracking_service,
        "review_service": review_service,
        "chart_service": chart_service,
        "alert_service": alert_service,
        "history_retention_service": history_retention_service,
        "scheduler": scheduler,
        "update_service": update_service,
        "export_service": export_service,
    }
