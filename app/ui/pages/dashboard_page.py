from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QWidget,
)

from app.db.repositories import KeywordRankRepository, SnapshotRepository
from app.ui.alert_labels import (
    ALERT_SEVERITY_COLORS,
    ALERT_SEVERITY_FILTERS,
    ALERT_SEVERITY_LABELS,
    ALERT_TYPE_LABELS,
)
from app.ui.pages.base_page import BasePage
from app.ui.widgets.app_table import AppTableWidget
from app.ui.widgets.chart_widget import ChartWidget
from app.ui.widgets.monitor_card import MonitorCard


class DashboardPage(BasePage):
    def __init__(self, services, window_api, logger):
        super().__init__(services, window_api, logger, "首页 Dashboard", "本地监控总览、趋势和提醒")
        self.snapshot_repository = SnapshotRepository()
        self.keyword_rank_repository = KeywordRankRepository()

        stats_grid = QGridLayout()
        stats_grid.setHorizontalSpacing(18)
        stats_grid.setVerticalSpacing(18)
        self.stat_labels: dict[str, QLabel] = {}
        self.stat_sub_labels: dict[str, QLabel] = {}
        stats = [
            ("tracked_apps", "监控 App", "0"),
            ("snapshots", "历史快照", "0"),
            ("tracked_keywords", "关键词监控", "0"),
            ("alerts", "未读提醒", "0"),
            ("last_sync", "最后同步", "-"),
        ]
        stats_columns = 5
        for index, (key, title, value) in enumerate(stats):
            card, layout = self.create_card(title)
            number = self.create_stat_value(value)
            sub = QLabel("等待本地数据")
            sub.setStyleSheet("font-size: 12px; color: #64748B;")
            layout.addWidget(number)
            layout.addWidget(sub)
            self.stat_labels[key] = number
            self.stat_sub_labels[key] = sub
            stats_grid.addWidget(card, index // stats_columns, index % stats_columns)
        self.root_layout.addLayout(stats_grid)

        charts_row = QHBoxLayout()
        dashboard_card, dashboard_layout = self.create_card("评分 / 评论趋势")
        self.rating_chart = ChartWidget("最近 30 天")
        dashboard_layout.addWidget(self.rating_chart)
        keyword_card, keyword_layout = self.create_card("关键词排名变化")
        self.keyword_chart = ChartWidget("数值越低排名越靠前")
        keyword_layout.addWidget(self.keyword_chart)
        charts_row.addWidget(dashboard_card)
        charts_row.addWidget(keyword_card)
        self.root_layout.addLayout(charts_row)

        tables_row = QHBoxLayout()
        alerts_card, alerts_layout = self.create_card("最近提醒")
        alerts_header = QHBoxLayout()
        self.severity_filter = QComboBox()
        self.severity_filter.addItems(ALERT_SEVERITY_FILTERS.keys())
        self.severity_filter.currentTextChanged.connect(lambda _: self.refresh())
        alerts_header.addWidget(self.severity_filter)
        alerts_header.addStretch()
        self.mark_read_button = self.create_secondary_button("标记全部已读")
        self.mark_read_button.clicked.connect(self.mark_alerts_read)
        alerts_header.addWidget(self.mark_read_button)
        alerts_layout.addLayout(alerts_header)
        self.alerts_table = AppTableWidget(
            [
                ("时间", "created_at"),
                ("级别", "severity"),
                ("类型", "type"),
                ("App", "app_id"),
                ("内容", "message"),
            ],
            row_tint=self._alert_row_tint,
        )
        alerts_layout.addWidget(self.alerts_table)
        self.alerts_empty_label = QLabel("暂无提醒")
        self.alerts_empty_label.setStyleSheet("font-size: 13px; color: #94A3B8;")
        self.alerts_empty_label.hide()
        alerts_layout.addWidget(self.alerts_empty_label)
        health_card, health_layout = self.create_card("监控健康")
        health_scroll = QScrollArea()
        health_scroll.setWidgetResizable(True)
        health_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.health_container = QWidget()
        self.health_grid = QGridLayout(self.health_container)
        self.health_grid.setHorizontalSpacing(12)
        self.health_grid.setVerticalSpacing(12)
        self.health_grid.setContentsMargins(0, 0, 0, 0)
        self.health_grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        health_scroll.setWidget(self.health_container)
        health_layout.addWidget(health_scroll)
        self.health_empty_label = QLabel("暂无监控 App，去『监控』页添加")
        self.health_empty_label.setStyleSheet("font-size: 13px; color: #94A3B8;")
        self.health_empty_label.hide()
        health_layout.addWidget(self.health_empty_label)
        tables_row.addWidget(alerts_card)
        tables_row.addWidget(health_card)
        self.root_layout.addLayout(tables_row)

    def on_activated(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        self.run_background(self._collect_dashboard_data, self._apply_dashboard_data)

    def mark_alerts_read(self) -> None:
        self.run_background(
            self.services["alert_service"].mark_all_read,
            lambda _: self.refresh(),
        )

    def _collect_dashboard_data(self) -> dict:
        tracking_service = self.services["tracking_service"]
        alert_service = self.services["alert_service"]
        tracked_apps = tracking_service.list_apps()
        tracked_keywords = tracking_service.list_keywords()
        with self.window_api.database.session() as session:
            snapshots = self.snapshot_repository.count(session)
            recent_snapshots = list(
                reversed(self.snapshot_repository.list_recent(session, limit=8))
            )
            # Pick the most-recently-synced keyword, then chart ITS rank history — the
            # old code mixed different keywords' ranks (and "未命中" checked_limits) into
            # one meaningless line, so you couldn't tell which keyword it was.
            latest_kw = self.keyword_rank_repository.list_recent(session, limit=1)
            if latest_kw:
                top = latest_kw[0]
                keyword_name = top.keyword
                keyword_history = self.keyword_rank_repository.history(
                    session, top.keyword, top.app_id, top.country, top.lang
                )
            else:
                keyword_name = None
                keyword_history = []

        unread = alert_service.unread_count()
        latest_keyword_sync = next(
            (item.last_synced_at for item in tracked_keywords if item.last_synced_at),
            None,
        )
        severity_filter = ALERT_SEVERITY_FILTERS.get(self.severity_filter.currentText())
        alerts = alert_service.recent_alerts(limit=8, severity=severity_filter)
        alerts_rows = [
            {
                "created_at": self._short_time(alert.created_at),
                "severity": ALERT_SEVERITY_LABELS.get(alert.severity, alert.severity),
                "severity_raw": alert.severity,
                "type": ALERT_TYPE_LABELS.get(alert.type, alert.type),
                "app_id": alert.app_id,
                "message": alert.message,
            }
            for alert in alerts
        ]

        monitor_health = tracking_service.monitor_overview()

        return {
            "tracked_apps_count": len(tracked_apps),
            "enabled_apps": sum(1 for item in tracked_apps if item.enabled),
            "tracked_keywords_count": len(tracked_keywords),
            "snapshots": snapshots,
            "unread": unread,
            "latest_sync": self._short_time(self._latest_sync_time(tracked_apps, tracked_keywords)) if self._latest_sync_time(tracked_apps, tracked_keywords) else "-",
            "snapshots_sub": self._short_time(recent_snapshots[-1].captured_at)
            if recent_snapshots
            else "SQLite 本地数据",
            "latest_keyword_sync": self._short_time(latest_keyword_sync) if latest_keyword_sync else "等待首次同步",
            "alerts_sub": "评分 / 版本 / 排名变化" if unread else "暂无未读提醒",
            "alerts_rows": alerts_rows,
            "monitor_health": monitor_health,
            "rating_labels": [self._short_time(item.captured_at) for item in recent_snapshots],
            "rating_values": [item.rating or 0 for item in recent_snapshots],
            "keyword_name": keyword_name,
            "keyword_labels": [self._short_time(item.captured_at) for item in keyword_history],
            "keyword_values": [item.rank or item.checked_limit or 0 for item in keyword_history],
        }

    @staticmethod
    def _short_time(captured_at: str) -> str:
        # "2026-06-04T12:53:35" -> "06-04 12:53" so same-day points are distinguishable
        return captured_at[5:16].replace("T", " ")

    @staticmethod
    def _alert_row_tint(row: dict) -> str | None:
        return ALERT_SEVERITY_COLORS.get(row.get("severity_raw"))

    def _apply_dashboard_data(self, data: dict) -> None:
        self.stat_labels["tracked_apps"].setText(str(data["tracked_apps_count"]))
        self.stat_labels["tracked_keywords"].setText(str(data["tracked_keywords_count"]))
        self.stat_labels["snapshots"].setText(str(data["snapshots"]))
        self.stat_labels["alerts"].setText(str(data["unread"]))
        self.stat_labels["last_sync"].setText(data["latest_sync"])
        self.stat_sub_labels["tracked_apps"].setText(f"启用 {data['enabled_apps']}")
        self.stat_sub_labels["snapshots"].setText(data["snapshots_sub"])
        self.stat_sub_labels["tracked_keywords"].setText(data["latest_keyword_sync"])
        self.stat_sub_labels["alerts"].setText(data["alerts_sub"])
        self.stat_sub_labels["last_sync"].setText("最近成功同步时间")
        self.alerts_table.set_rows(data["alerts_rows"])
        self.alerts_empty_label.setVisible(not data["alerts_rows"])
        self._render_monitor_cards(data["monitor_health"])
        self.rating_chart.set_series(data["rating_labels"], data["rating_values"])
        keyword_name = data.get("keyword_name")
        self.keyword_chart.title = (
            f"关键词「{keyword_name}」排名（越低越靠前）" if keyword_name else "数值越低排名越靠前"
        )
        self.keyword_chart.set_series(data["keyword_labels"], data["keyword_values"])

    def _render_monitor_cards(self, health_items: list) -> None:
        """Clear and rebuild the monitor-health card grid (2 cards per row)."""
        while self.health_grid.count():
            item = self.health_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.health_empty_label.setVisible(not health_items)
        columns = 2
        for index, health in enumerate(health_items):
            card = MonitorCard(health, self.window_api.open_app_detail)
            self.health_grid.addWidget(card, index // columns, index % columns)

    def _latest_sync_time(self, tracked_apps, tracked_keywords) -> str | None:
        values = [
            item.last_synced_at
            for item in [*tracked_apps, *tracked_keywords]
            if getattr(item, "last_synced_at", None)
        ]
        return max(values) if values else None
