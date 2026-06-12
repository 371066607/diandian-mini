from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
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

from app.ui.alert_labels import (
    ALERT_SEVERITY_COLORS,
    alert_severity_label,
    alert_type_label,
)
from app.ui.pages.base_page import BasePage
from app.ui.widgets.app_table import AppTableWidget
from app.ui.widgets.chart_widget import ChartWidget
from app.utils.image_loader import fetch_images, pixmap_from_bytes, placeholder_pixmap
from app.utils.time_utils import now_iso


class AppDetailPage(BasePage):
    def __init__(self, services, window_api, logger):
        super().__init__(services, window_api, logger, "应用详情", "包名查询、保存快照、相似竞品和历史趋势")
        self.google_play_service = services["google_play_service"]
        self.app_store_service = services.get("app_store_service")
        self.tracking_service = services["tracking_service"]
        self.monetization_service = services["monetization_service"]
        self.alert_service = services["alert_service"]
        self.export_service = services["export_service"]
        self.review_service = services["review_service"]
        self.current_detail = None
        self.current_similar = []
        self.current_icon_bytes: bytes | None = None
        self.current_screenshot_bytes: list[bytes | None] = []
        self._detail_gen = 0
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
        self.permissions_button = self.create_secondary_button("获取权限")
        self.reviews_button = self.create_secondary_button("获取评论")
        self.open_button = self.create_secondary_button("打开商店")
        self.history_button = self.create_secondary_button("查看历史")
        self.export_button = self.create_secondary_button("导出 CSV")

        query_row = self.create_actions_row(
            [
                self.app_id_input,
                self.country_input,
                self.lang_input,
                self.fetch_button,
            ]
        )
        toolbar_layout.addLayout(query_row)

        action_row = self.create_actions_row(
            [
                self.save_button,
                self.track_button,
                self.similar_button,
                self.permissions_button,
                self.reviews_button,
                self.open_button,
                self.history_button,
                self.export_button,
            ]
        )
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
        self.metric_chips: dict[str, QFrame] = {}
        # keys marked True are Google Play-only; hidden when on App Store
        self._gp_only_chips = {
            "installs", "min_installs", "real_installs",
            "daily_installs", "monthly_installs", "app_age_days",
            "android_api", "sale", "iap_price_range", "contains_ads",
        }
        metric_fields = [
            ("评分", "rating"),
            ("评分数", "ratings_count"),
            ("评论数", "reviews_count"),
            ("安装量", "installs"),
            ("最低安装", "min_installs"),
            ("真实安装", "real_installs"),
            ("日均安装", "daily_installs"),
            ("月均安装", "monthly_installs"),
            ("上线天数", "app_age_days"),
            ("内容分级", "content_rating"),
            ("Android API", "android_api"),
            ("价格", "price"),
            ("原价", "original_price"),
            ("促销", "sale"),
            ("内购", "has_iap"),
            ("内购价", "iap_price_range"),
            ("含广告", "contains_ads"),
            ("版本", "version"),
            ("可下载", "available"),
            ("更新", "updated"),
            ("发布", "released"),
        ]
        columns = 4
        for index, (title, key) in enumerate(metric_fields):
            chip, value = self._build_metric_chip(title)
            self.metric_values[key] = value
            self.metric_chips[key] = chip
            metrics_grid.addWidget(chip, index // columns, index % columns)
        for col in range(columns):
            metrics_grid.setColumnStretch(col, 1)
        summary_layout.addLayout(metrics_grid)
        content_layout.addWidget(summary_card)

        extra_row = QHBoxLayout()
        extra_row.setSpacing(20)
        dist_card, dist_layout = self.create_card("评分分布")
        self._histogram_card = dist_card
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
        self.dev_address_label = QLabel("地址：-")
        self.dev_phone_label = QLabel("电话：-")
        self.dev_country_label = QLabel("发布国：-")
        for plain_label in (self.dev_address_label, self.dev_phone_label, self.dev_country_label):
            plain_label.setWordWrap(True)
            plain_label.setStyleSheet("font-size: 13px; color: #1E293B;")
            dev_layout.addWidget(plain_label)
        dev_layout.addStretch()

        extra_row.addWidget(dist_card, 3)
        extra_row.addWidget(dev_card, 2)
        content_layout.addLayout(extra_row)

        # 更多信息 — the leftover app_analyze fields that don't fit the stat-chip grid
        # (technical identifiers, currency/min installs, trailer/header links, data safety).
        info_card, info_layout = self.create_card("更多信息")
        info_grid = QGridLayout()
        info_grid.setHorizontalSpacing(24)
        info_grid.setVerticalSpacing(8)
        self.info_labels: dict[str, QLabel] = {}
        self._gp_only_info = {"min_daily_installs", "min_monthly_installs", "video"}
        info_fields = [
            ("应用包", "app_bundle"),
            ("类目 ID", "genre_id"),
            ("开发者 ID", "developer_id"),
            ("货币", "currency"),
            ("最低日均安装", "min_daily_installs"),
            ("最低月均安装", "min_monthly_installs"),
            ("预告片", "video"),
            ("头图", "header_image"),
        ]
        info_cols = 2
        for index, (label_text, key) in enumerate(info_fields):
            value = QLabel(f"{label_text}：-")
            value.setWordWrap(True)
            value.setOpenExternalLinks(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            value.setStyleSheet("font-size: 13px; color: #1E293B;")
            self.info_labels[key] = value
            info_grid.addWidget(value, index // info_cols, index % info_cols)
        for col in range(info_cols):
            info_grid.setColumnStretch(col, 1)
        info_layout.addLayout(info_grid)
        self.content_rating_desc_label = QLabel("内容分级说明：-")
        self.content_rating_desc_label.setWordWrap(True)
        self.content_rating_desc_label.setStyleSheet("font-size: 13px; color: #475569;")
        info_layout.addWidget(self.content_rating_desc_label)
        self.data_safety_label = QLabel("数据安全：-")
        self.data_safety_label.setWordWrap(True)
        self.data_safety_label.setStyleSheet("font-size: 13px; color: #475569;")
        info_layout.addWidget(self.data_safety_label)
        content_layout.addWidget(info_card)

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

        perms_card, perms_outer = self.create_card("权限")
        perms_scroll = QScrollArea()
        perms_scroll.setWidgetResizable(True)
        perms_scroll.setFixedHeight(200)
        perms_scroll.setStyleSheet("QScrollArea { border: none; }")
        self._perms_container = QWidget()
        self._perms_layout = QVBoxLayout(self._perms_container)
        self._perms_layout.setContentsMargins(0, 0, 0, 0)
        self._perms_layout.setSpacing(10)
        hint = QLabel("点击「获取权限」按钮加载")
        hint.setStyleSheet("font-size: 13px; color: #94A3B8;")
        self._perms_layout.addWidget(hint)
        self._perms_layout.addStretch()
        perms_scroll.setWidget(self._perms_container)
        perms_outer.addWidget(perms_scroll)
        content_layout.addWidget(perms_card)

        bottom_row = QHBoxLayout()
        similar_card, similar_layout = self.create_card("相似 App")
        self.similar_table = AppTableWidget(
            [("应用", "title"), ("包名", "app_id"), ("评分", "rating"), ("安装量", "installs")]
        )
        self.similar_table.setMinimumHeight(220)
        similar_layout.addWidget(self.similar_table)
        bottom_row.addWidget(similar_card)

        alerts_card, alerts_layout = self.create_card("最近告警")
        self.alerts_table = AppTableWidget(
            [
                ("时间", "created_at"),
                ("级别", "severity"),
                ("类型", "type"),
                ("内容", "message"),
            ],
            row_tint=self._alert_row_tint,
        )
        self.alerts_table.setMinimumHeight(220)
        alerts_layout.addWidget(self.alerts_table)
        bottom_row.addWidget(alerts_card)
        content_layout.addLayout(bottom_row)

        reviews_card, reviews_layout = self.create_card("最近评论（监控落库）")
        self.reviews_table = AppTableWidget(
            [
                ("时间", "review_created_at"),
                ("评分", "rating"),
                ("内容", "content"),
            ]
        )
        self.reviews_table.setMinimumHeight(200)
        reviews_layout.addWidget(self.reviews_table)
        content_layout.addWidget(reviews_card)
        content_layout.addStretch()

        self.fetch_button.clicked.connect(self.fetch_detail)
        self.app_id_input.returnPressed.connect(self.fetch_detail)
        self.save_button.clicked.connect(self.save_snapshot)
        self.track_button.clicked.connect(self.add_tracking)
        self.similar_button.clicked.connect(self.fetch_similar)
        self.permissions_button.clicked.connect(self.fetch_permissions)
        self.reviews_button.clicked.connect(self.open_reviews)
        self.open_button.clicked.connect(self.open_store)
        self.history_button.clicked.connect(self.open_history)
        self.export_button.clicked.connect(self.export_snapshots)
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

    def _chart_series(self, history, value_fn, current):
        """History snapshots as a series, plus today's freshly-fetched value as the
        trailing point — so the chart shows the current value even with no saved
        history yet, and builds into a real trend as snapshots accumulate."""
        labels = [item.captured_at[5:10] for item in history]
        values = [value_fn(item) for item in history]
        today = now_iso()[5:10]
        if current is not None and (not labels or labels[-1] != today):
            labels.append(today)
            values.append(current)
        return labels, values

    def _set_history_charts(self, history, detail) -> None:
        self.rating_chart.set_series(
            *self._chart_series(history, lambda i: i.rating or 0, detail.rating)
        )
        self.reviews_chart.set_series(
            *self._chart_series(history, lambda i: i.reviews_count or 0, detail.reviews_count)
        )
        self.installs_chart.set_series(
            *self._chart_series(
                history,
                lambda i: i.real_installs or i.min_installs or 0,
                detail.real_installs or detail.min_installs,
            )
        )

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

    def _set_link(
        self,
        label: QLabel,
        prefix: str,
        url: str | None,
        mailto: bool = False,
        text: str | None = None,
    ) -> None:
        if not url:
            label.setText(f"{prefix}：-")
            return
        href = f"mailto:{url}" if mailto else url
        display = text or url
        label.setText(f'{prefix}：<a href="{href}" style="color:#2563EB;">{display}</a>')

    def _format_data_safety(self, data_safety) -> str:
        """Render the dataSafety list (shape varies by source) into a short summary."""
        if not data_safety:
            return "-"
        parts: list[str] = []
        for item in data_safety:
            if isinstance(item, dict):
                name = item.get("data") or item.get("type") or item.get("name") or item.get("category")
                if name:
                    parts.append(str(name))
            elif item:
                parts.append(str(item))
        if not parts:
            return f"{len(data_safety)} 项"
        return "、".join(parts[:8]) + (" …" if len(parts) > 8 else "")

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
        self._detail_gen += 1
        gen = self._detail_gen
        self.run_task(
            "正在获取应用详情...",
            lambda: self._load_detail_core(app_id, country, lang),
            lambda payload: self._on_detail_finished(payload, gen),
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
            lambda: self._active_service().similar(app_id, country=country, lang=lang, limit=10),
            self._on_similar_finished,
        )

    def fetch_permissions(self) -> None:
        app_id = self.app_id_input.text().strip()
        if not app_id:
            self.show_error("请先输入包名。")
            return
        country = self.country_input.text().strip() or "us"
        lang = self.lang_input.text().strip() or "en"
        self.run_task(
            "正在获取权限...",
            lambda: self.google_play_service.permissions(app_id, country=country, lang=lang),
            self._on_permissions_finished,
        )

    def _on_permissions_finished(self, data: dict) -> None:
        while self._perms_layout.count() > 1:
            item = self._perms_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not data:
            hint = QLabel("未找到权限信息")
            hint.setStyleSheet("font-size: 13px; color: #94A3B8;")
            self._perms_layout.insertWidget(0, hint)
            return
        pos = 0
        for group, items in data.items():
            if not items:
                continue
            header = QLabel(f"{group}  ({len(items)})")
            header.setStyleSheet("font-size: 13px; font-weight: 600; color: #1E293B;")
            self._perms_layout.insertWidget(pos, header)
            pos += 1
            for perm in items:
                lbl = QLabel(f"  · {perm}")
                lbl.setStyleSheet("font-size: 13px; color: #475569;")
                lbl.setWordWrap(True)
                self._perms_layout.insertWidget(pos, lbl)
                pos += 1
        total = sum(len(v) for v in data.values())
        self.show_status(f"权限：{len(data)} 组，共 {total} 条")

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

    def _on_detail_finished(self, payload, gen) -> None:
        if gen != self._detail_gen:
            return  # a newer fetch superseded this one
        detail = payload["detail"]
        history = payload["history"]
        self.current_detail = detail
        self.current_similar = []
        self.current_icon_bytes = None
        self.current_screenshot_bytes = []
        self.name_label.setText(detail.title or detail.app_id)
        categories_str = "、".join(detail.categories[:2]) if detail.categories else (detail.category or "-")
        self.meta_label.setText(
            f"{detail.app_id} · {detail.developer or '-'} · {categories_str}"
        )
        self.summary_note_label.setText(
            f"{detail.price or '免费'} · {'含内购' if detail.has_iap else '无内购'} · "
            f"Android {detail.android_version or '-'}"
        )
        self.icon_label.setPixmap(placeholder_pixmap(detail.title or "ICON"))
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
        daily = detail.real_daily_installs or detail.daily_installs
        self.metric_values["daily_installs"].setText(f"{daily:,}" if daily else "-")
        monthly = detail.real_monthly_installs or detail.monthly_installs
        self.metric_values["monthly_installs"].setText(f"{monthly:,}" if monthly else "-")
        self.metric_values["app_age_days"].setText(
            f"{detail.app_age_days:,} 天" if detail.app_age_days else "-"
        )
        self.metric_values["content_rating"].setText(detail.content_rating or "-")
        self.metric_values["iap_price_range"].setText(detail.iap_price_range or "-")
        ads = detail.contains_ads if detail.contains_ads is not None else detail.ad_supported
        self.metric_values["contains_ads"].setText("是" if ads else "否")
        self.metric_values["min_installs"].setText(
            f"{detail.min_installs:,}" if detail.min_installs else "-"
        )
        if detail.min_android_api and detail.max_android_api:
            api_text = f"{detail.min_android_api} ~ {detail.max_android_api}"
        elif detail.min_android_api:
            api_text = f"{detail.min_android_api}+"
        else:
            api_text = "-"
        self.metric_values["android_api"].setText(api_text)
        if detail.original_price:
            op = (
                f"{detail.currency} {detail.original_price:.2f}"
                if detail.currency
                else f"{detail.original_price:.2f}"
            )
        else:
            op = "-"
        self.metric_values["original_price"].setText(op)
        self.metric_values["sale"].setText("是" if detail.sale else "否")
        if detail.available is None:
            self.metric_values["available"].setText("-")
        else:
            self.metric_values["available"].setText("是" if detail.available else "否")
        self._update_histogram(detail.histogram)
        self._set_link(self.dev_email_label, "邮箱", detail.developer_email, mailto=True)
        self._set_link(self.dev_website_label, "官网", detail.developer_website)
        self._set_link(self.dev_privacy_label, "隐私政策", detail.privacy_policy)
        self.dev_address_label.setText(f"地址：{detail.developer_address or '-'}")
        self.dev_phone_label.setText(f"电话：{detail.developer_phone or '-'}")
        self.dev_country_label.setText(f"发布国：{detail.publisher_country or '-'}")
        self.info_labels["app_bundle"].setText(f"应用包：{detail.app_bundle or '-'}")
        self.info_labels["genre_id"].setText(f"类目 ID：{detail.genre_id or '-'}")
        self.info_labels["developer_id"].setText(f"开发者 ID：{detail.developer_id or '-'}")
        self.info_labels["currency"].setText(f"货币：{detail.currency or '-'}")
        self.info_labels["min_daily_installs"].setText(
            f"最低日均安装：{detail.min_daily_installs:,}" if detail.min_daily_installs else "最低日均安装：-"
        )
        self.info_labels["min_monthly_installs"].setText(
            f"最低月均安装：{detail.min_monthly_installs:,}" if detail.min_monthly_installs else "最低月均安装：-"
        )
        self._set_link(self.info_labels["video"], "预告片", detail.video, text="观看")
        self._set_link(self.info_labels["header_image"], "头图", detail.header_image, text="查看")
        self.content_rating_desc_label.setText(
            f"内容分级说明：{detail.content_rating_description or '-'}"
        )
        self.data_safety_label.setText(f"数据安全：{self._format_data_safety(detail.data_safety)}")
        score = self.monetization_service.score(detail)
        self.score_label.setText(f"{score['score']} / 100")
        self.score_note.setText("；".join(score["signals"][:3]) or score["note"])
        self.description.setPlainText(
            "\n\n".join(filter(None, [detail.summary, detail.description, detail.changelog]))
        )
        self._set_history_charts(history, detail)
        # Detail is shown — now stream in screenshots + similar apps in the background
        # so they don't block entering the page.
        self.similar_table.set_rows([])
        self.alerts_table.set_rows([])
        self.reviews_table.set_rows([])
        self._render_screenshots([])
        self._load_images_async(detail, gen)
        self._load_similar_async(detail.app_id, payload["country"], payload["lang"], gen)
        self._load_alerts_async(detail.app_id, gen)
        self._load_reviews_async(detail.app_id, gen)

    def _load_reviews_async(self, app_id: str, gen: int) -> None:
        self.run_background(
            lambda: self._collect_review_rows(app_id),
            lambda rows: self._apply_reviews(gen, rows),
        )

    def _collect_review_rows(self, app_id: str) -> list[dict]:
        reviews = self.review_service.list_cached(app_id, limit=10)
        rows = []
        for r in reviews:
            content = (r.content or "").strip().replace("\n", " ")
            if len(content) > 60:
                content = content[:60] + "…"
            rows.append(
                {
                    "review_created_at": (r.review_created_at or "")[:10],
                    "rating": r.rating,
                    "content": content,
                }
            )
        return rows

    def _apply_reviews(self, gen: int, rows: list[dict]) -> None:
        if gen != self._detail_gen:
            return
        self.reviews_table.set_rows(rows)

    def _load_images_async(self, detail, gen: int) -> None:
        urls = [detail.icon_url, *(detail.screenshots or [])[:3]]
        self.run_background(
            lambda: fetch_images(urls, timeout=6.0, thumbnail_size=320),
            lambda images: self._apply_images(gen, detail, images),
        )

    def _apply_images(self, gen: int, detail, images) -> None:
        if gen != self._detail_gen:
            return
        self.current_icon_bytes = images[0] if images else None
        self.current_screenshot_bytes = images[1:] if images else []
        self.icon_label.setPixmap(
            pixmap_from_bytes(
                self.current_icon_bytes, width=96, height=96, fallback_text=detail.title or "ICON"
            )
        )
        self._render_screenshots(self.current_screenshot_bytes)

    def _load_similar_async(self, app_id: str, country: str, lang: str, gen: int) -> None:
        self.run_background(
            lambda: self._active_service().similar(app_id, country=country, lang=lang, limit=10),
            lambda similar: self._apply_similar(gen, similar),
        )

    def _apply_similar(self, gen: int, similar) -> None:
        if gen != self._detail_gen:
            return
        self._on_similar_finished(similar)

    def _on_similar_finished(self, similar) -> None:
        self.current_similar = similar
        self.similar_table.set_rows(similar[:10])

    def _load_alerts_async(self, app_id: str, gen: int) -> None:
        # Pull this app's recent alerts off the UI thread (local DB read) so the
        # detail view isn't blocked — mirrors _load_similar_async.
        self.run_background(
            lambda: self._collect_alert_rows(app_id),
            lambda rows: self._apply_alerts(gen, rows),
        )

    def _collect_alert_rows(self, app_id: str) -> list[dict]:
        alerts = self.alert_service.list_alerts(app_id=app_id, limit=8)
        return [
            {
                "created_at": alert.created_at[5:16].replace("T", " ") if alert.created_at else "",
                "severity": alert_severity_label(alert.severity),
                "severity_raw": alert.severity,
                "type": alert_type_label(alert.type),
                "message": alert.message,
            }
            for alert in alerts
        ]

    def _apply_alerts(self, gen: int, rows: list[dict]) -> None:
        if gen != self._detail_gen:
            return
        self.alerts_table.set_rows(rows)

    @staticmethod
    def _alert_row_tint(row: dict) -> str | None:
        return ALERT_SEVERITY_COLORS.get(row.get("severity_raw"))

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

    def export_snapshots(self) -> None:
        if self.current_detail is None:
            self.show_error("请先获取应用详情。")
            return
        app_id = self.current_detail.app_id
        country = self.country_input.text().strip() or "us"
        lang = self.lang_input.text().strip() or "en"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出快照 CSV", f"{app_id}_snapshots.csv", "CSV (*.csv)"
        )
        if not path:
            return
        self.run_task(
            "正在导出...",
            lambda: self.export_service.export_app_snapshots(app_id, country, lang, path),
            lambda n: self.show_status(f"已导出 {n} 行到 {path}"),
        )

    def open_history(self) -> None:
        if self.current_detail is None:
            self.show_error("请先获取应用详情。")
            return
        self.window_api.open_history(
            self.current_detail.app_id,
            country=self.country_input.text().strip() or "us",
            lang=self.lang_input.text().strip() or "en",
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

    def _active_service(self):
        if self.window_api and getattr(self.window_api, "current_platform", "google_play") == "app_store":
            if self.app_store_service is None:
                # Wiring bug — fail loudly instead of answering with Google Play data
                # while the UI is labeled App Store.
                raise RuntimeError("App Store 服务未注入。")
            return self.app_store_service
        return self.google_play_service

    def _is_app_store(self) -> bool:
        return getattr(self.window_api, "current_platform", "google_play") == "app_store"

    def on_platform_changed(self, platform: str) -> None:
        is_as = platform == "app_store"
        # placeholder
        if is_as:
            self.app_id_input.setPlaceholderText("iTunes ID: 310633997 或 bundleId")
            self.update_subtitle("iTunes ID / Bundle ID 查询、截图和历史趋势")
        else:
            self.app_id_input.setPlaceholderText("com.whatsapp")
            self.update_subtitle("包名查询、保存快照、相似竞品和历史趋势")
        # GP-only action buttons
        self.similar_button.setVisible(not is_as)
        self.permissions_button.setVisible(not is_as)
        self.track_button.setVisible(not is_as)
        self.save_button.setVisible(not is_as)
        # GP-only metric chips
        for key, chip in self.metric_chips.items():
            chip.setVisible(key not in self._gp_only_chips or not is_as)
        # GP-only info labels
        for key, lbl in self.info_labels.items():
            lbl.setVisible(key not in self._gp_only_info or not is_as)
        # histogram section is GP-only (AS doesn't return star breakdown)
        if hasattr(self, "_histogram_card"):
            self._histogram_card.setVisible(not is_as)

    def _load_detail_core(self, app_id: str, country: str, lang: str) -> dict:
        # Only the detail itself + local history — the slow `similar` (~12s) and the
        # screenshots (~6s) are loaded asynchronously AFTER this shows, so entering the
        # detail page no longer waits on them serially.
        detail = self._active_service().app_detail(app_id, country=country, lang=lang)
        history = self.tracking_service.get_history(app_id, country=country, lang=lang)
        return {"detail": detail, "history": history, "country": country, "lang": lang}

    def _after_snapshot_saved(self, detail) -> None:
        self.current_detail = detail
        history = self.tracking_service.get_history(
            detail.app_id,
            country=self.country_input.text().strip() or "us",
            lang=self.lang_input.text().strip() or "en",
        )
        self._set_history_charts(history, detail)
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
