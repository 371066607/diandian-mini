from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.ui.pages.base_page import BasePage
from app.ui.widgets.app_table import AppTableWidget
from app.ui.widgets.chart_widget import ChartWidget
from app.utils.image_loader import fetch_images, pixmap_from_bytes, placeholder_pixmap


class AppDetailPage(BasePage):
    def __init__(self, services, window_api, logger):
        super().__init__(services, window_api, logger, "应用详情", "包名查询、保存快照、相似竞品和历史趋势")
        self.google_play_service = services["google_play_service"]
        self.tracking_service = services["tracking_service"]
        self.monetization_service = services["monetization_service"]
        self.current_detail = None
        self.current_similar = []
        self.current_icon_bytes: bytes | None = None
        self.current_screenshot_bytes: list[bytes | None] = []
        defaults = self.get_default_settings()

        toolbar_card, toolbar_layout = self.create_card()
        self.app_id_input = self.create_input("com.whatsapp")
        self.app_id_input.setMinimumWidth(220)
        self.country_input = self.create_input("country: us", width=120)
        self.country_input.setText(defaults["default_country"])
        self.lang_input = self.create_input("lang: en", width=120)
        self.lang_input.setText(defaults["default_lang"])
        self.fetch_button = self.create_primary_button("获取详情")
        self.save_button = self.create_secondary_button("保存快照")
        self.track_button = self.create_secondary_button("加入监控")
        self.similar_button = self.create_secondary_button("获取相似应用")
        self.reviews_button = self.create_secondary_button("获取评论")
        self.open_button = self.create_secondary_button("打开商店")

        query_row = QHBoxLayout()
        query_row.setSpacing(12)
        query_row.addWidget(self.app_id_input, 1)
        query_row.addWidget(self.country_input)
        query_row.addWidget(self.lang_input)
        query_row.addWidget(self.fetch_button)
        toolbar_layout.addLayout(query_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(12)
        for widget in [
            self.save_button,
            self.track_button,
            self.similar_button,
            self.reviews_button,
            self.open_button,
        ]:
            action_row.addWidget(widget)
        action_row.addStretch()
        toolbar_layout.addLayout(action_row)
        self.root_layout.addWidget(toolbar_card)

        # The detail page is tall (summary + charts + screenshots + similar). Keep the
        # toolbar fixed and let everything below scroll, so nothing gets compressed/
        # overlapped on shorter windows.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_content = QWidget()
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setContentsMargins(0, 0, 8, 0)
        content_layout.setSpacing(20)
        scroll.setWidget(scroll_content)
        self.root_layout.addWidget(scroll, 1)

        summary_card, summary_layout = self.create_card()
        self.icon_label = QLabel()
        self.icon_label.setPixmap(placeholder_pixmap("ICON"))
        self.icon_label.setFixedSize(96, 96)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label = QLabel("等待加载应用详情")
        self.name_label.setStyleSheet("font-size: 20px; font-weight: 700; color: #0F172A;")
        self.meta_label = QLabel("app_id / developer / category")
        self.meta_label.setStyleSheet("color: #64748B; font-size: 13px;")
        self.summary_note_label = QLabel("评分 / 评论数 / 安装量 / 版本")
        self.summary_note_label.setStyleSheet("color: #1E293B; font-size: 14px;")
        identity = QVBoxLayout()
        identity.setSpacing(6)
        identity.addWidget(self.name_label)
        identity.addWidget(self.meta_label)
        identity.addWidget(self.summary_note_label)
        identity.addStretch()
        top = QHBoxLayout()
        top.setSpacing(18)
        top.addWidget(self.icon_label, alignment=Qt.AlignmentFlag.AlignTop)
        top.addLayout(identity, 1)
        summary_layout.addLayout(top)

        # Metrics as a full-width grid of stat chips below the identity row — the old
        # layout crammed all 9 into the narrow column beside the icon and they overlapped.
        metrics_grid = QGridLayout()
        metrics_grid.setHorizontalSpacing(12)
        metrics_grid.setVerticalSpacing(12)
        self.metric_values: dict[str, QLabel] = {}
        metric_fields = [
            ("评分", "rating"),
            ("评分数", "ratings_count"),
            ("评论数", "reviews_count"),
            ("安装量", "installs"),
            ("真实安装", "real_installs"),
            ("内容分级", "content_rating"),
            ("价格", "price"),
            ("内购", "has_iap"),
            ("内购价", "iap_price_range"),
            ("含广告", "contains_ads"),
            ("版本", "version"),
            ("更新", "updated"),
            ("发布", "released"),
        ]
        columns = 3
        for index, (title, key) in enumerate(metric_fields):
            chip, value = self._build_metric_chip(title)
            self.metric_values[key] = value
            metrics_grid.addWidget(chip, index // columns, index % columns)
        for col in range(columns):
            metrics_grid.setColumnStretch(col, 1)
        summary_layout.addLayout(metrics_grid)
        content_layout.addWidget(summary_card)

        extra_row = QHBoxLayout()
        extra_row.setSpacing(20)
        dist_card, dist_layout = self.create_card("评分分布")
        self.histogram_bars: dict[int, QProgressBar] = {}
        self.histogram_counts: dict[int, QLabel] = {}
        for star in range(5, 0, -1):
            row_box = QHBoxLayout()
            row_box.setSpacing(10)
            star_label = QLabel(f"{star}★")
            star_label.setFixedWidth(30)
            star_label.setStyleSheet("color: #64748B; font-size: 13px;")
            bar = QProgressBar()
            bar.setFixedHeight(16)
            bar.setTextVisible(False)
            bar.setStyleSheet(
                "QProgressBar { background: #F1F5F9; border: none; border-radius: 8px; }"
                "QProgressBar::chunk { background: #2F67F6; border-radius: 8px; }"
            )
            count_label = QLabel("-")
            count_label.setMinimumWidth(150)
            count_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            count_label.setStyleSheet("color: #475569; font-size: 12px;")
            row_box.addWidget(star_label)
            row_box.addWidget(bar, 1)
            row_box.addWidget(count_label)
            dist_layout.addLayout(row_box)
            self.histogram_bars[star] = bar
            self.histogram_counts[star] = count_label

        dev_card, dev_layout = self.create_card("开发者信息")
        self.dev_email_label = QLabel("邮箱：-")
        self.dev_website_label = QLabel("官网：-")
        self.dev_privacy_label = QLabel("隐私政策：-")
        for link_label in (self.dev_email_label, self.dev_website_label, self.dev_privacy_label):
            link_label.setOpenExternalLinks(True)
            link_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            link_label.setWordWrap(True)
            link_label.setStyleSheet("font-size: 13px; color: #1E293B;")
            dev_layout.addWidget(link_label)
        dev_layout.addStretch()

        extra_row.addWidget(dist_card, 3)
        extra_row.addWidget(dev_card, 2)
        content_layout.addLayout(extra_row)

        mid_row = QHBoxLayout()
        score_card, score_layout = self.create_card("商业化强度")
        self.score_label = self.create_stat_value("0 / 100")
        self.score_note = QLabel("基于公开数据推断，不代表真实收入。")
        self.score_note.setStyleSheet("font-size: 12px; color: #64748B;")
        score_layout.addWidget(self.score_label)
        score_layout.addWidget(self.score_note)
        rating_card, rating_layout = self.create_card("评分历史")
        self.rating_chart = ChartWidget("评分历史")
        self.rating_chart.setMinimumHeight(200)
        rating_layout.addWidget(self.rating_chart)
        reviews_card, reviews_layout = self.create_card("评论数历史")
        self.reviews_chart = ChartWidget("评论数历史")
        self.reviews_chart.setMinimumHeight(200)
        reviews_layout.addWidget(self.reviews_chart)
        mid_row.addWidget(score_card, 1)
        mid_row.addWidget(rating_card, 2)
        mid_row.addWidget(reviews_card, 2)
        content_layout.addLayout(mid_row)

        installs_card, installs_layout = self.create_card("安装量历史（真实安装数）")
        self.installs_chart = ChartWidget("安装量历史")
        self.installs_chart.setMinimumHeight(220)
        installs_layout.addWidget(self.installs_chart)
        content_layout.addWidget(installs_card)

        media_card, media_layout = self.create_card("截图 / 描述 / 更新日志")
        self.screenshots_scroll = QScrollArea()
        self.screenshots_scroll.setWidgetResizable(True)
        self.screenshots_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.screenshots_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.screenshots_scroll.setFixedHeight(220)
        self.screenshots_scroll.setStyleSheet("border: none; background: transparent;")
        self.screenshots_container = QWidget()
        self.screenshots_layout = QHBoxLayout(self.screenshots_container)
        self.screenshots_layout.setContentsMargins(0, 0, 0, 0)
        self.screenshots_layout.setSpacing(12)
        self.screenshots_scroll.setWidget(self.screenshots_container)
        media_layout.addWidget(self.screenshots_scroll)
        self.description = QTextEdit()
        self.description.setReadOnly(True)
        self.description.setMinimumHeight(150)
        media_layout.addWidget(self.description)
        content_layout.addWidget(media_card)

        bottom_row = QHBoxLayout()
        similar_card, similar_layout = self.create_card("相似 App")
        self.similar_table = AppTableWidget(
            [("应用", "title"), ("包名", "app_id"), ("评分", "rating"), ("安装量", "installs")]
        )
        self.similar_table.setMinimumHeight(220)
        similar_layout.addWidget(self.similar_table)
        bottom_row.addWidget(similar_card)
        content_layout.addLayout(bottom_row)
        content_layout.addStretch()

        self.fetch_button.clicked.connect(self.fetch_detail)
        self.app_id_input.returnPressed.connect(self.fetch_detail)
        self.save_button.clicked.connect(self.save_snapshot)
        self.track_button.clicked.connect(self.add_tracking)
        self.similar_button.clicked.connect(self.fetch_similar)
        self.reviews_button.clicked.connect(self.open_reviews)
        self.open_button.clicked.connect(self.open_store)
        self.similar_table.itemDoubleClicked.connect(lambda *_: self._open_selected_similar())
        self._render_screenshots([])

    def _build_metric_chip(self, title: str) -> tuple[QFrame, QLabel]:
        chip = QFrame()
        chip.setMinimumHeight(56)
        chip.setStyleSheet(
            "QFrame { background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 10px; }"
        )
        layout = QVBoxLayout(chip)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)
        label = QLabel(title)
        label.setStyleSheet("font-size: 12px; color: #64748B; border: none;")
        value = QLabel("-")
        value.setWordWrap(True)
        value.setStyleSheet("font-size: 16px; font-weight: 700; color: #0F172A; border: none;")
        layout.addWidget(label)
        layout.addWidget(value)
        return chip, value

    def _update_histogram(self, histogram: list[int]) -> None:
        counts = list(histogram or [])
        total = sum(counts) or 1
        maximum = max(counts) if counts else 1
        for star in range(5, 0, -1):
            count = counts[star - 1] if len(counts) >= star else 0
            bar = self.histogram_bars[star]
            bar.setRange(0, max(maximum, 1))
            bar.setValue(count)
            self.histogram_counts[star].setText(f"{count:,} ({count / total * 100:.0f}%)")

    def _set_link(self, label: QLabel, prefix: str, url: str | None, mailto: bool = False) -> None:
        if not url:
            label.setText(f"{prefix}：-")
            return
        href = f"mailto:{url}" if mailto else url
        label.setText(f'{prefix}：<a href="{href}" style="color:#2563EB;">{url}</a>')

    def load_app(self, app_id: str, country: str | None = None, lang: str | None = None) -> None:
        self.app_id_input.setText(app_id)
        if country:
            self.country_input.setText(country)
        if lang:
            self.lang_input.setText(lang)
        self.fetch_detail()

    def fetch_detail(self) -> None:
        app_id = self.app_id_input.text().strip()
        if not app_id:
            self.show_error("请输入包名。")
            return
        country = self.country_input.text().strip() or "us"
        lang = self.lang_input.text().strip() or "en"
        self.run_task(
            "正在获取应用详情...",
            lambda: self._load_detail_bundle(app_id, country, lang),
            self._on_detail_finished,
        )

    def fetch_similar(self) -> None:
        app_id = self.app_id_input.text().strip()
        if not app_id:
            self.show_error("请先输入包名。")
            return
        country = self.country_input.text().strip() or "us"
        lang = self.lang_input.text().strip() or "en"
        self.run_task(
            "正在获取相似应用...",
            lambda: self.google_play_service.similar(app_id, country=country, lang=lang, limit=10),
            self._on_similar_finished,
        )

    def open_reviews(self) -> None:
        app_id = self.app_id_input.text().strip()
        if not app_id:
            self.show_error("请先输入包名。")
            return
        self.window_api.open_reviews(
            app_id,
            country=self.country_input.text().strip() or "us",
            lang=self.lang_input.text().strip() or "en",
            auto_fetch=True,
        )

    def _on_detail_finished(self, payload) -> None:
        detail = payload["detail"]
        similar = payload["similar"]
        history = payload["history"]
        self.current_detail = detail
        self.current_similar = similar
        self.current_icon_bytes = payload["icon_bytes"]
        self.current_screenshot_bytes = payload["screenshots"]
        self.name_label.setText(detail.title or detail.app_id)
        self.meta_label.setText(
            f"{detail.app_id} · {detail.developer or '-'} · {detail.category or '-'}"
        )
        self.summary_note_label.setText(
            f"{detail.price or '免费'} · {'含内购' if detail.has_iap else '无内购'} · "
            f"Android {detail.android_version or '-'}"
        )
        self.icon_label.setPixmap(
            pixmap_from_bytes(
                self.current_icon_bytes,
                width=96,
                height=96,
                fallback_text=detail.title or "ICON",
            )
        )
        self.metric_values["rating"].setText(f"{detail.rating:.2f}" if detail.rating else "-")
        self.metric_values["ratings_count"].setText(
            f"{detail.ratings_count:,}" if detail.ratings_count else "-"
        )
        self.metric_values["reviews_count"].setText(
            f"{detail.reviews_count:,}" if detail.reviews_count else "-"
        )
        self.metric_values["installs"].setText(detail.installs or "-")
        self.metric_values["price"].setText(detail.price or ("Free" if detail.free else "-"))
        self.metric_values["has_iap"].setText("是" if detail.has_iap else "否")
        self.metric_values["version"].setText(detail.version or "-")
        self.metric_values["updated"].setText(detail.updated or "-")
        self.metric_values["released"].setText(detail.released or "-")
        self.metric_values["real_installs"].setText(
            f"{detail.real_installs:,}" if detail.real_installs else "-"
        )
        self.metric_values["content_rating"].setText(detail.content_rating or "-")
        self.metric_values["iap_price_range"].setText(detail.iap_price_range or "-")
        self.metric_values["contains_ads"].setText("是" if detail.contains_ads else "否")
        self._update_histogram(detail.histogram)
        self._set_link(self.dev_email_label, "邮箱", detail.developer_email, mailto=True)
        self._set_link(self.dev_website_label, "官网", detail.developer_website)
        self._set_link(self.dev_privacy_label, "隐私政策", detail.privacy_policy)
        score = self.monetization_service.score(detail)
        self.score_label.setText(f"{score['score']} / 100")
        self.score_note.setText("；".join(score["signals"][:3]) or score["note"])
        self._on_similar_finished(similar)
        self._render_screenshots(self.current_screenshot_bytes)
        self.description.setPlainText(
            "\n\n".join(filter(None, [detail.summary, detail.description, detail.changelog]))
        )
        labels = [item.captured_at[5:10] for item in history]
        self.rating_chart.set_series(labels, [item.rating or 0 for item in history])
        self.reviews_chart.set_series(labels, [item.reviews_count or 0 for item in history])
        self.installs_chart.set_series(
            labels, [item.real_installs or item.min_installs or 0 for item in history]
        )

    def _on_similar_finished(self, similar) -> None:
        self.current_similar = similar
        self.similar_table.set_rows(similar[:10])

    def _open_selected_similar(self) -> None:
        row = self.similar_table.current_row_data(self.current_similar)
        if row is None:
            return
        self.load_app(row.app_id, self.country_input.text().strip() or "us", self.lang_input.text().strip() or "en")

    def save_snapshot(self) -> None:
        if self.current_detail is None:
            self.show_error("请先获取应用详情。")
            return
        self.run_task(
            "正在保存快照...",
            lambda: self.tracking_service.sync_app_now(
                self.current_detail.app_id,
                country=self.country_input.text().strip() or "us",
                lang=self.lang_input.text().strip() or "en",
            ),
            self._after_snapshot_saved,
        )

    def add_tracking(self) -> None:
        app_id = self.app_id_input.text().strip()
        if not app_id:
            self.show_error("请先输入包名。")
            return
        self.run_task(
            "正在加入监控...",
            lambda: self.tracking_service.add_app(
                app_id,
                country=self.country_input.text().strip() or "us",
                lang=self.lang_input.text().strip() or "en",
            ),
            lambda _: self.show_status("已加入监控"),
        )

    def open_store(self) -> None:
        target_url = None
        if self.current_detail and self.current_detail.store_url:
            target_url = self.current_detail.store_url
        else:
            app_id = self.app_id_input.text().strip()
            if app_id:
                country = self.country_input.text().strip() or "us"
                lang = self.lang_input.text().strip() or "en"
                target_url = (
                    f"https://play.google.com/store/apps/details?"
                    f"id={app_id}&gl={country}&hl={lang}"
                )
        if target_url:
            QDesktopServices.openUrl(QUrl(target_url))

    def _load_detail_bundle(self, app_id: str, country: str, lang: str) -> dict:
        detail = self.google_play_service.app_detail(app_id, country=country, lang=lang)
        similar = self.google_play_service.similar(app_id, country=country, lang=lang, limit=10)
        history = self.tracking_service.get_history(app_id, country=country, lang=lang)
        image_urls = [detail.icon_url, *(detail.screenshots or [])[:3]]
        images = fetch_images(image_urls, timeout=6.0, thumbnail_size=320)
        return {
            "detail": detail,
            "similar": similar,
            "history": history,
            "icon_bytes": images[0],
            "screenshots": images[1:],
        }

    def _after_snapshot_saved(self, detail) -> None:
        self.current_detail = detail
        history = self.tracking_service.get_history(
            detail.app_id,
            country=self.country_input.text().strip() or "us",
            lang=self.lang_input.text().strip() or "en",
        )
        labels = [item.captured_at[5:10] for item in history]
        self.rating_chart.set_series(labels, [item.rating or 0 for item in history])
        self.reviews_chart.set_series(labels, [item.reviews_count or 0 for item in history])
        self.installs_chart.set_series(
            labels, [item.real_installs or item.min_installs or 0 for item in history]
        )
        self.show_status("快照已写入 SQLite")

    def _render_screenshots(self, screenshots: list[bytes | None]) -> None:
        while self.screenshots_layout.count():
            item = self.screenshots_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not screenshots:
            empty = QLabel("暂无截图")
            empty.setStyleSheet("font-size: 13px; color: #64748B;")
            self.screenshots_layout.addWidget(empty)
            self.screenshots_layout.addStretch()
            return
        for index, image_bytes in enumerate(screenshots, start=1):
            label = QLabel()
            label.setFixedSize(140, 180)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet(
                "background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 12px;"
            )
            label.setPixmap(
                pixmap_from_bytes(
                    image_bytes,
                    width=132,
                    height=172,
                    fallback_text=f"SS{index}",
                )
            )
            self.screenshots_layout.addWidget(label)
        self.screenshots_layout.addStretch()
