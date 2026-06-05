from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout

from app.ui.alert_labels import (
    ALERT_SEVERITY_COLORS,
    ALERT_SEVERITY_FILTERS,
    ALERT_TYPE_LABELS,
    alert_severity_label,
    alert_type_label,
)
from app.ui.pages.base_page import BasePage
from app.ui.widgets.app_table import AppTableWidget

# Read-status dropdown: label -> stored is_read value. None = no filter; 0 / 1 are
# explicit and must not collapse into None ("未读" filters is_read=0, not "any").
_READ_FILTERS: dict[str, int | None] = {"全部": None, "未读": 0, "已读": 1}


class AlertsPage(BasePage):
    def __init__(self, services, window_api, logger):
        super().__init__(services, window_api, logger, "提醒", "全部监控告警与筛选")
        self.alert_service = services["alert_service"]
        self._rows: list[dict] = []

        filter_card, filter_layout = self.create_card("筛选")
        filters_row = QHBoxLayout()
        filters_row.setSpacing(12)

        # App dropdown ("全部 App" + each app_id). Filled in on_activated so the list
        # reflects whatever apps currently have alerts.
        self.app_filter = QComboBox()
        self.app_filter.addItem("全部 App", None)
        self.app_filter.currentIndexChanged.connect(lambda _: self.refresh())

        # Type dropdown: Chinese label shown, raw type stored as the item's data.
        self.type_filter = QComboBox()
        self.type_filter.addItem("全部类型", None)
        for raw_type, label in ALERT_TYPE_LABELS.items():
            self.type_filter.addItem(label, raw_type)
        self.type_filter.currentIndexChanged.connect(lambda _: self.refresh())

        # Severity dropdown uses the shared label->severity map (含「全部级别」=None).
        self.severity_filter = QComboBox()
        self.severity_filter.addItems(ALERT_SEVERITY_FILTERS.keys())
        self.severity_filter.currentTextChanged.connect(lambda _: self.refresh())

        # Read-status dropdown (全部 / 未读 / 已读 -> None / 0 / 1).
        self.read_filter = QComboBox()
        self.read_filter.addItems(_READ_FILTERS.keys())
        self.read_filter.currentTextChanged.connect(lambda _: self.refresh())

        filters_row.addWidget(self.app_filter)
        filters_row.addWidget(self.type_filter)
        filters_row.addWidget(self.severity_filter)
        filters_row.addWidget(self.read_filter)

        refresh_button = self.create_secondary_button("刷新")
        refresh_button.clicked.connect(self.refresh)
        mark_selected_button = self.create_secondary_button("标记选中已读")
        mark_selected_button.clicked.connect(self.mark_selected_read)
        mark_all_button = self.create_secondary_button("标记全部已读")
        mark_all_button.clicked.connect(self.mark_all_read)
        filters_row.addWidget(refresh_button)
        filters_row.addWidget(mark_selected_button)
        filters_row.addWidget(mark_all_button)
        filters_row.addStretch()

        filter_layout.addLayout(filters_row)
        self.root_layout.addWidget(filter_card)

        table_card, table_layout = self.create_card("告警列表")
        self.table = AppTableWidget(
            [
                ("时间", "created_at"),
                ("级别", "severity"),
                ("类型", "type"),
                ("App", "app_id"),
                ("内容", "message"),
            ],
            row_tint=self._row_tint,
        )
        self.table.itemDoubleClicked.connect(self._on_row_double_clicked)
        table_layout.addWidget(self.table)
        self.root_layout.addWidget(table_card, 1)

    def on_activated(self) -> None:
        self._reload_app_filter()
        self.refresh()

    def _reload_app_filter(self) -> None:
        def collect():
            return self.alert_service.distinct_alert_apps()

        self.run_background(collect, self._apply_app_filter)

    def _apply_app_filter(self, app_ids: list[str]) -> None:
        current = self.app_filter.currentData()
        self.app_filter.blockSignals(True)
        self.app_filter.clear()
        self.app_filter.addItem("全部 App", None)
        for app_id in app_ids:
            self.app_filter.addItem(app_id, app_id)
        # Restore the prior selection if it still exists.
        if current is not None:
            index = self.app_filter.findData(current)
            if index >= 0:
                self.app_filter.setCurrentIndex(index)
        self.app_filter.blockSignals(False)

    def refresh(self) -> None:
        app_id = self.app_filter.currentData()
        alert_type = self.type_filter.currentData()
        severity = ALERT_SEVERITY_FILTERS.get(self.severity_filter.currentText())
        is_read = _READ_FILTERS.get(self.read_filter.currentText())

        def collect():
            alerts = self.alert_service.list_alerts(
                app_id=app_id,
                alert_type=alert_type,
                severity=severity,
                is_read=is_read,
                limit=200,
            )
            return [
                {
                    "id": alert.id,
                    "created_at": self._short_time(alert.created_at),
                    "severity": alert_severity_label(alert.severity),
                    "severity_raw": alert.severity,
                    "type": alert_type_label(alert.type),
                    "app_id": alert.app_id,
                    "message": alert.message,
                }
                for alert in alerts
            ]

        self.run_background(collect, self._apply_rows)

    def _apply_rows(self, rows: list[dict]) -> None:
        self._rows = rows
        self.table.set_rows(rows)

    def mark_selected_read(self) -> None:
        row = self.table.current_row_data(self._rows)
        if not row or row.get("id") is None:
            self.show_status("未选中任何告警")
            return
        alert_id = row["id"]

        def do_mark():
            return self.alert_service.mark_read([alert_id])

        self.run_background(do_mark, lambda count: self._after_mark(count))

    def mark_all_read(self) -> None:
        self.run_background(
            self.alert_service.mark_all_read,
            lambda count: self._after_mark(count),
        )

    def _after_mark(self, count: int) -> None:
        self.show_status(f"已标记 {count} 条为已读")
        self.refresh()

    def _on_row_double_clicked(self, _item) -> None:
        row = self.table.current_row_data(self._rows)
        if row and row.get("app_id"):
            self.window_api.open_app_detail(row["app_id"])

    @staticmethod
    def _short_time(created_at: str) -> str:
        # "2026-06-04T12:53:35" -> "06-04 12:53"
        return (created_at or "")[5:16].replace("T", " ")

    @staticmethod
    def _row_tint(row: dict) -> str | None:
        return ALERT_SEVERITY_COLORS.get(row.get("severity_raw"))
