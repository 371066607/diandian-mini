# The hot-patch launcher must run before any `app.*` import so a downloaded code
# patch is loaded ahead of the bundled code — hence app imports come after the call.
# ruff: noqa: E402
from __future__ import annotations

import bootstrap

bootstrap.apply_code_override()

import argparse
import sys

from app.composition import build_services
from app.config import ensure_runtime_dirs
from app.db.database import Database
from app.db.migrations import migrate
from app.logging_config import setup_logging


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
