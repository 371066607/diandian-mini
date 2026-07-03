"""Composition root — every service is constructed here and collaborators injected.

Lives under ``app/`` (not in ``main.py``) ON PURPOSE: the hot-patch overlays a downloaded
``app/`` onto ``sys.path`` but never re-runs the bundled ``main.py`` (it's already the
running ``__main__``). So anything that must reach existing users through a code patch —
notably ADDING A NEW SERVICE to the registry — has to live here, under ``app/``. ``main.py``
is just a thin launcher that imports and calls ``build_services``. Add new services here and
thread them through, same as before.
"""

from __future__ import annotations

import os
import sys
import uuid

from app.constants import (
    AUTH_DEVICE_ID_SETTING,
    DEFAULT_SETTINGS,
    DEFAULT_STOREINTEL_API_URL,
    DEV_STOREINTEL_API_URL,
)
from app.db.database import Database
from app.jobs.scheduler import AppScheduler, RemoteSchedulerProxy
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
from app.services.store_intel_api_client import StoreIntelApiClient
from app.services.tracking_service import TrackingService
from app.services.update_service import UpdateService
from app.utils.network import apply_proxy_env
from app.utils.normalize import safe_float


_DISABLED_API_VALUES = {"", "0", "false", "no", "off", "none", "local", "legacy"}
_LOCAL_MODE_ENV_KEYS = ("CATCH_RADAR_LEGACY_LOCAL_MODE", "CATCH_RADAR_OFFLINE_MODE")


def _env_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _store_intel_api_url() -> str | None:
    if any(_env_truthy(os.environ.get(key)) for key in _LOCAL_MODE_ENV_KEYS):
        return None

    for key in ("CATCH_RADAR_STOREINTEL_API_URL", "STOREINTEL_API_URL"):
        if key in os.environ:
            value = (os.environ.get(key) or "").strip()
            if value.lower() in _DISABLED_API_VALUES:
                return None
            return value

    # No explicit env var set: packaged builds (PyInstaller sets sys.frozen)
    # default to production, since that's what real users run. Running from
    # source defaults to the local dev backend instead, so a plain
    # `python main.py` during development never talks to production by
    # accident — connecting to production still requires explicitly setting
    # CATCH_RADAR_STOREINTEL_API_URL.
    if getattr(sys, "frozen", False):
        return DEFAULT_STOREINTEL_API_URL
    return DEV_STOREINTEL_API_URL


def _store_intel_device_id(settings_service: SettingsService) -> str:
    stored = (settings_service.get(AUTH_DEVICE_ID_SETTING, "") or "").strip()
    if stored:
        return stored
    device_id = f"desktop-{uuid.uuid4().hex}"
    settings_service.set_many({AUTH_DEVICE_ID_SETTING: device_id})
    return device_id


def build_services(database: Database) -> dict[str, object]:
    settings_service = SettingsService(database)
    store_intel_api_url = _store_intel_api_url()
    settings = (
        settings_service.get_all() if store_intel_api_url is None else DEFAULT_SETTINGS.copy()
    )
    if store_intel_api_url is None:
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
    history_retention_service = HistoryRetentionService(database, settings_service=settings_service)
    update_service = UpdateService()
    export_service = ExportService(database)
    device_id = _store_intel_device_id(settings_service) if store_intel_api_url else None
    store_intel_api_client = StoreIntelApiClient(store_intel_api_url, device_id=device_id)
    # API mode is the default desktop shape: the Go backend owns scheduled sync,
    # refresh workers, persistence, and scraping. Local scheduling is kept only
    # for explicit legacy/offline mode.
    if store_intel_api_client.enabled:
        scheduler = RemoteSchedulerProxy()
    else:
        # The scheduler invokes ``sync_tracked_job(tracking_service)`` (its ``args`` are
        # fixed and scheduler.py is not edited here), so the daily cleanup is reached by
        # attaching the retention service to tracking_service; sync_tracked_job picks it up
        # via getattr.
        tracking_service.retention_service = history_retention_service
        scheduler = AppScheduler(
            settings_service=settings_service, tracking_service=tracking_service
        )
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
        "store_intel_api_client": store_intel_api_client,
    }
