from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
)

from app.ui.pages.base_page import BasePage
from app.ui.widgets.app_table import AppTableWidget


def _fmt_num(value) -> str:
    """Render a numeric snapshot value with thousands separators; '-' for blanks."""
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _with_arrow(text: str, delta) -> str:
    """Append a ↑/↓ arrow + signed delta to a cell when there's a non-zero change."""
    if delta is None:
        return text
    try:
        d = float(delta)
    except (TypeError, ValueError):
        return text
    if d == 0:
        return text
    arrow = "↑" if d > 0 else "↓"
    if float(d).is_integer():
        magnitude = f"{abs(int(d)):,}"
    else:
        magnitude = f"{abs(d):.2f}"
    return f"{text} {arrow}{magnitude}"


class HistoryPage(BasePage):
    """Local, offline view of a tracked app's per-day snapshot history with field-level
    day-over-day diffs. Never touches the network — it only reads what tracking has
    already persisted (``TrackingService.history_with_diffs``)."""

    _SNAPSHOT_COLUMNS = [
        ("采集时间", "captured_at"),
        ("评分", "rating_text"),
        ("评分数", "ratings_count_text"),
        ("评论数", "reviews_count_text"),
        ("真实安装", "real_installs_text"),
        ("版本", "version_text"),
        ("价格", "price_text"),
        ("含广告", "contains_ads_text"),
    ]

    _KEYWORD_COLUMNS = [
        ("关键词", "keyword"),
        ("采集时间", "captured_at"),
        ("排名", "rank_text"),
    ]

    def __init__(self, services, window_api, logger):
        super().__init__(
            services,
            window_api,
            logger,
            "监控历史",
            "本地快照明细与逐日变化（离线）",
        )
        self.tracking_service = services["tracking_service"]
        self.keyword_service = services.get("keyword_service")
        self.export_service = services["export_service"]
        # Parallel list of (app_id, country, lang) keyed by combo index; combo data holds
        # the same tuple so selection survives a reload that reorders items.
        self._apps: list = []

        toolbar_card, toolbar_layout = self.create_card()
        self.app_combo = QComboBox()
        self.app_combo.setMinimumWidth(320)
        self.app_combo.currentIndexChanged.connect(lambda _: self._on_app_changed())
        self.scope_label = QLabel("-")
        self.scope_label.setStyleSheet("color: #64748B; font-size: 13px;")
        self.refresh_button = self.create_secondary_button("刷新")
        self.export_button = self.create_secondary_button("导出当前 CSV")

        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(QLabel("应用"))
        row.addWidget(self.app_combo)
        row.addWidget(self.scope_label)
        row.addStretch()
        row.addWidget(self.refresh_button)
        row.addWidget(self.export_button)
        toolbar_layout.addLayout(row)
        self.root_layout.addWidget(toolbar_card)

        snapshots_card, snapshots_layout = self.create_card("快照明细（逐日变化）")
        self.empty_label = QLabel("暂无历史，去『监控』页同步")
        self.empty_label.setStyleSheet("color: #94A3B8; font-size: 13px;")
        snapshots_layout.addWidget(self.empty_label)
        self.snapshot_table = AppTableWidget(self._SNAPSHOT_COLUMNS)
        self.snapshot_table.setMinimumHeight(260)
        snapshots_layout.addWidget(self.snapshot_table)
        self.root_layout.addWidget(snapshots_card, 1)

        if self.keyword_service is not None:
            keyword_card, keyword_layout = self.create_card("关键词排名历史")
            self.keyword_table = AppTableWidget(self._KEYWORD_COLUMNS)
            self.keyword_table.setMinimumHeight(180)
            keyword_layout.addWidget(self.keyword_table)
            self.root_layout.addWidget(keyword_card)
        else:
            self.keyword_table = None

        self.refresh_button.clicked.connect(self.on_activated)
        self.export_button.clicked.connect(self.export_current)

    # --- App selection -------------------------------------------------------
    def _reload_apps(self) -> list:
        """Refresh the combo with the current tracked apps, preserving the selection."""
        previous = self.app_combo.currentData()
        self.app_combo.blockSignals(True)
        self.app_combo.clear()
        apps = self.tracking_service.list_apps()
        self._apps = apps
        for item in apps:
            label = item.title or item.app_id
            self.app_combo.addItem(
                f"{label} · {item.app_id}", (item.app_id, item.country, item.lang)
            )
        if previous is not None:
            index = self.app_combo.findData(previous)
            if index >= 0:
                self.app_combo.setCurrentIndex(index)
        self.app_combo.blockSignals(False)
        return apps

    def _current_key(self):
        data = self.app_combo.currentData()
        if data is None:
            return None
        return data  # (app_id, country, lang)

    def _on_app_changed(self) -> None:
        self._refresh_table()

    # --- BasePage hooks ------------------------------------------------------
    def on_activated(self) -> None:
        apps = self._reload_apps()
        self._update_scope_label()
        if not apps:
            self.snapshot_table.set_rows([])
            if self.keyword_table is not None:
                self.keyword_table.set_rows([])
            self.empty_label.setText("暂无监控应用，去『监控』页添加并同步")
            self.empty_label.setVisible(True)
            return
        self._refresh_table()

    def load_app(self, app_id: str, country: str = "us", lang: str = "en") -> None:
        """Pre-select the given app (used by cross-page jumps) and refresh."""
        self._reload_apps()
        index = self.app_combo.findData((app_id, country, lang))
        if index < 0:
            # Not currently tracked — still show its history if any snapshots exist.
            self.app_combo.blockSignals(True)
            self.app_combo.addItem(f"{app_id} · {app_id}", (app_id, country, lang))
            index = self.app_combo.count() - 1
            self.app_combo.setCurrentIndex(index)
            self.app_combo.blockSignals(False)
        else:
            self.app_combo.setCurrentIndex(index)
        self._update_scope_label()
        self._refresh_table()

    # --- Data load (pure local, off the UI thread) ---------------------------
    def _refresh_table(self) -> None:
        key = self._current_key()
        self._update_scope_label()
        if key is None:
            self.snapshot_table.set_rows([])
            if self.keyword_table is not None:
                self.keyword_table.set_rows([])
            self.empty_label.setVisible(True)
            return
        app_id, country, lang = key

        def collect() -> dict:
            snapshots = self.tracking_service.history_with_diffs(
                app_id, country=country, lang=lang
            )
            keywords = self._collect_keyword_rows(app_id, country, lang)
            return {"snapshots": snapshots, "keywords": keywords}

        self.run_background(collect, lambda payload: self._apply(payload))

    def _collect_keyword_rows(self, app_id: str, country: str, lang: str) -> list[dict]:
        if self.keyword_service is None:
            return []
        rows: list[dict] = []
        try:
            tracked = self.tracking_service.list_keywords()
        except Exception:  # pragma: no cover - defensive
            self.logger.exception("history: could not list keywords")
            return []
        for item in tracked:
            if item.app_id != app_id or item.country != country or item.lang != lang:
                continue
            try:
                history = self.keyword_service.history(item.keyword, app_id, country, lang)
            except Exception:  # pragma: no cover - defensive
                self.logger.exception("history: keyword history failed for %s", item.keyword)
                continue
            for snap in history:
                rows.append(
                    {
                        "keyword": item.keyword,
                        "captured_at": snap.captured_at,
                        "rank_text": f"#{snap.rank}" if snap.rank else "未命中",
                    }
                )
        return rows

    def _apply(self, payload: dict) -> None:
        snapshots = payload["snapshots"]
        self.empty_label.setVisible(not snapshots)
        if not snapshots:
            self.empty_label.setText("暂无历史，去『监控』页同步")
        self.snapshot_table.set_rows([self._render_snapshot_row(r) for r in snapshots])
        if self.keyword_table is not None:
            self.keyword_table.set_rows(payload["keywords"])

    @staticmethod
    def _render_snapshot_row(row: dict) -> dict:
        rating = _fmt_num(row.get("rating"))
        ratings_count = _fmt_num(row.get("ratings_count"))
        reviews_count = _fmt_num(row.get("reviews_count"))
        real_installs = _fmt_num(row.get("real_installs"))
        version = row.get("version") or "-"
        price = row.get("price") or "-"
        ads = row.get("contains_ads")
        return {
            "captured_at": (row.get("captured_at") or "")[:10],
            "rating_text": _with_arrow(rating, row.get("rating_delta")),
            "ratings_count_text": _with_arrow(ratings_count, row.get("ratings_count_delta")),
            "reviews_count_text": _with_arrow(reviews_count, row.get("reviews_count_delta")),
            "real_installs_text": _with_arrow(real_installs, row.get("real_installs_delta")),
            "version_text": f"{version} ✱" if row.get("version_changed") else version,
            "price_text": f"{price} ✱" if row.get("price_changed") else price,
            "contains_ads_text": "-" if ads is None else ("是" if ads else "否"),
        }

    def _update_scope_label(self) -> None:
        key = self._current_key()
        if key is None:
            self.scope_label.setText("-")
            return
        _, country, lang = key
        self.scope_label.setText(f"{country} / {lang}")

    # --- Export --------------------------------------------------------------
    def export_current(self) -> None:
        key = self._current_key()
        if key is None:
            self.show_error("请先选择应用。")
            return
        app_id, country, lang = key
        path, _ = QFileDialog.getSaveFileName(
            self, "导出快照 CSV", f"{app_id}_snapshots.csv", "CSV (*.csv)"
        )
        if not path:
            return
        self.run_task(
            "正在导出...",
            lambda: self.export_service.export_app_snapshots(
                app_id, country, lang, path, None, None
            ),
            lambda n: self.show_status(f"已导出 {n} 行到 {path}"),
        )
