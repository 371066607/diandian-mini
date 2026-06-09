from __future__ import annotations

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui.widgets.message_box import show_error, show_info
from app.ui.widgets.flow_layout import FlowLayout
from app.utils.worker import Worker


class BasePage(QWidget):
    def __init__(self, services: dict[str, object], window_api, logger, title: str, subtitle: str):
        super().__init__()
        self.services = services
        self.window_api = window_api
        self.logger = logger
        self._workers: list[Worker] = []

        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(28, 24, 28, 24)
        self.root_layout.setSpacing(20)
        self.root_layout.addLayout(self.build_header(title, subtitle))

    def build_header(self, title: str, subtitle: str):
        layout = QVBoxLayout()
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 24px; font-weight: 700; color: #0F172A;")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setStyleSheet("font-size: 13px; color: #64748B;")
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        return layout

    def create_card(self, title: str | None = None) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)
        if title:
            label = QLabel(title)
            label.setStyleSheet("font-size: 14px; font-weight: 600; color: #1E293B;")
            layout.addWidget(label)
        return card, layout

    def create_input(self, placeholder: str, width: int | None = None) -> QLineEdit:
        line_edit = QLineEdit()
        line_edit.setPlaceholderText(placeholder)
        if width:
            line_edit.setMinimumWidth(width)
            line_edit.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        else:
            line_edit.setMinimumWidth(180)
            line_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return line_edit

    def create_primary_button(self, text: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("PrimaryButton")
        button.setMinimumHeight(38)
        return button

    def create_secondary_button(self, text: str) -> QPushButton:
        button = QPushButton(text)
        button.setMinimumHeight(38)
        return button

    def run_task(self, loading_text: str, fn, on_success) -> None:
        worker = Worker(fn)
        self._workers.append(worker)
        # The blocking network call can't be killed mid-flight, so "cancel" hides the
        # overlay immediately and discards the result when it eventually arrives.
        state = {"cancelled": False}

        def finish(result):
            if not state["cancelled"]:
                self.window_api.hide_loading()
                on_success(result)
            self._cleanup_worker(worker)

        def fail(message: str):
            if not state["cancelled"]:
                self.window_api.hide_loading()
                self.show_error(message)
            self._cleanup_worker(worker)

        def cancel():
            state["cancelled"] = True
            self.window_api.hide_loading()

        worker.signals.started.connect(lambda: self.window_api.show_loading(loading_text, cancel))
        worker.signals.finished.connect(finish)
        worker.signals.error.connect(fail)
        QThreadPool.globalInstance().start(worker)

    def run_background(self, fn, on_success, on_error=None) -> None:
        """Run ``fn`` off the UI thread without the loading overlay.

        Use for cheap, frequent refreshes (e.g. local SQLite reads on navigation)
        where a flashing overlay would be worse than the work itself. ``on_success``
        / ``on_error`` run back on the UI thread via Qt's queued signal delivery.
        """
        worker = Worker(fn)
        self._workers.append(worker)

        def finish(result):
            on_success(result)
            self._cleanup_worker(worker)

        def fail(message: str):
            if on_error is not None:
                on_error(message)
            else:
                self.show_error(message)
            self._cleanup_worker(worker)

        worker.signals.finished.connect(finish)
        worker.signals.error.connect(fail)
        QThreadPool.globalInstance().start(worker)

    def show_error(self, message: str) -> None:
        show_error(self, message)

    def show_info(self, message: str) -> None:
        show_info(self, message)

    def show_status(self, message: str) -> None:
        """Non-blocking success/info feedback via a transient toast.

        Preferred over show_info for routine actions so the user isn't forced to
        dismiss a modal dialog after every search/fetch/save.
        """
        show_toast = getattr(self.window_api, "show_toast", None)
        if show_toast is not None:
            show_toast(message)
        else:  # pragma: no cover - defensive fallback
            self.show_info(message)

    def create_actions_row(self, widgets: list[QWidget]):
        row = FlowLayout(spacing=10)
        for widget in widgets:
            row.addWidget(widget)
        return row

    def create_stat_value(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-size: 18px; font-weight: 700; color: #0F172A;")
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return label

    def get_default_settings(self) -> dict[str, str]:
        settings_service = self.services.get("settings_service")
        if settings_service is None:
            return {
                "default_country": "us",
                "default_lang": "en",
                "default_limit": "50",
            }
        return settings_service.get_all()

    def _cleanup_worker(self, worker: Worker) -> None:
        if worker in self._workers:
            self._workers.remove(worker)
