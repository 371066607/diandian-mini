from __future__ import annotations

import re

from PySide6.QtWidgets import QHBoxLayout

from app.ui.pages.base_page import BasePage
from app.ui.widgets.review_table import ReviewTableWidget

class ReviewsPage(BasePage):
    def __init__(self, services, window_api, logger):
        super().__init__(services, window_api, logger, "评论", "评论抓取、筛选和保存")
        self.review_service = services["review_service"]
        self.all_reviews = []
        self.current_reviews = []
        self._continuation_token = None
        defaults = self.get_default_settings()

        controls_card, controls_layout = self.create_card()
        self.app_id_input = self.create_input("app_id: com.whatsapp")
        self.sort_input = self.create_input("sort: newest", width=150)
        self.sort_input.setText("newest")
        self.country_input = self.create_input("country: us", width=120)
        self.country_input.setText(defaults["default_country"])
        self.lang_input = self.create_input("lang: en", width=120)
        self.lang_input.setText(defaults["default_lang"])
        self.fetch_button = self.create_primary_button("获取评论")
        self.load_more_button = self.create_secondary_button("加载更多")
        self.load_more_button.setEnabled(False)
        self.save_button = self.create_secondary_button("保存评论")
        self.rating_filter_input = self.create_input("筛选: 1-2星", width=180)
        self.text_filter_input = self.create_input("搜索评论内容", width=220)

        top_row = QHBoxLayout()
        for widget in [
            self.app_id_input,
            self.sort_input,
            self.country_input,
            self.lang_input,
            self.fetch_button,
            self.load_more_button,
            self.save_button,
        ]:
            top_row.addWidget(widget)
        controls_layout.addLayout(top_row)

        filter_row = QHBoxLayout()
        filter_row.addWidget(self.rating_filter_input)
        filter_row.addWidget(self.text_filter_input)
        filter_row.addStretch()
        controls_layout.addLayout(filter_row)
        self.root_layout.addWidget(controls_card)

        table_card, table_layout = self.create_card("评论列表")
        self.table = ReviewTableWidget()
        table_layout.addWidget(self.table)
        self.root_layout.addWidget(table_card)

        self.fetch_button.clicked.connect(self.fetch_reviews)
        self.load_more_button.clicked.connect(self.load_more)
        self.save_button.clicked.connect(self.save_reviews)
        self.app_id_input.returnPressed.connect(self.fetch_reviews)
        self.rating_filter_input.textChanged.connect(self.apply_filters)
        self.text_filter_input.textChanged.connect(self.apply_filters)

    def load_app(
        self,
        app_id: str,
        *,
        country: str = "us",
        lang: str = "en",
        auto_fetch: bool = True,
    ) -> None:
        self.app_id_input.setText(app_id)
        self.country_input.setText(country)
        self.lang_input.setText(lang)
        if auto_fetch:
            self.fetch_reviews()

    def fetch_reviews(self) -> None:
        app_id = self.app_id_input.text().strip()
        if not app_id:
            self.show_error("请输入包名。")
            return
        country = self.country_input.text().strip() or "us"
        lang = self.lang_input.text().strip() or "en"
        sort = self.sort_input.text().strip() or "newest"
        self.all_reviews = []
        self._continuation_token = None
        self.load_more_button.setEnabled(False)
        self.run_task(
            "正在抓取评论...",
            lambda: self.review_service.fetch(app_id, country, lang, sort),
            self._on_reviews_finished,
        )

    def load_more(self) -> None:
        app_id = self.app_id_input.text().strip()
        if not app_id or self._continuation_token is None:
            return
        country = self.country_input.text().strip() or "us"
        lang = self.lang_input.text().strip() or "en"
        sort = self.sort_input.text().strip() or "newest"
        token = self._continuation_token
        self.load_more_button.setEnabled(False)
        self.run_task(
            "正在加载更多评论...",
            lambda: self.review_service.fetch(app_id, country, lang, sort, token),
            self._on_more_finished,
        )

    def _on_reviews_finished(self, result) -> None:
        items, token = result
        self._continuation_token = token
        self.all_reviews = items
        self.apply_filters()
        self.load_more_button.setEnabled(len(items) > 0)
        self.show_status(f"已获取 {len(items)} 条评论")

    def _on_more_finished(self, result) -> None:
        items, token = result
        self._continuation_token = token
        self.all_reviews.extend(items)
        self.apply_filters()
        self.load_more_button.setEnabled(len(items) > 0)
        self.show_status(f"共 {len(self.all_reviews)} 条评论")

    def apply_filters(self) -> None:
        rating_filter = self._parse_rating_filter(self.rating_filter_input.text().strip())
        text_filter = self.text_filter_input.text().strip().casefold()

        filtered = []
        for item in self.all_reviews:
            if rating_filter is not None and item.rating not in rating_filter:
                continue
            content = (item.content or "").casefold()
            if text_filter and text_filter not in content:
                continue
            filtered.append(item)

        self.current_reviews = filtered
        self.table.set_reviews(filtered)

    def save_reviews(self) -> None:
        app_id = self.app_id_input.text().strip()
        if not app_id or not self.all_reviews:
            self.show_error("请先获取评论。")
            return
        country = self.country_input.text().strip() or "us"
        lang = self.lang_input.text().strip() or "en"
        self.run_task(
            "正在保存评论...",
            lambda: self.review_service.save(app_id, country, lang, self.all_reviews),
            lambda saved: self.show_status(f"新保存 {saved} 条评论"),
        )

    def _parse_rating_filter(self, value: str) -> set[int] | None:
        if not value:
            return None
        values = [int(item) for item in re.findall(r"\d+", value)]
        if not values:
            return None
        if "-" in value and len(values) >= 2:
            start, end = values[0], values[1]
            lower, upper = sorted((start, end))
            return set(range(lower, upper + 1))
        return {value for value in values if 1 <= value <= 5}
