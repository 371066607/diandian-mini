from __future__ import annotations

from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem


class ReviewTableWidget(QTableWidget):
    HEADERS = ["用户", "星级", "版本", "helpful", "时间", "内容"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(len(self.HEADERS))
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.verticalHeader().setVisible(False)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)

    def set_reviews(self, items) -> None:
        self.setRowCount(len(items))
        for row_index, item in enumerate(items):
            values = [
                item.user_name,
                item.rating,
                item.app_version,
                item.helpful_count,
                item.review_created_at,
                item.content,
            ]
            for column_index, value in enumerate(values):
                self.setItem(
                    row_index,
                    column_index,
                    QTableWidgetItem("" if value is None else str(value)),
                )
