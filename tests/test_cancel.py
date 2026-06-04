import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from app.ui.pages.base_page import BasePage


class _FakeWindowApi:
    def __init__(self):
        self.loading = False
        self.cancel = None

    def show_loading(self, text, on_cancel=None):
        self.loading = True
        self.cancel = on_cancel

    def hide_loading(self):
        self.loading = False


def _app():
    try:
        return QApplication.instance() or QApplication([])
    except Exception:  # pragma: no cover - no Qt platform
        pytest.skip("no Qt platform available")


def _pump(app, predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_run_task_cancel_discards_result():
    app = _app()
    win = _FakeWindowApi()
    page = BasePage({}, win, None, "t", "s")
    gate = threading.Event()
    results = []

    def slow():
        gate.wait(5)
        return "data"

    page.run_task("loading", slow, results.append)
    assert _pump(app, lambda: win.cancel is not None)  # started -> cancel registered
    assert win.loading is True

    win.cancel()  # user clicks 取消
    assert win.loading is False  # overlay hidden immediately

    gate.set()  # the background worker only now returns
    _pump(app, lambda: not page._workers)
    assert results == []  # cancelled -> the late result is discarded


def test_run_task_delivers_result_when_not_cancelled():
    app = _app()
    win = _FakeWindowApi()
    page = BasePage({}, win, None, "t", "s")
    results = []

    page.run_task("loading", lambda: "data", results.append)
    assert _pump(app, lambda: results == ["data"])
    assert win.loading is False  # overlay hidden on success
