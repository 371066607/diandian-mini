from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from app.constants import APP_TITLE
from app.ui.qml_bridge import QmlBridge


def _resolve_qml_file() -> Path:
    """Locate Main.qml in dev runs, hot-patch overrides, and frozen bundles.

    Module-relative first: in a dev checkout this is app/qml/, and when a hot patch
    is active the override's qml_app.py resolves into app_override/app/qml/ (the
    patch zip ships the .qml files). In a frozen bundle without a patch the modules
    live in the PYZ, so fall back to the data files at <_MEIPASS>/app/qml/.
    """
    candidates = [Path(__file__).resolve().parents[1] / "qml" / "Main.qml"]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "app" / "qml" / "Main.qml")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def run_qml_app(database, services, logger, argv: list[str]) -> int:
    app = QApplication(argv)
    app.setApplicationName("点点数据 Mini")
    QQuickStyle.setStyle("Fusion")

    bridge = QmlBridge(database=database, services=services, logger=logger)
    services["tracking_service"].set_notifier(bridge.notify)

    engine = QQmlApplicationEngine()
    engine.setInitialProperties({"bridge": bridge, "appTitle": APP_TITLE})
    engine.load(QUrl.fromLocalFile(str(_resolve_qml_file())))
    if not engine.rootObjects():
        return 1

    bridge.refreshAll()
    return app.exec()
