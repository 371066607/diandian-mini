from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

from app.utils.image_loader import pixmap_from_bytes


class _SortableTableItem(QTableWidgetItem):
    """A cell that sorts by an explicit key so numeric columns sort numerically.

    A plain QTableWidgetItem compares its display text, which orders "100" before "9"
    and "1,000,000+" before "5,000+". Holding the real value as the sort key fixes that.
    """

    def __init__(self, text: str, sort_key: Any):
        super().__init__(text)
        self._sort_key = sort_key

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, _SortableTableItem):
            left, right = self._sort_key, other._sort_key
            if left is None:
                return False  # blanks sort to the bottom
            if right is None:
                return True
            try:
                return left < right
            except TypeError:
                return str(left) < str(right)
        return super().__lt__(other)


class AppTableWidget(QTableWidget):
    def __init__(self, columns: list[tuple[str, str]], parent=None, row_tint=None):
        super().__init__(parent)
        self.columns = columns
        # Optional ``row_tint(row) -> hex_color | None`` to colour a whole row's text
        # (e.g. high-severity alerts in red). Generic, so it stays reusable across tables.
        self._row_tint = row_tint
        self.setColumnCount(len(columns))
        self.setHorizontalHeaderLabels([label for label, _ in columns])
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.verticalHeader().setVisible(False)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        # Clicking a header sorts by that column. Start with no sort indicator so the
        # default order is the order rows are provided in (relevance / rank / recency)
        # until the user explicitly picks a column.
        self.setSortingEnabled(True)
        self.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self.horizontalHeader().setSortIndicatorShown(True)
        self.setIconSize(QSize(36, 36))
        self.verticalHeader().setDefaultSectionSize(52)
        self._icon_column_indexes = [
            index for index, (_, key) in enumerate(columns) if key == "icon"
        ]
        for index in self._icon_column_indexes:
            self.horizontalHeader().setSectionResizeMode(index, QHeaderView.ResizeMode.Fixed)
            self.setColumnWidth(index, 64)

    def set_rows(self, rows: list[Any]) -> None:
        # Disable sorting while filling so insertion isn't reordered mid-build; turning
        # it back on re-applies whatever sort column the user currently has selected
        # (a no-op when none is selected, so the provided order is preserved).
        self.setSortingEnabled(False)
        self.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            tint = self._row_tint(row) if self._row_tint is not None else None
            tint_color = QColor(tint) if tint else None
            for column_index, (_, key) in enumerate(self.columns):
                if key == "icon":
                    item = self._create_icon_item(row)
                else:
                    value = self._get_value(row, key)
                    item = _SortableTableItem(
                        self._format_display(value), self._sort_key(row, key, value)
                    )
                # remember the row's original index so a selection still maps back to
                # the right record after the visible rows have been re-sorted
                item.setData(Qt.ItemDataRole.UserRole, row_index)
                if tint_color is not None:
                    item.setForeground(tint_color)
                self.setItem(row_index, column_index, item)
        self.setSortingEnabled(True)

    def current_row_data(self, rows: list[Any]) -> Any | None:
        row = self.currentRow()
        if row < 0:
            return None
        item = self.item(row, 0)
        index = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if index is None or index < 0 or index >= len(rows):
            return None
        return rows[index]

    def _format_display(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "是" if value else "否"
        if isinstance(value, int):
            return f"{value:,}"  # thousands separators: 1000000 -> 1,000,000
        if isinstance(value, float):
            return f"{value:.2f}"  # 4.6699653 -> 4.67
        return str(value)

    def _sort_key(self, row: Any, key: str, value: Any) -> Any:
        # sort the install-band column by its numeric floor, not the "1,000,000+" text
        if key == "installs":
            minimum = self._get_value(row, "min_installs")
            if isinstance(minimum, (int, float)):
                return minimum
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return value
        if value is None:
            return None
        return str(value).casefold()

    def _get_value(self, row: Any, key: str) -> Any:
        if isinstance(row, dict):
            return row.get(key)
        return getattr(row, key, None)

    def _create_icon_item(self, row: Any) -> QTableWidgetItem:
        item = QTableWidgetItem("")
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        title = self._get_value(row, "title") or self._get_value(row, "app_id") or "APP"
        icon_bytes = self._get_icon_bytes(row)
        pixmap = pixmap_from_bytes(
            icon_bytes,
            width=36,
            height=36,
            fallback_text=str(title),
        )
        item.setData(Qt.ItemDataRole.DecorationRole, QIcon(pixmap))
        return item

    def _get_icon_bytes(self, row: Any) -> bytes | None:
        if isinstance(row, dict):
            if row.get("icon_bytes") is not None:
                return row.get("icon_bytes")
            raw = row.get("raw")
            if isinstance(raw, dict):
                return raw.get("_icon_bytes")
            return None
        icon_bytes = getattr(row, "icon_bytes", None)
        if icon_bytes is not None:
            return icon_bytes
        raw = getattr(row, "raw", None)
        if isinstance(raw, dict):
            return raw.get("_icon_bytes")
        return None
