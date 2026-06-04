from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class LoadingOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setWindowFlags(Qt.WindowType.Widget | Qt.WindowType.FramelessWindowHint)
        self.hide()
        self._on_cancel = None

        self.label = QLabel("加载中...", self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet(
            "color: white; font-size: 18px; font-weight: 600; background: transparent;"
        )

        self.cancel_button = QPushButton("取消", self)
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.setStyleSheet(
            "QPushButton { color: white; background: rgba(255, 255, 255, 0.14);"
            " border: 1px solid rgba(255, 255, 255, 0.45); border-radius: 10px;"
            " padding: 8px 28px; font-size: 14px; font-weight: 600; }"
            "QPushButton:hover { background: rgba(255, 255, 255, 0.26); }"
        )
        self.cancel_button.clicked.connect(self._handle_cancel)

        layout = QVBoxLayout(self)
        layout.addStretch()
        layout.addWidget(self.label, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(14)
        layout.addWidget(self.cancel_button, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()

    def show_message(self, message: str, on_cancel=None) -> None:
        self.label.setText(message)
        self._on_cancel = on_cancel
        self.cancel_button.setVisible(on_cancel is not None)
        self.resize(self.parent().size())
        self.show()
        self.raise_()

    def _handle_cancel(self) -> None:
        callback = self._on_cancel
        self._on_cancel = None
        if callback is not None:
            callback()

    def paintEvent(self, event) -> None:  # pragma: no cover - UI rendering
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(15, 23, 42, 140))
        super().paintEvent(event)
