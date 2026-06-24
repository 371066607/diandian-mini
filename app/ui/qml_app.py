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


def _make_window_immersive(window) -> None:
    """macOS only, best-effort: transparent title bar + hidden title + content extends
    under it, so the window blends into the dark/light theme instead of showing the
    stock gray Qt title bar. Any failure just leaves the standard window (never raises)."""
    if sys.platform != "darwin":
        return
    try:
        import ctypes

        libobjc = ctypes.CDLL("/usr/lib/libobjc.dylib")
        libobjc.sel_registerName.restype = ctypes.c_void_p
        libobjc.sel_registerName.argtypes = [ctypes.c_char_p]
        send_addr = ctypes.cast(libobjc.objc_msgSend, ctypes.c_void_p).value

        def msg(restype, argtypes, obj, selector, *args):
            fn = ctypes.CFUNCTYPE(restype, *argtypes)(send_addr)
            return fn(obj, libobjc.sel_registerName(selector.encode()), *args)

        handle = int(window.winId())
        if not handle:
            return
        view = ctypes.c_void_p(handle)
        ns = msg(ctypes.c_void_p, [ctypes.c_void_p, ctypes.c_void_p], view, "window")
        if not ns:
            return
        ns = ctypes.c_void_p(ns)
        # styleMask |= NSWindowStyleMaskFullSizeContentView (1 << 15)
        mask = msg(ctypes.c_ulong, [ctypes.c_void_p, ctypes.c_void_p], ns, "styleMask")
        msg(None, [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong],
            ns, "setStyleMask:", mask | (1 << 15))
        msg(None, [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool],
            ns, "setTitlebarAppearsTransparent:", True)
        # NSWindowTitleHidden = 1
        msg(None, [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_long],
            ns, "setTitleVisibility:", 1)
    except Exception:
        pass


def run_qml_app(database, services, logger, argv: list[str]) -> int:
    app = QApplication(argv)
    app.setApplicationName("catch-radar")
    QQuickStyle.setStyle("Fusion")

    bridge = QmlBridge(database=database, services=services, logger=logger)
    services["tracking_service"].set_notifier(bridge.notify)

    engine = QQmlApplicationEngine()
    engine.setInitialProperties({"bridge": bridge, "appTitle": APP_TITLE})
    engine.load(QUrl.fromLocalFile(str(_resolve_qml_file())))
    roots = engine.rootObjects()
    if not roots:
        return 1
    _make_window_immersive(roots[0])

    bridge.refreshAll()
    return app.exec()
