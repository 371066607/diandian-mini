"""Regression guard for the invisible-input-text bug.

The global stylesheet must pin an explicit text color on inputs so typed text stays
visible even when the OS palette (e.g. macOS Dark Mode) would default it to white,
which previously rendered white-on-white. Headless service/logic tests cannot catch
this — it only shows up when the widget is actually rendered, so we render to pixels.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QLineEdit

from app.ui.main_window import MainWindow


def _dark_pixels(widget):
    image = widget.grab().toImage()
    count = 0
    for x in range(image.width()):
        for y in range(image.height()):
            c = image.pixelColor(x, y)
            if c.red() < 110 and c.green() < 110 and c.blue() < 110:
                count += 1
    return count


def test_input_text_visible_under_dark_palette():
    try:
        app = QApplication.instance() or QApplication([])
    except Exception:  # pragma: no cover - no Qt platform
        pytest.skip("no Qt platform available")

    original = app.palette()
    try:
        # emulate a dark system palette where default text would be white
        dark = QPalette()
        dark.setColor(QPalette.ColorRole.Text, QColor("white"))
        dark.setColor(QPalette.ColorRole.WindowText, QColor("white"))
        app.setPalette(dark)

        field = QLineEdit()
        field.setStyleSheet(MainWindow.build_stylesheet(None))
        field.setText("可见 ABC 123")
        field.resize(240, 44)

        # the app stylesheet forces dark text, so glyphs render as dark pixels even
        # though the palette alone would have produced white-on-white (0 dark pixels)
        assert _dark_pixels(field) > 30
    finally:
        app.setPalette(original)
