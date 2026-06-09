from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPlainTextEdit,
    QScrollArea,
    QVBoxLayout,
)

from app.ui.pages.base_page import BasePage
from app.ui.widgets.app_table import AppTableWidget
from app.ui.widgets.settings_form import SettingsFormWidget
from app.utils.time_utils import FREQUENCY_HOURS, is_sync_due

# Auto-sync cadence: dropdown label <-> stored value.
FREQUENCY_OPTIONS = {"每日": "daily", "每周": "weekly", "手动": "manual"}
FREQUENCY_LABELS = {"daily": "每日", "weekly": "每周", "manual": "手动"}


class TrackingPage(BasePage):
    def __init__(self, services, window_api, logger):
        super().__init__(services, window_api, logger, "监控", "管理本地监控任务，同步应用和关键词")
        self.tracking_service = services["tracking_service"]
        self.settings_service = services["settings_service"]
        self.keyword_service = services["keyword_service"]
        self.chart_rank_service = services.get("chart_rank_service")
        self.export_service = services["export_service"]
        self.retention_service = services.get("history_retention_service")
        self.apps = []
        self.keywords = []
        self.chart_apps = []
        self.active_table = "app"
        # Cached app rows (pre-filter) + the currently selected tag filter ("全部" = no
        # filter). Kept on the instance so the filter dropdown can re-render locally
        # without re-querying the DB.
        self._apps_rows_cache: list[dict] = []
        self._tag_filter = "全部"

        action_card, action_layout = self.create_card()
        self.app_id_input = self.create_input("com.whatsapp", width=260)
        self.country_input = self.create_input("us", width=90)
        self.lang_input = self.create_input("en", width=90)
        self.frequency_combo = QComboBox()
        self.frequency_combo.addItems(FREQUENCY_OPTIONS.keys())
        self.frequency_combo.setMinimumWidth(90)
        self.add_app_button = self.create_secondary_button("添加 App 监控")
        self.bulk_import_button = self.create_secondary_button("批量导入")
        self.tag_input = self.create_input("标签", width=120)
        self.set_tag_button = self.create_secondary_button("设置标签")
        self.tag_filter_combo = QComboBox()
        self.tag_filter_combo.addItem("全部")
        self.tag_filter_combo.setMinimumWidth(120)
        add_row = self.create_actions_row(
            [
                self.app_id_input,
                self.country_input,
                self.lang_input,
                self.frequency_combo,
                self.add_app_button,
                self.bulk_import_button,
                self.tag_input,
                self.set_tag_button,
                QLabel("标签筛选"),
                self.tag_filter_combo,
            ]
        )
        action_layout.addLayout(add_row)

        # --- Chart-monitor add controls (reuses country/lang above) ---
        self.chart_app_id_input = self.create_input("com.whatsapp", width=200)
        self.chart_collection_combo = QComboBox()
        self.chart_collection_combo.addItems(
            ["top_free", "top_paid", "top_grossing"]
        )
        self.chart_collection_combo.setMinimumWidth(120)
        self.chart_category_input = self.create_input("APPLICATION", width=140)
        self.add_chart_button = self.create_secondary_button("添加榜单监控")
        self.remove_chart_button = self.create_secondary_button("删除榜单监控")
        chart_row = self.create_actions_row(
            [
                QLabel("榜单监控"),
                self.chart_app_id_input,
                self.chart_collection_combo,
                self.chart_category_input,
                self.add_chart_button,
                self.remove_chart_button,
            ]
        )
        action_layout.addLayout(chart_row)

        self.sync_selected_button = self.create_primary_button("同步选中")
        self.sync_all_button = self.create_secondary_button("同步全部")
        self.remove_button = self.create_secondary_button("删除监控")
        self.toggle_button = self.create_secondary_button("启用/禁用")
        self.more_button = self.create_secondary_button("更多 ▾")
        self._more_menu = QMenu(self)
        self._more_menu.addAction("同步到期项", self.sync_due)
        self._more_menu.addAction("设为所选频率", self.set_selected_frequency)
        self._more_menu.addAction("导出 CSV", self.export_selected)
        self._more_menu.addSeparator()
        self._more_menu.addAction("清理历史", self.cleanup_history)
        self.more_button.setMenu(self._more_menu)
        buttons_row = self.create_actions_row(
            [
                self.sync_selected_button,
                self.sync_all_button,
                self.remove_button,
                self.toggle_button,
                self.more_button,
            ]
        )
        action_layout.addLayout(buttons_row)

        # --- Tooltips ---
        self.app_id_input.setToolTip("应用包名，如 com.whatsapp")
        self.country_input.setToolTip("国家代码，如 us / cn / jp")
        self.lang_input.setToolTip("语言代码，如 en / zh / ja")
        self.frequency_combo.setToolTip("自动同步频率：每日 / 每周 / 手动（不自动同步）")
        self.add_app_button.setToolTip("将上方包名加入监控列表，首次同步会自动拉取应用信息")
        self.bulk_import_button.setToolTip("粘贴多个包名批量添加，每行一个，最多 200 个")
        self.tag_input.setToolTip("给选中的应用打标签，便于分组筛选（留空可清除标签）")
        self.set_tag_button.setToolTip("将标签框中的文字设置到当前选中的 App 上")
        self.tag_filter_combo.setToolTip("按标签筛选 App 监控列表，选「全部」显示所有")

        self.chart_app_id_input.setToolTip("要监控榜单排名的应用包名")
        self.chart_collection_combo.setToolTip(
            "榜单类型：top_free = 免费榜  top_paid = 付费榜  top_grossing = 畅销榜"
        )
        self.chart_category_input.setToolTip(
            "Google Play 分类代码，如 APPLICATION（全品类）、GAME、GAME_ACTION 等"
        )
        self.add_chart_button.setToolTip("添加该应用到榜单监控，定期记录其在指定榜单的排名变化")
        self.remove_chart_button.setToolTip("删除当前选中的榜单监控条目")

        self.sync_selected_button.setToolTip("立即同步当前选中的应用或关键词，不受频率限制")
        self.sync_all_button.setToolTip("立即同步全部监控项（应用 + 关键词 + 榜单），无论是否到期")
        self.remove_button.setToolTip("删除选中的监控（历史数据保留，不影响其他监控）")
        self.toggle_button.setToolTip("暂停或恢复选中监控的自动同步（禁用后不会自动拉取数据）")
        self.more_button.setToolTip("同步到期项 / 设置频率 / 导出 CSV / 清理历史")

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
                ("下次同步", "next_sync"),
                ("连续失败", "consecutive_failures"),
                ("标签", "tag"),
                ("状态", "enabled"),
            ],
            row_tint=self._fail_tint,
            column_widths=[None, None, 52, 58, 108, 108, 68, 70, 52],
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
                ("下次同步", "next_sync"),
                ("连续失败", "consecutive_failures"),
                ("状态", "enabled"),
            ],
            row_tint=self._fail_tint,
            column_widths=[None, None, 60, 52, 58, 108, 108, 68, 52],
        )
        lower_layout.addWidget(self.keywords_table)
        left_column.addWidget(lower_card)

        chart_card, chart_card_layout = self.create_card("榜单监控")
        self.chart_table = AppTableWidget(
            [
                ("App", "app_id"),
                ("榜单", "collection"),
                ("分类", "category"),
                ("国家", "country"),
                ("当前排名", "rank"),
                ("上次同步", "last_synced_at"),
                ("状态", "enabled"),
            ],
            row_tint=self._fail_tint,
            column_widths=[None, 110, None, 52, 72, 108, 52],
        )
        chart_card_layout.addWidget(self.chart_table)
        left_column.addWidget(chart_card)

        settings_card, settings_layout = self.create_card("设置")
        self.settings_form = SettingsFormWidget(services, on_saved=self.refresh)
        _scroll = QScrollArea()
        _scroll.setWidgetResizable(True)
        _scroll.setFrameShape(QFrame.Shape.NoFrame)
        _scroll.setWidget(self.settings_form)
        settings_layout.addWidget(_scroll)
        settings_card.setMinimumWidth(360)
        settings_card.setMaximumWidth(460)

        content_row.addLayout(left_column, 3)
        content_row.addWidget(settings_card, 2)
        self.root_layout.addLayout(content_row)

        self.add_app_button.clicked.connect(self.add_app_tracking)
        self.bulk_import_button.clicked.connect(self.bulk_import_open)
        self.set_tag_button.clicked.connect(self.set_selected_tag)
        self.tag_filter_combo.currentTextChanged.connect(self._on_tag_filter_changed)
        self.app_id_input.returnPressed.connect(self.add_app_tracking)
        self.sync_selected_button.clicked.connect(self.sync_selected)
        self.sync_all_button.clicked.connect(self.sync_all)
        self.remove_button.clicked.connect(self.remove_selected)
        self.toggle_button.clicked.connect(self.toggle_selected)
        self.add_chart_button.clicked.connect(self.add_chart_tracking)
        self.remove_chart_button.clicked.connect(self.remove_selected_chart)
        self.apps_table.itemSelectionChanged.connect(lambda: self._set_active_table("app"))
        self.keywords_table.itemSelectionChanged.connect(lambda: self._set_active_table("keyword"))
        self.chart_table.itemSelectionChanged.connect(lambda: self._set_active_table("chart"))

        self.apps_table.set_context_actions([
            ("同步选中", self.sync_selected),
            ("启用 / 禁用", self.toggle_selected),
            "---",
            ("查看详情", self._ctx_open_app_detail),
            ("查看历史", self._ctx_open_app_history),
            "---",
            ("删除监控", self.remove_selected),
        ])
        self.keywords_table.set_context_actions([
            ("同步选中", self.sync_selected),
            ("启用 / 禁用", self.toggle_selected),
            "---",
            ("删除监控", self.remove_selected),
        ])
        self.chart_table.set_context_actions([
            ("启用 / 禁用", self.toggle_selected),
            "---",
            ("删除榜单监控", self.remove_selected_chart),
        ])

    def _ctx_open_app_detail(self) -> None:
        row = self.apps_table.current_row_data(self.apps)
        if row:
            self.window_api.open_app_detail(row.app_id)

    def _ctx_open_app_history(self) -> None:
        row = self.apps_table.current_row_data(self.apps)
        if row:
            self.window_api.open_history(row.app_id, row.country, row.lang)

    def on_activated(self) -> None:
        self.settings_form.load()
        self.refresh()

    def refresh(self) -> None:
        self.run_background(self._collect_tracking_data, self._apply_tracking_data)

    def _collect_tracking_data(self) -> dict:
        apps = self.tracking_service.list_apps()
        keywords = self.tracking_service.list_keywords()
        chart_apps = self.tracking_service.list_chart_apps()
        settings = self.settings_service.get_all()

        # Batch-load all latest keyword ranks in one query (replaces N per-row calls).
        kw_rank_map = self.keyword_service.latest_rank_bulk(keywords)

        return {
            "apps": apps,
            "keywords": keywords,
            "chart_apps": chart_apps,
            "chart_rows": [
                {
                    "app_id": item.app_id,
                    "collection": item.collection,
                    "category": item.category or "-",
                    "country": item.country,
                    "rank": self._chart_rank_label(item),
                    "last_synced_at": self._fmt_dt(item.last_synced_at),
                    "consecutive_failures": self._fail_label(item),
                    "_fail_count": item.consecutive_failures or 0,
                    "enabled": "启用" if item.enabled else "禁用",
                }
                for item in chart_apps
            ],
            "default_country": settings["default_country"],
            "default_lang": settings["default_lang"],
            "apps_rows": [
                {
                    "title": item.title or item.app_id,
                    "app_id": item.app_id,
                    "country": item.country,
                    "frequency": FREQUENCY_LABELS.get(item.frequency, item.frequency),
                    "last_synced_at": self._fmt_dt(item.last_synced_at),
                    "next_sync": self._next_sync_label(item.last_synced_at, item.frequency),
                    "consecutive_failures": self._fail_label(item),
                    "_fail_count": item.consecutive_failures or 0,
                    "tag": item.tag or "-",
                    "enabled": "启用" if item.enabled else "禁用",
                }
                for item in apps
            ],
            "keywords_rows": [
                {
                    "keyword": item.keyword,
                    "app_id": item.app_id,
                    "rank": self._rank_label_bulk(item, kw_rank_map),
                    "country": item.country,
                    "frequency": FREQUENCY_LABELS.get(item.frequency, item.frequency),
                    "last_synced_at": self._fmt_dt(item.last_synced_at),
                    "next_sync": self._next_sync_label(item.last_synced_at, item.frequency),
                    "consecutive_failures": self._fail_label(item),
                    "_fail_count": item.consecutive_failures or 0,
                    "enabled": "启用" if item.enabled else "禁用",
                }
                for item in keywords
            ],
        }

    @staticmethod
    def _fmt_dt(iso_str: str | None) -> str:
        """Shorten an ISO datetime to 'MM-DD HH:MM' so it fits in narrow table cells."""
        if not iso_str:
            return "未同步"
        try:
            dt = datetime.fromisoformat(iso_str)
            return dt.strftime("%m-%d %H:%M")
        except (ValueError, TypeError):
            return iso_str[:10] if len(iso_str) >= 10 else iso_str

    @staticmethod
    def _fail_label(item) -> str:
        count = item.consecutive_failures or 0
        return "-" if count == 0 else f"{count} 次"

    @staticmethod
    def _fail_tint(row) -> str | None:
        # A monitor that's currently failing turns red so it's impossible to miss.
        return "#DC2626" if row.get("_fail_count", 0) > 0 else None

    def _rank_label(self, item) -> str:
        snapshot = self.keyword_service.latest_rank(
            item.keyword, item.app_id, item.country, item.lang
        )
        if snapshot is None:
            return "未同步"
        if not snapshot.found or snapshot.rank is None:
            return "未命中"
        return f"#{snapshot.rank}"

    @staticmethod
    def _rank_label_bulk(item, rank_map: dict) -> str:
        """Look up the rank from a pre-fetched bulk map — no per-row DB query."""
        snapshot = rank_map.get((item.keyword, item.app_id, item.country, item.lang))
        if snapshot is None:
            return "未同步"
        if not snapshot.found or snapshot.rank is None:
            return "未命中"
        return f"#{snapshot.rank}"

    def _chart_rank_label(self, item) -> str:
        if self.chart_rank_service is None:
            return "未同步"
        snapshot = self.chart_rank_service.latest_rank(
            item.app_id, item.collection, item.category, item.country, item.lang
        )
        if snapshot is None:
            return "未同步"
        if not snapshot.found or snapshot.rank is None:
            return "未命中"
        return f"#{snapshot.rank}"

    @staticmethod
    def _next_sync_label(
        last_synced_at: str | None,
        frequency: str | None,
        now: datetime | None = None,
    ) -> str:
        """Friendly Chinese estimate of the next auto-sync for a tracked item.

        Pure/static so it can be unit-tested with a fixed ``now``. "manual" never
        auto-syncs; a never-synced item is awaiting its first sync; otherwise reuse
        ``is_sync_due`` to decide between "已到期" and the projected next time.
        """
        freq = (frequency or "daily").lower()
        if freq == "manual":
            return "手动"
        if not last_synced_at:
            return "待首次同步"
        if is_sync_due(last_synced_at, freq, now=now):
            return "已到期"
        interval = FREQUENCY_HOURS.get(freq, FREQUENCY_HOURS["daily"])
        if interval is None:  # defensive: unknown non-manual frequency
            return "手动"
        try:
            last = datetime.fromisoformat(last_synced_at)
        except (ValueError, TypeError):
            return "待首次同步"
        return (last + timedelta(hours=interval)).strftime("%m-%d %H:%M")

    def _apply_tracking_data(self, data: dict) -> None:
        self.apps = data["apps"]
        self.keywords = data["keywords"]
        self.chart_apps = data["chart_apps"]
        self.country_input.setText(data["default_country"])
        self.lang_input.setText(data["default_lang"])
        self._apps_rows_cache = data["apps_rows"]
        self._rebuild_tag_filter()
        self._render_apps_table()
        self.keywords_table.set_rows(data["keywords_rows"])
        self.chart_table.set_rows(data["chart_rows"])

    def _rebuild_tag_filter(self) -> None:
        """Rebuild the tag-filter dropdown from the tags present in the cached app rows.

        Block signals during the rebuild so ``currentTextChanged`` doesn't fire mid-edit
        and trigger a spurious re-render. The previously selected tag is preserved when it
        still exists; otherwise the filter falls back to "全部".
        """
        tags = sorted(
            {
                row["tag"]
                for row in self._apps_rows_cache
                if row.get("tag") and row["tag"] != "-"
            }
        )
        combo = self.tag_filter_combo
        combo.blockSignals(True)
        try:
            combo.clear()
            combo.addItem("全部")
            for tag in tags:
                combo.addItem(tag)
            if self._tag_filter in tags:
                combo.setCurrentText(self._tag_filter)
            else:
                self._tag_filter = "全部"
                combo.setCurrentText("全部")
        finally:
            combo.blockSignals(False)

    def _render_apps_table(self) -> None:
        """Set the apps table to the cached rows filtered by the current tag selection."""
        if self._tag_filter == "全部":
            rows = self._apps_rows_cache
        else:
            rows = [
                row for row in self._apps_rows_cache if row.get("tag") == self._tag_filter
            ]
        self.apps_table.set_rows(rows)

    def _on_tag_filter_changed(self, text: str) -> None:
        # Lightweight local re-render off the cached rows — no DB re-query.
        self._tag_filter = text or "全部"
        self._render_apps_table()

    def set_selected_tag(self) -> None:
        target = self._selected_target()
        if target is None or target[0] != "app":
            self.show_error("请选择要打标签的 App")
            return
        row = target[1]
        tag = self.tag_input.text().strip()
        self.run_task(
            "正在设置标签...",
            lambda: self.tracking_service.set_app_tag(
                row.app_id, row.country, row.lang, tag
            ),
            lambda result: (
                self.show_status(
                    f"已设置标签「{result}」。" if result else "已清除标签。"
                ),
                self.refresh(),
            ),
        )

    def _selected_frequency(self) -> str:
        return FREQUENCY_OPTIONS.get(self.frequency_combo.currentText(), "daily")

    def add_app_tracking(self) -> None:
        app_id = self.app_id_input.text().strip()
        if not app_id:
            self.show_error("请输入要监控的包名。")
            return
        country = self.country_input.text().strip() or "us"
        lang = self.lang_input.text().strip() or "en"
        frequency = self._selected_frequency()
        self.run_task(
            "正在添加 App 监控...",
            lambda: self.tracking_service.add_app(
                app_id, country=country, lang=lang, frequency=frequency
            ),
            lambda _: (self.show_status("已添加 App 监控。"), self.refresh()),
        )

    def add_chart_tracking(self) -> None:
        app_id = self.chart_app_id_input.text().strip()
        if not app_id:
            self.show_error("请输入要监控的包名。")
            return
        collection = self.chart_collection_combo.currentText()
        category = self.chart_category_input.text().strip() or "APPLICATION"
        country = self.country_input.text().strip() or "us"
        lang = self.lang_input.text().strip() or "en"
        self.run_task(
            "正在添加榜单监控...",
            lambda: self.tracking_service.add_chart_app(
                app_id, collection, category, country, lang
            ),
            lambda _: (self.show_status("已添加榜单监控。"), self.refresh()),
        )

    def remove_selected_chart(self) -> None:
        row = self.chart_table.current_row_data(self.chart_apps)
        if row is None:
            self.show_error("请先选择要删除的榜单监控。")
            return
        self.run_task(
            "正在删除榜单监控...",
            lambda: self.tracking_service.remove_chart_app(
                row.app_id, row.collection, row.category, row.country, row.lang
            ),
            lambda _: (self.show_status("已删除榜单监控。"), self.refresh()),
        )

    def bulk_import_open(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("批量导入监控")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("每行一个包名（如 com.whatsapp）"))
        text_edit = QPlainTextEdit()
        text_edit.setPlaceholderText("com.whatsapp\ncom.facebook.katana\n...")
        text_edit.setMinimumSize(360, 240)
        layout.addWidget(text_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.Accepted:
            return

        ids = [line.strip() for line in text_edit.toPlainText().splitlines() if line.strip()]
        if not ids:
            self.show_error("请粘贴至少一个包名。")
            return
        if len(ids) > 200:
            self.show_error("一次最多导入 200 个包名。")
            return

        country = self.country_input.text().strip() or "us"
        lang = self.lang_input.text().strip() or "en"
        frequency = self._selected_frequency()
        self.run_task(
            "正在批量导入...",
            lambda: self.tracking_service.add_apps_bulk(ids, country, lang, frequency),
            self._on_bulk_imported,
        )

    def _on_bulk_imported(self, result: dict) -> None:
        added = result.get("added", 0)
        existing = result.get("existing", 0)
        failed = result.get("failed", [])
        message = f"新增 {added} 个，已存在 {existing} 个，失败 {len(failed)} 个"
        if failed:
            sample = "、".join(item.get("app_id", "?") for item in failed[:3])
            message = f"{message}（如：{sample}）"
        self.show_status(message)
        self.refresh()

    def set_selected_frequency(self) -> None:
        target = self._selected_target()
        if target is None:
            self.show_error("请先选择要设置频率的应用或关键词。")
            return
        frequency = self._selected_frequency()
        label = self.frequency_combo.currentText()
        if target[0] == "app":
            row = target[1]
            self.run_task(
                "正在设置同步频率...",
                lambda: self.tracking_service.set_app_frequency(
                    row.app_id, row.country, row.lang, frequency
                ),
                lambda _: (self.show_status(f"同步频率已设为「{label}」。"), self.refresh()),
            )
            return
        row = target[1]
        self.run_task(
            "正在设置同步频率...",
            lambda: self.tracking_service.set_keyword_frequency(
                row.keyword, row.app_id, row.country, row.lang, frequency
            ),
            lambda _: (self.show_status(f"同步频率已设为「{label}」。"), self.refresh()),
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
                self.show_status(
                    f"已同步 {result['apps']} 个应用，{result['keywords']} 个关键词，"
                    f"{result['charts']} 个榜单。"
                ),
                self.refresh(),
            ),
        )

    def sync_due(self) -> None:
        # Reproduce the scheduler's behavior on demand: only items whose cadence is due.
        self.run_task(
            "正在同步到期项...",
            lambda: self.tracking_service.sync_all(due_only=True),
            lambda result: (
                self.show_status(
                    f"到期同步：{result['apps']} 个应用，{result['keywords']} 个关键词，"
                    f"{result['charts']} 个榜单。"
                    if (result["apps"] or result["keywords"] or result["charts"])
                    else "没有到期的监控项。"
                ),
                self.refresh(),
            ),
        )

    def cleanup_history(self) -> None:
        if self.retention_service is None:
            self.show_error("历史清理服务不可用。")
            return
        from PySide6.QtWidgets import QMessageBox

        confirm = QMessageBox.question(
            self,
            "清理历史",
            "将删除超出保留窗口的历史快照/排名/告警/评论（每个对象至少保留最近若干条，删除不可逆）。确认清理？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.run_task(
            "正在清理历史...",
            self.retention_service.cleanup,
            lambda result: self.show_status(
                "已清理："
                f"快照 {result.get('snapshots', 0)}、排名 {result.get('keywords', 0)}、"
                f"榜单 {result.get('charts', 0)}、"
                f"告警 {result.get('alerts', 0)}、评论 {result.get('reviews', 0)} 条。"
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

    def export_selected(self) -> None:
        target = self._selected_target()
        if target is None or target[0] != "app":
            self.show_error("请先选择要导出的监控 App。")
            return
        row = target[1]
        app_id, country, lang = row.app_id, row.country, row.lang
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
