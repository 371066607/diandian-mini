"""Composition root — every service is constructed here and collaborators injected.

Lives under ``app/`` (not in ``main.py``) ON PURPOSE: the hot-patch overlays a downloaded
``app/`` onto ``sys.path`` but never re-runs the bundled ``main.py`` (it's already the
running ``__main__``). So anything that must reach existing users through a code patch —
notably ADDING A NEW SERVICE to the registry — has to live here, under ``app/``. ``main.py``
is just a thin launcher that imports and calls ``build_services``. Add new services here and
thread them through, same as before.

``build_services`` builds the remote API-mode services used by the product path. The old
local-scraping service stack remains in this file for frozen diagnostic code, but normal
startup no longer exposes a local/offline configuration switch.
"""

from __future__ import annotations

import os
import uuid

from app.constants import (
    AUTH_DEVICE_ID_SETTING,
    DEFAULT_STOREINTEL_API_URL,
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
_LOCAL_API_PREFIXES = ("http://127.0.0.1", "http://localhost", "http://[::1]")
_ALLOW_LOCAL_API_ENV = "CATCH_RADAR_ALLOW_LOCAL_API"


def _store_intel_api_url() -> str | None:
    for key in ("CATCH_RADAR_STOREINTEL_API_URL", "STOREINTEL_API_URL"):
        if key in os.environ:
            value = (os.environ.get(key) or "").strip()
            if value.lower() in _DISABLED_API_VALUES:
                return DEFAULT_STOREINTEL_API_URL
            if (
                value.lower().startswith(_LOCAL_API_PREFIXES)
                and (os.environ.get(_ALLOW_LOCAL_API_ENV) or "").strip().lower()
                not in {"1", "true", "yes", "on"}
            ):
                return DEFAULT_STOREINTEL_API_URL
            return value

    return DEFAULT_STOREINTEL_API_URL


def _store_intel_device_id(settings_service: SettingsService) -> str:
    stored = (settings_service.get(AUTH_DEVICE_ID_SETTING, "") or "").strip()
    if stored:
        return stored
    device_id = f"desktop-{uuid.uuid4().hex}"
    settings_service.set_many({AUTH_DEVICE_ID_SETTING: device_id})
    return device_id


def build_api_services(database: Database) -> dict[str, object]:
    """Build the services API mode (qml_bridge.py/controllers) actually calls.

    Always constructed, regardless of mode: ``store_intel_api_client`` is how the mode
    decision itself gets made (its ``.enabled`` flag), and the rest are cheap, mode-agnostic
    services that both API and legacy mode rely on.
    """
    settings_service = SettingsService(database)
    store_intel_api_url = _store_intel_api_url()
    monetization_service = MonetizationService()
    update_service = UpdateService()
    device_id = _store_intel_device_id(settings_service) if store_intel_api_url else None
    store_intel_api_client = StoreIntelApiClient(store_intel_api_url, device_id=device_id)
    return {
        "settings_service": settings_service,
        "store_intel_api_client": store_intel_api_client,
        "monetization_service": monetization_service,
        "update_service": update_service,
    }


def build_legacy_services(database: Database, shared: dict) -> dict[str, object]:
    """Build the local-scraping service stack used only by explicit legacy/offline mode.

    ``shared`` is the dict returned by ``build_api_services``; some of these constructors
    need e.g. ``settings_service`` from it. Only called when
    ``store_intel_api_client.enabled`` is False, since API mode never reaches these services
    (every call site in qml_bridge.py/controllers is gated behind
    ``if api is not None: return ... else: <uses these services>``, and the legacy
    ``--widgets`` UI that calls them unconditionally is refused from starting when API mode
    is enabled).
    """
    settings_service = shared["settings_service"]
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
    export_service = ExportService(database)
    return {
        "google_play_service": google_play_service,
        "app_store_service": app_store_service,
        "keyword_service": keyword_service,
        "keyword_service_app_store": keyword_service_app_store,
        "keyword_coverage_service": keyword_coverage_service,
        "keyword_corpus_service": keyword_corpus_service,
        "chart_rank_service": chart_rank_service,
        "tracking_service": tracking_service,
        "review_service": review_service,
        "chart_service": chart_service,
        "alert_service": alert_service,
        "history_retention_service": history_retention_service,
        "export_service": export_service,
    }


def build_services(database: Database) -> dict[str, object]:
    """Build the remote API-mode service graph.

    API mode is the default desktop shape: the Go backend owns scheduled sync, refresh
    workers, persistence, and scraping, so ``services`` in API mode intentionally lacks keys
    like ``google_play_service``/``tracking_service``/etc.
    """
    services = build_api_services(database)
    if not services["store_intel_api_client"].enabled:
        services.update(build_legacy_services(database, services))
    if services["store_intel_api_client"].enabled:
        scheduler = RemoteSchedulerProxy()
    else:
        # The scheduler invokes ``sync_tracked_job(tracking_service)`` (its ``args`` are
        # fixed and scheduler.py is not edited here), so the daily cleanup is reached by
        # attaching the retention service to tracking_service; sync_tracked_job picks it up
        # via getattr.
        services["tracking_service"].retention_service = services["history_retention_service"]
        scheduler = AppScheduler(
            settings_service=services["settings_service"],
            tracking_service=services["tracking_service"],
        )
    services["scheduler"] = scheduler
    return services
