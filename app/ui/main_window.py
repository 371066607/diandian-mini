from __future__ import annotations

from PySide6.QtCore import QThreadPool, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from app.utils.worker import Worker

from app.constants import APP_TITLE, SIDEBAR_ITEMS, WINDOW_HEIGHT, WINDOW_WIDTH
from app.ui.alert_labels import alert_severity_label
from app.ui.pages.app_detail_page import AppDetailPage
from app.ui.pages.alerts_page import AlertsPage
from app.ui.pages.app_search_page import AppSearchPage
from app.ui.pages.charts_page import ChartsPage
from app.ui.pages.dashboard_page import DashboardPage
from app.ui.pages.history_page import HistoryPage
from app.ui.pages.keywords_page import KeywordsPage
from app.ui.pages.reviews_page import ReviewsPage
from app.ui.pages.settings_page import SettingsPage
from app.ui.pages.tracking_page import TrackingPage
from app.ui.widgets.loading_overlay import LoadingOverlay
from app.ui.widgets.toast import Toast


class MainWindow(QMainWindow):
    # Emitted by ``notify`` (called from background sync threads) and delivered on the
    # UI thread via Qt's queued connection — the ONLY safe way to touch widgets from the
    # scheduler / worker threads.
    new_alerts_signal = Signal(list)

    def __init__(self, database, services, logger):
        super().__init__()
        self.database = database
        self.services = services
        self.logger = logger
        self.page_indices: dict[str, int] = {}
        self.page_objects: dict[str, QWidget] = {}
        self.nav_buttons: dict[str, QPushButton] = {}
        self.nav_labels: dict[str, str] = dict(SIDEBAR_ITEMS)
        self._tray: QSystemTrayIcon | None = None

        self.setWindowTitle(APP_TITLE)
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setMinimumSize(1280, 800)
        self.setStyleSheet(self.build_stylesheet())

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar = self.build_sidebar()
        content_frame = QFrame()
        content_frame.setObjectName("ContentFrame")
        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack)

        root_layout.addWidget(sidebar)
        root_layout.addWidget(content_frame, 1)
        self.setCentralWidget(root)

        self.loading_overlay = LoadingOverlay(root)
        self.toast = Toast(root)
        self.build_pages()
        self.new_alerts_signal.connect(self._on_new_alerts)
        self._setup_tray()
        self.navigate_to("dashboard")
        self.refresh_alert_badge()
        self.statusBar().showMessage("Google Play / 本地 SQLite")
        self.check_for_updates_quietly()

    def resizeEvent(self, event) -> None:  # pragma: no cover - UI rendering
        super().resizeEvent(event)
        self.loading_overlay.resize(self.centralWidget().size())

    def build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 24, 16, 20)
        layout.setSpacing(8)

        logo = QLabel("点点数据 Mini")
        logo.setStyleSheet("font-size: 18px; font-weight: 800; color: white;")
        layout.addWidget(logo)
        layout.addSpacing(24)

        for key, label in SIDEBAR_ITEMS:
            button = QPushButton(label)
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, page_key=key: self.navigate_to(page_key))
            layout.addWidget(button)
            self.nav_buttons[key] = button

        layout.addStretch()
        footer = QLabel("Google Play / 本地 SQLite")
        footer.setStyleSheet("font-size: 12px; color: #94A3B8;")
        layout.addWidget(footer)
        return sidebar

    def build_pages(self) -> None:
        pages = {
            "dashboard": DashboardPage(self.services, self, self.logger),
            "app_search": AppSearchPage(self.services, self, self.logger),
            "app_detail": AppDetailPage(self.services, self, self.logger),
            "reviews": ReviewsPage(self.services, self, self.logger),
            "charts": ChartsPage(self.services, self, self.logger),
            "keywords": KeywordsPage(self.services, self, self.logger),
            "tracking": TrackingPage(self.services, self, self.logger),
            "history": HistoryPage(self.services, self, self.logger),
            "alerts": AlertsPage(self.services, self, self.logger),
            "settings": SettingsPage(self.services, self, self.logger),
        }
        for key, widget in pages.items():
            self.page_indices[key] = self.stack.addWidget(widget)
            self.page_objects[key] = widget

    def navigate_to(self, page_key: str) -> None:
        self.stack.setCurrentIndex(self.page_indices[page_key])
        for key, button in self.nav_buttons.items():
            button.setChecked(key == page_key)
        page = self.page_objects[page_key]
        if hasattr(page, "on_activated"):
            page.on_activated()
        # Reading/marking alerts changes the unread count; keep the sidebar badge fresh.
        self.refresh_alert_badge()

    def _setup_tray(self) -> None:
        """Create the system-tray icon if the platform supports it; degrade silently
        otherwise (the unread badge still works)."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon = self.windowIcon()
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation)
        self._tray = QSystemTrayIcon(icon, self)
        self._tray.setToolTip(APP_TITLE)
        # Clicking the tray icon / its bubble jumps to the alert center.
        self._tray.activated.connect(lambda _reason: self.navigate_to("alerts"))
        self._tray.messageClicked.connect(lambda: self.navigate_to("alerts"))
        self._tray.show()

    def notify(self, alerts) -> None:
        """Thread-safe entry point handed to TrackingService. Marshals the new alerts
        onto the UI thread via the queued signal — never touches widgets directly."""
        self.new_alerts_signal.emit(list(alerts))

    def _on_new_alerts(self, alerts) -> None:
        # Runs on the UI thread (queued delivery). Refresh the badge and pop one bubble.
        self.refresh_alert_badge()
        if not alerts or self._tray is None:
            return
        top = alerts[0]
        if len(alerts) == 1:
            heading = f"新提醒 · {alert_severity_label(top.severity)}"
            body = top.message
        else:
            heading = f"{len(alerts)} 条新提醒"
            body = f"{top.message} 等 {len(alerts)} 条"
        self._tray.showMessage(heading, body, QSystemTrayIcon.MessageIcon.Information, 8000)

    def refresh_alert_badge(self) -> None:
        button = self.nav_buttons.get("alerts")
        if button is None:
            return
        try:
            count = self.services["alert_service"].unread_count()
        except Exception:  # pragma: no cover - defensive; badge must never crash nav
            count = 0
        base = self.nav_labels.get("alerts", "提醒")
        button.setText(f"{base} ({count})" if count else base)

    def open_app_detail(self, app_id: str) -> None:
        self.navigate_to("app_detail")
        detail_page = self.page_objects["app_detail"]
        detail_page.load_app(app_id)

    def open_history(self, app_id: str, country: str = "us", lang: str = "en") -> None:
        self.navigate_to("history")
        history_page = self.page_objects["history"]
        history_page.load_app(app_id, country=country, lang=lang)

    def open_reviews(
        self,
        app_id: str,
        *,
        country: str = "us",
        lang: str = "en",
        auto_fetch: bool = True,
    ) -> None:
        self.navigate_to("reviews")
        reviews_page = self.page_objects["reviews"]
        reviews_page.load_app(app_id, country=country, lang=lang, auto_fetch=auto_fetch)

    def show_loading(self, text: str, on_cancel=None) -> None:
        self.loading_overlay.show_message(text, on_cancel)

    def hide_loading(self) -> None:
        self.loading_overlay.hide()

    def show_toast(self, message: str) -> None:
        self.toast.show_message(message)

    def check_for_updates_quietly(self) -> None:
        """Background check at startup; toasts only if a newer release exists."""
        service = self.services.get("update_service")
        if service is None:
            return
        worker = Worker(service.check)
        self._update_worker = worker  # keep a reference so it isn't GC'd mid-run
        worker.signals.finished.connect(self._on_startup_update)
        QThreadPool.globalInstance().start(worker)

    def _on_startup_update(self, result) -> None:
        if getattr(result, "mode", "") == "patch" and getattr(result, "can_patch", False):
            self.show_toast(f"发现新版本 {result.latest_label}，可在设置页一键更新")

    def build_stylesheet(self) -> str:
        return """
        QMainWindow {
            background: #F3F5F9;
        }
        #Sidebar {
            background: #1E293B;
        }
        #ContentFrame {
            background: #F6F7FB;
        }
        QFrame#Card {
            background: white;
            border: 1px solid #E2E8F0;
            border-radius: 18px;
        }
        QLabel {
            color: #0F172A;
        }
        QLineEdit, QTextEdit {
            background: white;
            color: #0F172A;
            selection-background-color: #DBEAFE;
            selection-color: #0F172A;
            border: 1px solid #CBD5E1;
            border-radius: 12px;
            padding: 10px 12px;
            font-size: 13px;
        }
        QPushButton {
            background: white;
            border: 1px solid #CBD5E1;
            border-radius: 12px;
            padding: 10px 18px;
            font-size: 13px;
            color: #1E293B;
        }
        QPushButton:hover {
            border-color: #94A3B8;
        }
        QPushButton:checked {
            background: #3B82F6;
            color: white;
            border-color: #3B82F6;
        }
        QPushButton#PrimaryButton {
            background: #2563EB;
            color: white;
            border-color: #2563EB;
        }
        QTableWidget {
            border: none;
            background: white;
            color: #0F172A;
            alternate-background-color: #F8FAFC;
            gridline-color: #E2E8F0;
            selection-background-color: #DBEAFE;
            selection-color: #0F172A;
        }
        QHeaderView::section {
            background: #F8FAFC;
            border: none;
            border-bottom: 1px solid #E2E8F0;
            padding: 10px;
            color: #334155;
            font-weight: 600;
        }
        """
