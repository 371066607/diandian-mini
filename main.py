from __future__ import annotations

import argparse
import sys

from app.config import ensure_runtime_dirs
from app.db.database import Database
from app.db.migrations import migrate
from app.jobs.scheduler import AppScheduler
from app.logging_config import setup_logging
from app.services.alert_service import AlertService
from app.services.chart_service import ChartService
from app.services.google_play_service import GooglePlayService
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
    keyword_service = KeywordService(google_play_service, database=database)
    monetization_service = MonetizationService()
    alert_service = AlertService(database)
    tracking_service = TrackingService(
        database=database,
        google_play_service=google_play_service,
        keyword_service=keyword_service,
        alert_service=alert_service,
        settings_service=settings_service,
    )
    review_service = ReviewService(database=database, google_play_service=google_play_service)
    chart_service = ChartService(database=database, google_play_service=google_play_service)
    scheduler = AppScheduler(settings_service=settings_service, tracking_service=tracking_service)
    update_service = UpdateService()
    return {
        "settings_service": settings_service,
        "google_play_service": google_play_service,
        "keyword_service": keyword_service,
        "monetization_service": monetization_service,
        "tracking_service": tracking_service,
        "review_service": review_service,
        "chart_service": chart_service,
        "alert_service": alert_service,
        "scheduler": scheduler,
        "update_service": update_service,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", action="store_true", help="初始化数据库和服务后退出")
    args = parser.parse_args()

    ensure_runtime_dirs()
    logger = setup_logging()
    database = Database()
    migrate(database)
    services = build_services(database)
    services["settings_service"].ensure_defaults()

    if args.smoke_test:
        print("smoke-ok")
        return 0

    from PySide6.QtCore import QThreadPool
    from PySide6.QtWidgets import QApplication

    from app.ui.main_window import MainWindow

    services["scheduler"].start()

    app = QApplication(sys.argv)
    app.setApplicationName("点点数据 Mini")
    window = MainWindow(database=database, services=services, logger=logger)
    window.show()

    try:
        exit_code = app.exec()
    finally:
        # Closing the window must stop every background thread/process: shut the
        # scheduler down, drop queued worker tasks, and give running ones a bounded
        # window to finish so the process exits promptly instead of hanging on a
        # long network call.
        services["scheduler"].shutdown()
        pool = QThreadPool.globalInstance()
        pool.clear()
        pool.waitForDone(3000)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
