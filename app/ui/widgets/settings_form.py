from __future__ import annotations

from PySide6.QtCore import QTime
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from app.constants import DEFAULT_SETTINGS
from app.ui.widgets.message_box import show_error, show_info
from app.utils.network import apply_proxy_env
from app.utils.normalize import safe_float
from app.utils.time_utils import DEFAULT_SYNC_TIME, is_valid_time_of_day, parse_time_of_day


def _section_label(text: str) -> QLabel:
    """A bold sub-heading used to break the form into readable groups."""
    label = QLabel(text)
    font = label.font()
    font.setBold(True)
    label.setFont(font)
    return label


def _format_float(value: float) -> str:
    """Render a spinbox value as a compact string (drop a trailing ``.0``)."""
    if value == int(value):
        return str(int(value))
    return ("%g" % value)


class SettingsFormWidget(QWidget):
    """The global settings form, shared by the Settings and Tracking pages.

    Owns the single save path: validate -> persist -> apply proxy -> retune the
    scraper -> reload the scheduler. Keeping this in one place avoids the two
    divergent copies that previously both carried the malformed-time crash.

    Inputs are typed widgets (checkbox / time / spin boxes) so booleans, times
    and thresholds can't be hand-typed into invalid shapes, but the persisted
    payload is still a plain ``str -> str`` dict keyed exactly as the settings
    table expects.
    """

    def __init__(self, services: dict[str, object], on_saved=None, parent=None):
        super().__init__(parent)
        self.services = services
        self.settings_service = services["settings_service"]
        self.on_saved = on_saved

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # --- 基础 -------------------------------------------------------
        self.default_country = QLineEdit()
        self.default_lang = QLineEdit()
        self.default_limit = QSpinBox()
        self.default_limit.setRange(1, 500)
        self.database_path = QLineEdit()

        basic_form = QFormLayout()
        basic_form.setHorizontalSpacing(16)
        basic_form.setVerticalSpacing(16)
        basic_form.addRow("默认国家", self.default_country)
        basic_form.addRow("默认语言", self.default_lang)
        basic_form.addRow("默认 limit", self.default_limit)
        basic_form.addRow("数据库路径", self.database_path)

        layout.addWidget(_section_label("基础"))
        layout.addLayout(basic_form)

        # --- 定时与网络 -------------------------------------------------
        self.scheduler_enabled = QCheckBox("启用定时任务")
        self.daily_sync_time = QTimeEdit()
        self.daily_sync_time.setDisplayFormat("HH:mm")
        self.request_delay = QDoubleSpinBox()
        self.request_delay.setRange(0.0, 10.0)
        self.request_delay.setSingleStep(0.5)
        self.proxy = QLineEdit()

        schedule_form = QFormLayout()
        schedule_form.setHorizontalSpacing(16)
        schedule_form.setVerticalSpacing(16)
        schedule_form.addRow("启用定时任务", self.scheduler_enabled)
        schedule_form.addRow("每日同步时间", self.daily_sync_time)
        schedule_form.addRow("请求延迟秒数", self.request_delay)
        schedule_form.addRow("代理", self.proxy)

        layout.addWidget(_section_label("定时与网络"))
        layout.addLayout(schedule_form)

        # --- 告警阈值 ---------------------------------------------------
        self.alert_rating_drop = QDoubleSpinBox()
        self.alert_rating_drop.setRange(0.0, 5.0)
        self.alert_rating_drop.setSingleStep(0.1)
        self.alert_growth_percent = QDoubleSpinBox()
        self.alert_growth_percent.setRange(0.0, 100.0)
        self.alert_growth_percent.setSingleStep(1.0)
        self.alert_keyword_top_band = QSpinBox()
        self.alert_keyword_top_band.setRange(1, 200)
        self.alert_keyword_move = QSpinBox()
        self.alert_keyword_move.setRange(1, 100)
        self.alert_fetch_escalate_after = QSpinBox()
        self.alert_fetch_escalate_after.setRange(1, 20)
        self.alert_negative_review_surge_percent = QDoubleSpinBox()
        self.alert_negative_review_surge_percent.setRange(0.0, 100.0)
        self.alert_negative_review_surge_percent.setSingleStep(1.0)
        self.alert_positive_ratio_drop = QDoubleSpinBox()
        self.alert_positive_ratio_drop.setRange(0.0, 100.0)
        self.alert_positive_ratio_drop.setSingleStep(1.0)

        alert_form = QFormLayout()
        alert_form.setHorizontalSpacing(16)
        alert_form.setVerticalSpacing(16)
        alert_form.addRow("评分下降阈值", self.alert_rating_drop)
        alert_form.addRow("增长告警(%)", self.alert_growth_percent)
        alert_form.addRow("关键词前N名", self.alert_keyword_top_band)
        alert_form.addRow("关键词移动名次", self.alert_keyword_move)
        alert_form.addRow("连续失败升级次数", self.alert_fetch_escalate_after)
        alert_form.addRow("差评激增(%)", self.alert_negative_review_surge_percent)
        alert_form.addRow("好评率下降(百分点)", self.alert_positive_ratio_drop)

        layout.addWidget(_section_label("告警阈值"))
        layout.addLayout(alert_form)

        # --- 通知 -------------------------------------------------------
        self.desktop_notifications = QCheckBox("启用桌面通知")
        self.notify_min_severity = QComboBox()
        # display label -> stored severity value
        self._severity_options = {"高": "high", "中": "medium", "低": "low"}
        self.notify_min_severity.addItems(self._severity_options.keys())

        notify_form = QFormLayout()
        notify_form.setHorizontalSpacing(16)
        notify_form.setVerticalSpacing(16)
        notify_form.addRow("桌面通知", self.desktop_notifications)
        notify_form.addRow("最低通知级别", self.notify_min_severity)

        layout.addWidget(_section_label("通知"))
        layout.addLayout(notify_form)

        # --- 历史数据 ---------------------------------------------------
        self.retention_enabled = QCheckBox("启用历史清理")
        self.snapshot_retention_days = QSpinBox()
        self.snapshot_retention_days.setRange(1, 3650)
        self.keyword_retention_days = QSpinBox()
        self.keyword_retention_days.setRange(1, 3650)
        self.alert_retention_days = QSpinBox()
        self.alert_retention_days.setRange(1, 3650)
        self.retention_min_keep = QSpinBox()
        self.retention_min_keep.setRange(1, 1000)
        self.review_retention_days = QSpinBox()
        self.review_retention_days.setRange(1, 3650)

        retention_form = QFormLayout()
        retention_form.setHorizontalSpacing(16)
        retention_form.setVerticalSpacing(16)
        retention_form.addRow("启用历史清理", self.retention_enabled)
        retention_form.addRow("快照保留天数", self.snapshot_retention_days)
        retention_form.addRow("关键词保留天数", self.keyword_retention_days)
        retention_form.addRow("告警保留天数", self.alert_retention_days)
        retention_form.addRow("评论保留天数", self.review_retention_days)
        retention_form.addRow("至少保留条数", self.retention_min_keep)

        layout.addWidget(_section_label("历史数据"))
        layout.addLayout(retention_form)

        # --- 评论监控 ---------------------------------------------------
        self.review_monitor_enabled = QCheckBox("同步时抓取评论")
        self.review_alert_max_rating = QSpinBox()
        self.review_alert_max_rating.setRange(1, 5)
        self.review_alert_min_count = QSpinBox()
        self.review_alert_min_count.setRange(1, 100)
        self.review_monitor_limit = QSpinBox()
        self.review_monitor_limit.setRange(1, 500)

        review_form = QFormLayout()
        review_form.setHorizontalSpacing(16)
        review_form.setVerticalSpacing(16)
        review_form.addRow("评论监控", self.review_monitor_enabled)
        review_form.addRow("差评星级阈值(<=)", self.review_alert_max_rating)
        review_form.addRow("新增差评告警条数", self.review_alert_min_count)
        review_form.addRow("每次抓取条数", self.review_monitor_limit)

        layout.addWidget(_section_label("评论监控"))
        layout.addLayout(review_form)

        self.save_button = QPushButton("保存设置")
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.clicked.connect(self.save)
        layout.addWidget(self.save_button)

        self.load()

    def load(self) -> None:
        values = self.settings_service.get_all()
        self.default_country.setText(values["default_country"])
        self.default_lang.setText(values["default_lang"])
        self.default_limit.setValue(self._as_int(values["default_limit"], "default_limit"))
        self.database_path.setText(values["database_path"])

        self.scheduler_enabled.setChecked(str(values["scheduler_enabled"]).strip().lower() == "true")
        parsed = parse_time_of_day(values["daily_sync_time"])
        self.daily_sync_time.setTime(QTime(parsed.hour, parsed.minute))
        self.request_delay.setValue(safe_float(values["request_delay_seconds"], 1.0))
        self.proxy.setText(values["proxy"])

        self.alert_rating_drop.setValue(
            safe_float(values["alert_rating_drop"], float(DEFAULT_SETTINGS["alert_rating_drop"]))
        )
        self.alert_growth_percent.setValue(
            safe_float(
                values["alert_growth_percent"], float(DEFAULT_SETTINGS["alert_growth_percent"])
            )
        )
        self.alert_keyword_top_band.setValue(
            self._as_int(values["alert_keyword_top_band"], "alert_keyword_top_band")
        )
        self.alert_keyword_move.setValue(
            self._as_int(values["alert_keyword_move"], "alert_keyword_move")
        )
        self.alert_fetch_escalate_after.setValue(
            self._as_int(values["alert_fetch_escalate_after"], "alert_fetch_escalate_after")
        )
        self.alert_negative_review_surge_percent.setValue(
            safe_float(
                values["alert_negative_review_surge_percent"],
                float(DEFAULT_SETTINGS["alert_negative_review_surge_percent"]),
            )
        )
        self.alert_positive_ratio_drop.setValue(
            safe_float(
                values["alert_positive_ratio_drop"],
                float(DEFAULT_SETTINGS["alert_positive_ratio_drop"]),
            )
        )

        self.desktop_notifications.setChecked(
            str(values["desktop_notifications"]).strip().lower() == "true"
        )
        severity = str(values["notify_min_severity"]).strip().lower()
        label = next((k for k, v in self._severity_options.items() if v == severity), "高")
        self.notify_min_severity.setCurrentText(label)

        self.retention_enabled.setChecked(
            str(values["retention_enabled"]).strip().lower() == "true"
        )
        self.snapshot_retention_days.setValue(
            self._as_int(values["snapshot_retention_days"], "snapshot_retention_days")
        )
        self.keyword_retention_days.setValue(
            self._as_int(values["keyword_retention_days"], "keyword_retention_days")
        )
        self.alert_retention_days.setValue(
            self._as_int(values["alert_retention_days"], "alert_retention_days")
        )
        self.retention_min_keep.setValue(
            self._as_int(values["retention_min_keep"], "retention_min_keep")
        )
        self.review_retention_days.setValue(
            self._as_int(values["review_retention_days"], "review_retention_days")
        )
        self.review_monitor_enabled.setChecked(
            str(values["review_monitor_enabled"]).strip().lower() == "true"
        )
        self.review_alert_max_rating.setValue(
            self._as_int(values["review_alert_max_rating"], "review_alert_max_rating")
        )
        self.review_alert_min_count.setValue(
            self._as_int(values["review_alert_min_count"], "review_alert_min_count")
        )
        self.review_monitor_limit.setValue(
            self._as_int(values["review_monitor_limit"], "review_monitor_limit")
        )

    @staticmethod
    def _as_int(value: str, key: str) -> int:
        """Parse an int setting, falling back to the shipped default for ``key``."""
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return int(float(DEFAULT_SETTINGS[key]))

    def save(self) -> None:
        sync_time = self.daily_sync_time.time().toString("HH:mm") or DEFAULT_SYNC_TIME
        if not is_valid_time_of_day(sync_time):
            show_error(self, "每日同步时间格式不正确，请使用 HH:MM（例如 09:00）。")
            return

        proxy_value = self.proxy.text().strip()
        request_delay = _format_float(self.request_delay.value())
        payload = {
            "default_country": self.default_country.text().strip() or "us",
            "default_lang": self.default_lang.text().strip() or "en",
            "default_limit": str(self.default_limit.value()),
            "scheduler_enabled": "true" if self.scheduler_enabled.isChecked() else "false",
            "daily_sync_time": sync_time,
            "request_delay_seconds": request_delay,
            "database_path": self.database_path.text().strip() or "./data/diandian_mini.sqlite3",
            "proxy": proxy_value,
            "alert_rating_drop": _format_float(self.alert_rating_drop.value()),
            "alert_growth_percent": _format_float(self.alert_growth_percent.value()),
            "alert_keyword_top_band": str(self.alert_keyword_top_band.value()),
            "alert_keyword_move": str(self.alert_keyword_move.value()),
            "alert_fetch_escalate_after": str(self.alert_fetch_escalate_after.value()),
            "alert_negative_review_surge_percent": _format_float(
                self.alert_negative_review_surge_percent.value()
            ),
            "alert_positive_ratio_drop": _format_float(self.alert_positive_ratio_drop.value()),
            "desktop_notifications": "true" if self.desktop_notifications.isChecked() else "false",
            "notify_min_severity": self._severity_options.get(
                self.notify_min_severity.currentText(), "high"
            ),
            "retention_enabled": "true" if self.retention_enabled.isChecked() else "false",
            "snapshot_retention_days": str(self.snapshot_retention_days.value()),
            "keyword_retention_days": str(self.keyword_retention_days.value()),
            "alert_retention_days": str(self.alert_retention_days.value()),
            "review_retention_days": str(self.review_retention_days.value()),
            "retention_min_keep": str(self.retention_min_keep.value()),
            "review_monitor_enabled": "true" if self.review_monitor_enabled.isChecked() else "false",
            "review_alert_max_rating": str(self.review_alert_max_rating.value()),
            "review_alert_min_count": str(self.review_alert_min_count.value()),
            "review_monitor_limit": str(self.review_monitor_limit.value()),
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
