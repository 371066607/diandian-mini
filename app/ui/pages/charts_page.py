from __future__ import annotations

from app.ui.pages.base_page import BasePage
from app.ui.widgets.app_table import AppTableWidget
from app.utils.image_loader import fetch_images
from app.utils.normalize import safe_int


class ChartsPage(BasePage):
    def __init__(self, services, window_api, logger):
        super().__init__(services, window_api, logger, "榜单", "Top Free / Paid / Grossing 榜单抓取")
        self.chart_service = services["chart_service"]
        self.current_items = []
        self._chart_gen = 0
        defaults = self.get_default_settings()

        controls_card, controls_layout = self.create_card()
        self.chart_type_input = self.create_input("chart_type: top_free", width=180)
        self.chart_type_input.setText("top_free")
        self.category_input = self.create_input("category: ", width=180)
        self.country_input = self.create_input("country: us", width=120)
        self.country_input.setText(defaults["default_country"])
        self.lang_input = self.create_input("lang: en", width=120)
        self.lang_input.setText(defaults["default_lang"])
        self.limit_input = self.create_input("limit: 100", width=120)
        self.limit_input.setText(defaults["default_limit"])
        self.fetch_button = self.create_primary_button("获取榜单")
        self.save_button = self.create_secondary_button("保存榜单快照")
        self.detail_button = self.create_secondary_button("打开详情")

        row = self.create_actions_row(
            [
                self.chart_type_input,
                self.category_input,
                self.country_input,
                self.lang_input,
                self.limit_input,
                self.fetch_button,
                self.save_button,
                self.detail_button,
            ]
        )
        controls_layout.addLayout(row)
        self.root_layout.addWidget(controls_card)

        table_card, table_layout = self.create_card("榜单结果")
        self.table = AppTableWidget(
            [
                ("icon", "icon"),
                ("rank", "rank"),
                ("title", "title"),
                ("app_id", "app_id"),
                ("developer", "developer"),
                ("rating", "rating"),
                ("installs", "installs"),
            ]
        )
        table_layout.addWidget(self.table)
        self.root_layout.addWidget(table_card)

        self.fetch_button.clicked.connect(self.fetch_chart)
        self.save_button.clicked.connect(self.save_chart)
        self.detail_button.clicked.connect(self.open_detail)
        self.chart_type_input.returnPressed.connect(self.fetch_chart)
        self.limit_input.returnPressed.connect(self.fetch_chart)
        self.table.itemDoubleClicked.connect(lambda *_: self.open_detail())

    def on_platform_changed(self, platform: str) -> None:
        label = "App Store" if platform == "app_store" else "Google Play"
        self.update_subtitle(f"{label} Top Free / Paid / Grossing 榜单抓取")

    def fetch_chart(self) -> None:
        chart_type = self.chart_type_input.text().strip() or "top_free"
        category = self.category_input.text().strip() or None
        country = self.country_input.text().strip() or "us"
        lang = self.lang_input.text().strip() or "en"
        limit = safe_int(self.limit_input.text(), 100)
        platform = getattr(self.window_api, "current_platform", "google_play")
        self.run_task(
            "正在获取榜单...",
            lambda: self.chart_service.fetch(chart_type, category, country, lang, limit, platform=platform),
            self._on_chart_finished,
        )

    def _on_chart_finished(self, items) -> None:
        # Render the ranking immediately; icons stream in afterwards.
        self.current_items = items
        self._chart_gen += 1
        self.table.set_rows(items)
        head = items[: min(len(items), 12)]
        if not head:
            return
        gen = self._chart_gen
        urls = [item.icon_url for item in head]
        self.run_background(
            lambda: fetch_images(urls, timeout=6.0, thumbnail_size=96),
            lambda icons: self._apply_icons(gen, head, icons),
        )

    def _apply_icons(self, gen: int, head, icons) -> None:
        if gen != self._chart_gen:
            return
        for item, icon in zip(head, icons, strict=True):
            item.raw["_icon_bytes"] = icon
        self.table.set_rows(self.current_items)

    def save_chart(self) -> None:
        if not self.current_items:
            self.show_error("请先获取榜单。")
            return
        chart_type = self.chart_type_input.text().strip() or "top_free"
        category = self.category_input.text().strip() or None
        country = self.country_input.text().strip() or "us"
        lang = self.lang_input.text().strip() or "en"
        self.run_task(
            "正在保存榜单快照...",
            lambda: self.chart_service.save(
                chart_type,
                category,
                country,
                lang,
                self.current_items,
            ),
            lambda count: self.show_status(f"已保存 {count} 条榜单快照"),
        )

    def open_detail(self) -> None:
        row = self.table.current_row_data(self.current_items)
        if row is None:
            self.show_error("请先选择一条榜单记录。")
            return
        self.window_api.open_app_detail(row.app_id)
