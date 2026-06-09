# The hot-patch launcher must run before any `app.*` import so a downloaded code
# patch is loaded ahead of the bundled code — hence app imports come after the call.
# ruff: noqa: E402
from __future__ import annotations

import bootstrap

bootstrap.apply_code_override()

import argparse
import sys

from app.config import ensure_runtime_dirs
from app.db.database import Database
from app.db.migrations import migrate
from app.jobs.scheduler import AppScheduler
from app.logging_config import setup_logging
from app.services.alert_service import AlertService
from app.services.chart_rank_service import ChartRankService
from app.services.chart_service import ChartService
from app.services.export_service import ExportService
from app.services.google_play_service import GooglePlayService
from app.services.history_retention_service import HistoryRetentionService
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
    alert_service = AlertService(database, settings_service=settings_service)
    review_service = ReviewService(database=database, google_play_service=google_play_service)
    chart_rank_service = ChartRankService(google_play_service, database=database)
    tracking_service = TrackingService(
        database=database,
        google_play_service=google_play_service,
        keyword_service=keyword_service,
        alert_service=alert_service,
        settings_service=settings_service,
        review_service=review_service,
        chart_rank_service=chart_rank_service,
    )
    chart_service = ChartService(database=database, google_play_service=google_play_service)
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
        "keyword_service": keyword_service,
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", action="store_true", help="初始化数据库和服务后退出")
    parser.add_argument("--widgets", action="store_true", help="使用旧 Qt Widgets 界面启动")
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

    if args.widgets:
        from PySide6.QtWidgets import QApplication

        from app.ui.main_window import MainWindow
    else:
        from app.ui.qml_app import run_qml_app

    services["scheduler"].start()

    try:
        if args.widgets:
            app = QApplication(sys.argv)
            app.setApplicationName("点点数据 Mini")
            window = MainWindow(database=database, services=services, logger=logger)
            # Wire background-sync alerts to the tray/badge. Done here (not in
            # build_services) so the service layer never imports the UI; headless/smoke
            # runs leave the notifier None.
            services["tracking_service"].set_notifier(window.notify)
            window.show()
            exit_code = app.exec()
        else:
            exit_code = run_qml_app(database, services, logger, sys.argv)
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
