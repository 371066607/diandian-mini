from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui.widgets.message_box import show_error, show_info
from app.utils.network import apply_proxy_env
from app.utils.normalize import safe_float
from app.utils.time_utils import DEFAULT_SYNC_TIME, is_valid_time_of_day


class SettingsFormWidget(QWidget):
    """The global settings form, shared by the Settings and Tracking pages.

    Owns the single save path: validate -> persist -> apply proxy -> retune the
    scraper -> reload the scheduler. Keeping this in one place avoids the two
    divergent copies that previously both carried the malformed-time crash.
    """

    def __init__(self, services: dict[str, object], on_saved=None, parent=None):
        super().__init__(parent)
        self.services = services
        self.settings_service = services["settings_service"]
        self.on_saved = on_saved

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        form = QFormLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(16)

        self.default_country = QLineEdit()
        self.default_lang = QLineEdit()
        self.default_limit = QLineEdit()
        self.scheduler_enabled = QLineEdit()
        self.daily_sync_time = QLineEdit()
        self.request_delay = QLineEdit()
        self.database_path = QLineEdit()
        self.proxy = QLineEdit()

        form.addRow("默认国家", self.default_country)
        form.addRow("默认语言", self.default_lang)
        form.addRow("默认 limit", self.default_limit)
        form.addRow("启用定时任务", self.scheduler_enabled)
        form.addRow("每日同步时间", self.daily_sync_time)
        form.addRow("请求延迟秒数", self.request_delay)
        form.addRow("数据库路径", self.database_path)
        form.addRow("代理", self.proxy)
        layout.addLayout(form)

        self.save_button = QPushButton("保存设置")
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.clicked.connect(self.save)
        layout.addWidget(self.save_button)

        self.load()

    def load(self) -> None:
        values = self.settings_service.get_all()
        self.default_country.setText(values["default_country"])
        self.default_lang.setText(values["default_lang"])
        self.default_limit.setText(values["default_limit"])
        self.scheduler_enabled.setText(values["scheduler_enabled"])
        self.daily_sync_time.setText(values["daily_sync_time"])
        self.request_delay.setText(values["request_delay_seconds"])
        self.database_path.setText(values["database_path"])
        self.proxy.setText(values["proxy"])

    def save(self) -> None:
        sync_time = self.daily_sync_time.text().strip() or DEFAULT_SYNC_TIME
        if not is_valid_time_of_day(sync_time):
            show_error(self, "每日同步时间格式不正确，请使用 HH:MM（例如 09:00）。")
            return

        proxy_value = self.proxy.text().strip()
        request_delay = self.request_delay.text().strip() or "1"
        payload = {
            "default_country": self.default_country.text().strip() or "us",
            "default_lang": self.default_lang.text().strip() or "en",
            "default_limit": self.default_limit.text().strip() or "50",
            "scheduler_enabled": self.scheduler_enabled.text().strip() or "true",
            "daily_sync_time": sync_time,
            "request_delay_seconds": request_delay,
            "database_path": self.database_path.text().strip() or "./data/diandian_mini.sqlite3",
            "proxy": proxy_value,
        }
        self.settings_service.set_many(payload)

        apply_proxy_env(proxy_value)
        google_play_service = self.services.get("google_play_service")
        if google_play_service is not None and hasattr(google_play_service, "configure"):
            google_play_service.configure(request_delay_seconds=safe_float(request_delay, 1.0))
        scheduler = self.services.get("scheduler")
        if scheduler is not None:
            scheduler.reload_jobs()

        show_info(self, "设置已保存。")
        if self.on_saved is not None:
            self.on_saved()
