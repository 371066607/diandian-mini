from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from app.ui.alert_labels import ALERT_SEVERITY_COLORS, alert_type_label

# Trend token -> (arrow glyph, color). "none" means not enough history to compare.
_TREND_ARROWS = {"up": "↑", "down": "↓", "flat": "→", "none": "-"}
_TREND_COLORS = {"up": "#16A34A", "down": "#DC2626", "flat": "#64748B", "none": "#94A3B8"}

# Status dot colors: red = failing, yellow = unread alerts, green = healthy.
_STATUS_COLORS = {"red": "#DC2626", "yellow": "#D97706", "green": "#16A34A"}


class MonitorCard(QFrame):
    """Pure-display health card for one monitored app.

    Receives a ``MonitorHealth`` DTO and an ``on_open(app_id)`` callback; never
    touches the database. Clicking the card (or the "查看详情" button) invokes
    ``on_open`` with the app's id.
    """

    def __init__(self, health, on_open, parent=None):
        super().__init__(parent)
        self._health = health
        self._on_open = on_open
        self.setObjectName("Card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        # Header: status dot + app name.
        header = QHBoxLayout()
        header.setSpacing(8)
        dot = QLabel("●")
        dot.setStyleSheet(
            f"color: {_STATUS_COLORS[self._status_color()]}; font-size: 14px;"
        )
        header.addWidget(dot)
        name = QLabel(health.title or health.app_id)
        name.setStyleSheet("font-size: 14px; font-weight: 700; color: #0F172A;")
        name.setWordWrap(True)
        header.addWidget(name, 1)
        layout.addLayout(header)

        # Rating row.
        rating_text = (
            f"{health.latest_rating:.2f}" if health.latest_rating is not None else "-"
        )
        layout.addLayout(
            self._metric_row("评分", rating_text, health.rating_trend)
        )
        # Installs row.
        layout.addLayout(
            self._metric_row("安装", health.latest_installs or "-", health.installs_trend)
        )

        # Latest alert row.
        alert_label = QLabel(self._alert_text())
        alert_color = self._alert_color()
        alert_label.setStyleSheet(f"font-size: 12px; color: {alert_color};")
        alert_label.setWordWrap(True)
        layout.addWidget(alert_label)

        # Footer: detail button.
        footer = QHBoxLayout()
        footer.addStretch()
        button = QPushButton("查看详情")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(self._handle_open)
        footer.addWidget(button)
        layout.addLayout(footer)

    # --- behavior ---------------------------------------------------------
    def _handle_open(self) -> None:
        if self._on_open is not None:
            self._on_open(self._health.app_id)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.button() == Qt.MouseButton.LeftButton:
            self._handle_open()
        super().mouseReleaseEvent(event)

    # --- rendering helpers ------------------------------------------------
    def _status_color(self) -> str:
        if self._health.fail_status != "normal":
            return "red"
        if self._health.unread_count > 0:
            return "yellow"
        return "green"

    def _metric_row(self, label: str, value: str, trend: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        key = QLabel(label)
        key.setStyleSheet("font-size: 12px; color: #64748B;")
        row.addWidget(key)
        val = QLabel(value)
        val.setStyleSheet("font-size: 13px; font-weight: 600; color: #1E293B;")
        row.addWidget(val)
        arrow = QLabel(_TREND_ARROWS.get(trend, "-"))
        arrow.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {_TREND_COLORS.get(trend, '#94A3B8')};"
        )
        row.addWidget(arrow)
        row.addStretch()
        return row

    def _alert_text(self) -> str:
        alert = self._health.last_alert
        if not alert:
            return "暂无告警"
        return alert_type_label(alert.get("type", ""))

    def _alert_color(self) -> str:
        alert = self._health.last_alert
        if not alert:
            return "#94A3B8"
        return ALERT_SEVERITY_COLORS.get(alert.get("severity"), "#64748B")
