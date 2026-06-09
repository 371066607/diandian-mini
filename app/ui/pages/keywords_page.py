from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
)

from app.ui.pages.base_page import BasePage
from app.ui.widgets.app_table import AppTableWidget
from app.ui.widgets.chart_widget import ChartWidget
from app.utils.normalize import safe_int


class KeywordsPage(BasePage):
    def __init__(self, services, window_api, logger):
        super().__init__(services, window_api, logger, "关键词", "关键词排名查询与历史保存")
        self.keyword_service = services["keyword_service"]
        self.tracking_service = services["tracking_service"]
        self.current_result = None
        defaults = self.get_default_settings()

        controls_card, controls_layout = self.create_card()
        self.keyword_input = self.create_input("keyword: messenger")
        self.app_id_input = self.create_input("target app_id: com.whatsapp")
        self.country_input = self.create_input("us", width=100)
        self.country_input.setText(defaults["default_country"])
        self.lang_input = self.create_input("en", width=100)
        self.lang_input.setText(defaults["default_lang"])
        self.limit_input = self.create_input("limit: 100", width=120)
        self.limit_input.setText(defaults["default_limit"])
        self.fetch_button = self.create_primary_button("查询排名")
        self.save_button = self.create_secondary_button("保存排名")
        self.track_button = self.create_secondary_button("加入监控")
        self.bulk_track_button = self.create_secondary_button("批量添加关键词")

        row = self.create_actions_row(
            [
                self.keyword_input,
                self.app_id_input,
                self.country_input,
                self.lang_input,
                self.limit_input,
                self.fetch_button,
                self.save_button,
                self.track_button,
                self.bulk_track_button,
            ]
        )
        controls_layout.addLayout(row)
        self.root_layout.addWidget(controls_card)

        self.rank_label = QLabel("当前排名：暂无")
        self.rank_label.setStyleSheet("font-size: 20px; font-weight: 700; color: #0F172A;")
        self.root_layout.addWidget(self.rank_label)

        body_row = QHBoxLayout()
        chart_card, chart_layout = self.create_card("关键词排名历史")
        self.chart = ChartWidget("关键词排名历史")
        chart_layout.addWidget(self.chart)
        table_card, table_layout = self.create_card("搜索结果")
        self.table = AppTableWidget(
            [("rank", "rank"), ("App", "title"), ("app_id", "app_id"), ("评分", "rating")]
        )
        table_layout.addWidget(self.table)
        body_row.addWidget(chart_card)
        body_row.addWidget(table_card)
        self.root_layout.addLayout(body_row)

        self.fetch_button.clicked.connect(self.fetch_rank)
        self.save_button.clicked.connect(self.save_rank)
        self.track_button.clicked.connect(self.add_tracking)
        self.bulk_track_button.clicked.connect(self.bulk_add_tracking)
        self.keyword_input.returnPressed.connect(self.fetch_rank)
        self.app_id_input.returnPressed.connect(self.fetch_rank)

    @staticmethod
    def _looks_like_package(app_id: str) -> bool:
        # Android package ids always contain a dot and never a space; a display name
        # (e.g. "Hotshot AI") never equals a package id, so it would always miss.
        return "." in app_id and " " not in app_id

    def fetch_rank(self) -> None:
        keyword = self.keyword_input.text().strip()
        app_id = self.app_id_input.text().strip()
        if not keyword or not app_id:
            self.show_error("请输入关键词和目标包名。")
            return
        if not self._looks_like_package(app_id):
            self.show_error("目标请填【包名】(形如 com.example.app)，不是应用名称。")
            return
        country = self.country_input.text().strip() or "us"
        lang = self.lang_input.text().strip() or "en"
        limit = safe_int(self.limit_input.text(), 100)
        self.run_task(
            "正在查询关键词排名...",
            lambda: self.keyword_service.rank(
                keyword,
                app_id,
                country=country,
                lang=lang,
                limit=limit,
            ),
            self._on_rank_finished,
        )

    def _on_rank_finished(self, result) -> None:
        self.current_result = result
        status = f"当前排名 #{result.rank}" if result.found else "未找到目标应用"
        self.rank_label.setText(f"{status}    checked_limit: {result.checked_limit}")
        rows = []
        for index, item in enumerate(result.results, start=1):
            rows.append(
                {
                    "rank": index,
                    "title": item.title,
                    "app_id": item.app_id,
                    "rating": item.rating,
                }
            )
        self.table.set_rows(rows)
        self._refresh_history_chart()

    def save_rank(self) -> None:
        if self.current_result is None:
            self.show_error("请先查询关键词排名。")
            return
        self.run_task(
            "正在保存关键词排名...",
            lambda: self.keyword_service.save_result(self.current_result),
            lambda _: (self.show_status("关键词排名已保存"), self._refresh_history_chart()),
        )

    def add_tracking(self) -> None:
        keyword = self.keyword_input.text().strip()
        app_id = self.app_id_input.text().strip()
        if not keyword or not app_id:
            self.show_error("请输入关键词和目标包名。")
            return
        if not self._looks_like_package(app_id):
            self.show_error("目标请填【包名】(形如 com.example.app)，不是应用名称。")
            return
        self.run_task(
            "正在加入关键词监控...",
            lambda: self.tracking_service.add_keyword(
                keyword,
                app_id,
                country=self.country_input.text().strip() or "us",
                lang=self.lang_input.text().strip() or "en",
            ),
            lambda _: self.show_status("已加入关键词监控"),
        )

    def bulk_add_tracking(self) -> None:
        app_id = self.app_id_input.text().strip()
        country = self.country_input.text().strip() or "us"
        lang = self.lang_input.text().strip() or "en"

        dialog = QDialog(self)
        dialog.setWindowTitle("批量添加关键词")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("目标包名"))
        app_id_field = QLineEdit(app_id)
        app_id_field.setPlaceholderText("com.whatsapp")
        layout.addWidget(app_id_field)
        layout.addWidget(QLabel("每行一个关键词"))
        editor = QPlainTextEdit()
        editor.setMinimumSize(360, 200)
        layout.addWidget(editor)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        target = app_id_field.text().strip()
        if not target:
            self.show_error("请填写目标包名。")
            return
        keywords = [line.strip() for line in editor.toPlainText().splitlines() if line.strip()]
        if not keywords:
            self.show_error("请至少输入一个关键词。")
            return
        if len(keywords) > 200:
            self.show_error("一次最多添加 200 个关键词。")
            return
        self.run_task(
            "正在批量添加关键词...",
            lambda: self.tracking_service.add_keywords_bulk(keywords, target, country, lang),
            self._on_bulk_keywords_added,
        )

    def _on_bulk_keywords_added(self, result: dict) -> None:
        msg = (
            f"新增 {result['added']} 个，已存在 {result['existing']} 个，"
            f"失败 {len(result['failed'])} 个。"
        )
        if result["failed"]:
            sample = "、".join(item["keyword"] for item in result["failed"][:3])
            msg += f" 失败例：{sample}"
        self.show_status(msg)

    def _refresh_history_chart(self) -> None:
        if self.current_result is None:
            return
        history = self.keyword_service.history(
            self.current_result.keyword,
            self.current_result.app_id,
            country=self.current_result.country,
            lang=self.current_result.lang,
        )
        labels = [item.captured_at[5:10] for item in history]
        values = [item.rank or item.checked_limit for item in history]
        self.chart.set_series(labels, values)
