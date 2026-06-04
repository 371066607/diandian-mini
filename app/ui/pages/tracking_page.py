from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout

from app.ui.pages.base_page import BasePage
from app.ui.widgets.app_table import AppTableWidget
from app.ui.widgets.settings_form import SettingsFormWidget


class TrackingPage(BasePage):
    def __init__(self, services, window_api, logger):
        super().__init__(services, window_api, logger, "监控", "管理本地监控任务，同步应用和关键词")
        self.tracking_service = services["tracking_service"]
        self.settings_service = services["settings_service"]
        self.keyword_service = services["keyword_service"]
        self.apps = []
        self.keywords = []
        self.active_table = "app"

        action_card, action_layout = self.create_card()
        self.app_id_input = self.create_input("com.whatsapp", width=260)
        self.country_input = self.create_input("us", width=90)
        self.lang_input = self.create_input("en", width=90)
        self.add_app_button = self.create_secondary_button("添加 App 监控")
        add_row = QHBoxLayout()
        add_row.setSpacing(12)
        add_row.addWidget(self.app_id_input)
        add_row.addWidget(self.country_input)
        add_row.addWidget(self.lang_input)
        add_row.addWidget(self.add_app_button)
        add_row.addStretch()
        action_layout.addLayout(add_row)

        self.sync_selected_button = self.create_primary_button("同步选中")
        self.sync_all_button = self.create_secondary_button("同步全部")
        self.remove_button = self.create_secondary_button("删除监控")
        self.toggle_button = self.create_secondary_button("启用/禁用")
        buttons_row = self.create_actions_row(
            [
                self.sync_selected_button,
                self.sync_all_button,
                self.remove_button,
                self.toggle_button,
            ]
        )
        action_layout.addLayout(buttons_row)
        self.root_layout.addWidget(action_card)

        content_row = QHBoxLayout()
        content_row.setSpacing(20)
        left_column = QVBoxLayout()
        left_column.setSpacing(20)

        upper_card, upper_layout = self.create_card("App 监控")
        self.apps_table = AppTableWidget(
            [
                ("App", "title"),
                ("包名", "app_id"),
                ("国家", "country"),
                ("频率", "frequency"),
                ("上次同步", "last_synced_at"),
                ("状态", "enabled"),
            ]
        )
        upper_layout.addWidget(self.apps_table)
        left_column.addWidget(upper_card)

        lower_card, lower_layout = self.create_card("关键词监控")
        self.keywords_table = AppTableWidget(
            [
                ("关键词", "keyword"),
                ("App", "app_id"),
                ("排名", "rank"),
                ("国家", "country"),
                ("频率", "frequency"),
                ("上次同步", "last_synced_at"),
                ("状态", "enabled"),
            ]
        )
        lower_layout.addWidget(self.keywords_table)
        left_column.addWidget(lower_card)

        settings_card, settings_layout = self.create_card("设置")
        self.settings_form = SettingsFormWidget(services, on_saved=self.refresh)
        settings_layout.addWidget(self.settings_form)
        settings_card.setFixedWidth(430)

        content_row.addLayout(left_column, 3)
        content_row.addWidget(settings_card, 2)
        self.root_layout.addLayout(content_row)

        self.add_app_button.clicked.connect(self.add_app_tracking)
        self.app_id_input.returnPressed.connect(self.add_app_tracking)
        self.sync_selected_button.clicked.connect(self.sync_selected)
        self.sync_all_button.clicked.connect(self.sync_all)
        self.remove_button.clicked.connect(self.remove_selected)
        self.toggle_button.clicked.connect(self.toggle_selected)
        self.apps_table.itemSelectionChanged.connect(lambda: self._set_active_table("app"))
        self.keywords_table.itemSelectionChanged.connect(lambda: self._set_active_table("keyword"))

    def on_activated(self) -> None:
        self.settings_form.load()
        self.refresh()

    def refresh(self) -> None:
        self.run_background(self._collect_tracking_data, self._apply_tracking_data)

    def _collect_tracking_data(self) -> dict:
        apps = self.tracking_service.list_apps()
        keywords = self.tracking_service.list_keywords()
        settings = self.settings_service.get_all()
        return {
            "apps": apps,
            "keywords": keywords,
            "default_country": settings["default_country"],
            "default_lang": settings["default_lang"],
            "apps_rows": [
                {
                    "title": item.title or item.app_id,
                    "app_id": item.app_id,
                    "country": item.country,
                    "frequency": item.frequency,
                    "last_synced_at": item.last_synced_at or "未同步",
                    "enabled": "启用" if item.enabled else "禁用",
                }
                for item in apps
            ],
            "keywords_rows": [
                {
                    "keyword": item.keyword,
                    "app_id": item.app_id,
                    "rank": self._rank_label(item),
                    "country": item.country,
                    "frequency": item.frequency,
                    "last_synced_at": item.last_synced_at or "未同步",
                    "enabled": "启用" if item.enabled else "禁用",
                }
                for item in keywords
            ],
        }

    def _rank_label(self, item) -> str:
        snapshot = self.keyword_service.latest_rank(
            item.keyword, item.app_id, item.country, item.lang
        )
        if snapshot is None:
            return "未同步"
        if not snapshot.found or snapshot.rank is None:
            return "未命中"
        return f"#{snapshot.rank}"

    def _apply_tracking_data(self, data: dict) -> None:
        self.apps = data["apps"]
        self.keywords = data["keywords"]
        self.country_input.setText(data["default_country"])
        self.lang_input.setText(data["default_lang"])
        self.apps_table.set_rows(data["apps_rows"])
        self.keywords_table.set_rows(data["keywords_rows"])

    def add_app_tracking(self) -> None:
        app_id = self.app_id_input.text().strip()
        if not app_id:
            self.show_error("请输入要监控的包名。")
            return
        country = self.country_input.text().strip() or "us"
        lang = self.lang_input.text().strip() or "en"
        self.run_task(
            "正在添加 App 监控...",
            lambda: self.tracking_service.add_app(app_id, country=country, lang=lang),
            lambda _: (self.show_status("已添加 App 监控。"), self.refresh()),
        )

    def sync_selected(self) -> None:
        target = self._selected_target()
        if target is None:
            self.show_error("请先选择要同步的应用或关键词。")
            return
        if target[0] == "app":
            row = target[1]
            self.run_task(
                "正在同步选中应用...",
                lambda: self.tracking_service.sync_app_now(row.app_id, row.country, row.lang),
                lambda _: (self.show_status("应用同步完成。"), self.refresh()),
            )
            return
        row = target[1]
        self.run_task(
            "正在同步选中关键词...",
            lambda: self.tracking_service.sync_keyword_now(
                row.keyword,
                row.app_id,
                row.country,
                row.lang,
            ),
            lambda result: (
                self.show_status(
                    f"关键词同步完成，当前排名 {result.rank if result.rank is not None else '未命中'}。"
                ),
                self.refresh(),
            ),
        )

    def sync_all(self) -> None:
        self.run_task(
            "正在同步全部监控项...",
            self.tracking_service.sync_all,
            lambda result: (
                self.show_status(f"已同步 {result['apps']} 个应用，{result['keywords']} 个关键词。"),
                self.refresh(),
            ),
        )

    def remove_selected(self) -> None:
        target = self._selected_target()
        if target is None:
            self.show_error("请先选择要删除的应用或关键词。")
            return
        if target[0] == "app":
            row = target[1]
            self.run_task(
                "正在删除应用监控...",
                lambda: self.tracking_service.remove_app(row.app_id, row.country, row.lang),
                lambda _: (self.show_status("已删除应用监控。"), self.refresh()),
            )
            return
        row = target[1]
        self.run_task(
            "正在删除关键词监控...",
            lambda: self.tracking_service.remove_keyword(
                row.keyword,
                row.app_id,
                row.country,
                row.lang,
            ),
            lambda _: (self.show_status("已删除关键词监控。"), self.refresh()),
        )

    def toggle_selected(self) -> None:
        target = self._selected_target()
        if target is None:
            self.show_error("请先选择要启用/禁用的应用或关键词。")
            return
        if target[0] == "app":
            row = target[1]
            self.run_task(
                "正在切换应用监控状态...",
                lambda: self.tracking_service.toggle_app(row.app_id, row.country, row.lang),
                lambda enabled: (
                    self.show_status(f"应用监控已{'启用' if enabled else '禁用'}。"),
                    self.refresh(),
                ),
            )
            return
        row = target[1]
        self.run_task(
            "正在切换关键词监控状态...",
            lambda: self.tracking_service.toggle_keyword(
                row.keyword,
                row.app_id,
                row.country,
                row.lang,
            ),
            lambda enabled: (
                self.show_status(f"关键词监控已{'启用' if enabled else '禁用'}。"),
                self.refresh(),
            ),
        )

    def _selected_target(self):
        if self.active_table == "keyword":
            row = self.keywords_table.current_row_data(self.keywords)
            if row is not None:
                return ("keyword", row)
        row = self.apps_table.current_row_data(self.apps)
        if self.active_table == "app" and row is not None:
            return ("app", row)
        row = self.keywords_table.current_row_data(self.keywords)
        if row is not None:
            return ("keyword", row)
        row = self.apps_table.current_row_data(self.apps)
        if row is not None:
            return ("app", row)
        return None

    def _set_active_table(self, value: str) -> None:
        self.active_table = value
