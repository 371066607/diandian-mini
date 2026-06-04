from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QLabel, QHBoxLayout

from app.db.repositories import KeywordRankRepository, SnapshotRepository
from app.schemas.app_schema import AppDetail
from app.ui.pages.base_page import BasePage
from app.ui.widgets.app_table import AppTableWidget
from app.ui.widgets.chart_widget import ChartWidget


class DashboardPage(BasePage):
    def __init__(self, services, window_api, logger):
        super().__init__(services, window_api, logger, "首页 Dashboard", "本地监控总览、趋势和提醒")
        self.snapshot_repository = SnapshotRepository()
        self.keyword_rank_repository = KeywordRankRepository()
        self.monetization_service = services["monetization_service"]

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
        for index, (key, title, value) in enumerate(stats):
            card, layout = self.create_card(title)
            number = self.create_stat_value(value)
            sub = QLabel("等待本地数据")
            sub.setStyleSheet("font-size: 12px; color: #64748B;")
            layout.addWidget(number)
            layout.addWidget(sub)
            self.stat_labels[key] = number
            self.stat_sub_labels[key] = sub
            stats_grid.addWidget(card, index // 4, index % 4)
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
        alerts_header.addStretch()
        self.mark_read_button = self.create_secondary_button("标记全部已读")
        self.mark_read_button.clicked.connect(self.mark_alerts_read)
        alerts_header.addWidget(self.mark_read_button)
        alerts_layout.addLayout(alerts_header)
        self.alerts_table = AppTableWidget(
            [("时间", "created_at"), ("类型", "type"), ("App", "app_id"), ("内容", "message")]
        )
        alerts_layout.addWidget(self.alerts_table)
        changes_card, changes_layout = self.create_card("最近变化 App")
        self.changes_table = AppTableWidget(
            [
                ("App", "title"),
                ("评分", "rating"),
                ("评论数", "reviews_count"),
                ("安装量", "installs"),
                ("商业化", "monetization"),
            ]
        )
        changes_layout.addWidget(self.changes_table)
        tables_row.addWidget(alerts_card)
        tables_row.addWidget(changes_card)
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
            recent_keyword_ranks = list(
                reversed(self.keyword_rank_repository.list_recent(session, limit=8))
            )

        unread = alert_service.unread_count()
        latest_keyword_sync = next(
            (item.last_synced_at for item in tracked_keywords if item.last_synced_at),
            None,
        )
        alerts = alert_service.recent_alerts(limit=8)
        alerts_rows = [
            {
                "created_at": alert.created_at,
                "type": alert.type,
                "app_id": alert.app_id,
                "message": alert.message,
            }
            for alert in alerts
        ]

        change_rows = []
        for item in recent_snapshots:
            detail = AppDetail(
                app_id=item.app_id,
                title=item.title,
                rating=item.rating,
                ratings_count=item.ratings_count,
                reviews_count=item.reviews_count,
                installs=item.installs,
                min_installs=item.min_installs,
                price=item.price,
                free=bool(item.free) if item.free is not None else None,
                has_iap=bool(item.has_iap) if item.has_iap is not None else None,
            )
            score = self.monetization_service.score(detail)
            change_rows.append(
                {
                    "title": item.title or item.app_id,
                    "rating": item.rating,
                    "reviews_count": item.reviews_count,
                    "installs": item.installs,
                    "monetization": self._score_level_label(score["level"]),
                }
            )

        return {
            "tracked_apps_count": len(tracked_apps),
            "enabled_apps": sum(1 for item in tracked_apps if item.enabled),
            "tracked_keywords_count": len(tracked_keywords),
            "snapshots": snapshots,
            "unread": unread,
            "latest_sync": self._latest_sync_time(tracked_apps, tracked_keywords) or "-",
            "snapshots_sub": recent_snapshots[-1].captured_at
            if recent_snapshots
            else "SQLite 本地数据",
            "latest_keyword_sync": latest_keyword_sync or "等待首次同步",
            "alerts_sub": "评分下降 / 版本变化" if unread else "暂无未读提醒",
            "alerts_rows": alerts_rows,
            "change_rows": change_rows,
            "rating_labels": [item.captured_at[5:10] for item in recent_snapshots],
            "rating_values": [item.rating or 0 for item in recent_snapshots],
            "keyword_labels": [item.captured_at[5:10] for item in recent_keyword_ranks],
            "keyword_values": [
                item.rank or item.checked_limit or 0 for item in recent_keyword_ranks
            ],
        }

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
        self.changes_table.set_rows(data["change_rows"])
        self.rating_chart.set_series(data["rating_labels"], data["rating_values"])
        self.keyword_chart.set_series(data["keyword_labels"], data["keyword_values"])

    def _score_level_label(self, level: str) -> str:
        mapping = {
            "very_high": "很高",
            "high": "高",
            "medium": "中",
            "low": "低",
        }
        return mapping.get(level, level)

    def _latest_sync_time(self, tracked_apps, tracked_keywords) -> str | None:
        values = [
            item.last_synced_at
            for item in [*tracked_apps, *tracked_keywords]
            if getattr(item, "last_synced_at", None)
        ]
        return max(values) if values else None
