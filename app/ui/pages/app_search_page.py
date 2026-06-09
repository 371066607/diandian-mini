from __future__ import annotations

from app.ui.pages.base_page import BasePage
from app.ui.widgets.app_table import AppTableWidget
from app.utils.image_loader import fetch_images
from app.utils.normalize import safe_int


class AppSearchPage(BasePage):
    def __init__(self, services, window_api, logger):
        super().__init__(services, window_api, logger, "应用搜索", "按关键词搜索 Google Play 应用")
        self.google_play_service = services["google_play_service"]
        self.tracking_service = services["tracking_service"]
        self.search_results = []
        self._search_gen = 0
        defaults = self.get_default_settings()

        controls_card, controls_layout = self.create_card()
        self.keyword_input = self.create_input("keyword: photo editor")
        self.country_input = self.create_input("country: us", width=140)
        self.country_input.setText(defaults["default_country"])
        self.lang_input = self.create_input("lang: en", width=120)
        self.lang_input.setText(defaults["default_lang"])
        self.limit_input = self.create_input("limit: 50", width=120)
        self.limit_input.setText(defaults["default_limit"])
        self.search_button = self.create_primary_button("搜索")
        self.detail_button = self.create_secondary_button("打开详情")
        self.track_button = self.create_secondary_button("加入监控")

        row = self.create_actions_row(
            [
                self.keyword_input,
                self.country_input,
                self.lang_input,
                self.limit_input,
                self.search_button,
                self.detail_button,
                self.track_button,
            ]
        )
        controls_layout.addLayout(row)
        self.root_layout.addWidget(controls_card)

        result_card, result_layout = self.create_card("搜索结果")
        self.table = AppTableWidget(
            [
                ("图标", "icon"),
                ("应用名", "title"),
                ("包名", "app_id"),
                ("开发者", "developer"),
                ("评分", "rating"),
                ("评分数", "ratings_count"),
                ("安装量", "installs"),
                ("价格", "price"),
                ("内购", "has_iap"),
            ]
        )
        result_layout.addWidget(self.table)
        self.root_layout.addWidget(result_card)

        self.search_button.clicked.connect(self.search_apps)
        self.detail_button.clicked.connect(self.open_detail)
        self.track_button.clicked.connect(self.add_tracking)
        self.keyword_input.returnPressed.connect(self.search_apps)
        self.table.itemDoubleClicked.connect(lambda *_: self.open_detail())
        self.table.set_context_actions([
            ("打开详情", self.open_detail),
            ("加入监控", self.add_tracking),
        ])

    def search_apps(self) -> None:
        keyword = self.keyword_input.text().strip()
        if not keyword:
            self.show_error("请输入关键词。")
            return

        country = self.country_input.text().strip() or "us"
        lang = self.lang_input.text().strip() or "en"
        limit = safe_int(self.limit_input.text(), 50)
        self.run_task(
            "正在搜索应用...",
            lambda: self.google_play_service.search(
                keyword, country=country, lang=lang, limit=limit
            ),
            self._on_search_finished,
        )

    def _on_search_finished(self, results) -> None:
        # Show results the instant the search returns; load icons afterwards in the
        # background so the table isn't blocked on ~12 slow image round-trips.
        self.search_results = results
        self._search_gen += 1
        self.table.set_rows(results)
        self.show_status(f"已获取 {len(results)} 条搜索结果")
        self._load_icons_async(results)

    def _load_icons_async(self, results) -> None:
        head = results[: min(len(results), 12)]
        if not head:
            return
        gen = self._search_gen
        urls = [item.icon_url for item in head]
        self.run_background(
            lambda: fetch_images(urls, timeout=6.0, thumbnail_size=96),
            lambda icons: self._apply_icons(gen, head, icons),
        )

    def _apply_icons(self, gen: int, head, icons) -> None:
        if gen != self._search_gen:
            return  # a newer search superseded this icon load
        for item, icon in zip(head, icons, strict=True):
            item.raw["_icon_bytes"] = icon
        self.table.set_rows(self.search_results)

    def open_detail(self) -> None:
        row = self.table.current_row_data(self.search_results)
        if row is None:
            self.show_error("请先选择一条应用记录。")
            return
        self.window_api.open_app_detail(row.app_id)

    def add_tracking(self) -> None:
        row = self.table.current_row_data(self.search_results)
        if row is None:
            self.show_error("请先选择一条应用记录。")
            return
        self.run_task(
            "正在加入监控...",
            lambda: self.tracking_service.add_app(
                row.app_id,
                self.country_input.text().strip() or "us",
                self.lang_input.text().strip() or "en",
            ),
            lambda _: self.show_status("已加入监控"),
        )
