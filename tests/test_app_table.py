import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.ui.widgets.app_table import AppTableWidget


def _app():
    try:
        return QApplication.instance() or QApplication([])
    except Exception:  # pragma: no cover - no Qt platform
        pytest.skip("no Qt platform available")


def test_default_order_preserved_until_sorted():
    _app()
    table = AppTableWidget([("应用名", "title"), ("评分", "rating")])
    rows = [
        {"title": "B", "rating": 4.5},
        {"title": "A", "rating": 3.0},
        {"title": "C", "rating": 5.0},
    ]
    table.set_rows(rows)
    # no header clicked yet -> the provided order is preserved
    assert [table.item(r, 0).text() for r in range(table.rowCount())] == ["B", "A", "C"]


def test_numeric_column_sorts_numerically():
    _app()
    table = AppTableWidget([("应用名", "title"), ("评分数", "ratings_count")])
    table.set_rows(
        [
            {"title": "x", "ratings_count": 9},
            {"title": "y", "ratings_count": 100},
            {"title": "z", "ratings_count": 25},
        ]
    )
    table.sortByColumn(1, Qt.SortOrder.AscendingOrder)
    assert [table.item(r, 1).text() for r in range(table.rowCount())] == ["9", "25", "100"]
    table.sortByColumn(1, Qt.SortOrder.DescendingOrder)
    assert [table.item(r, 1).text() for r in range(table.rowCount())] == ["100", "25", "9"]


def test_installs_sorts_by_min_installs_not_text():
    _app()
    table = AppTableWidget([("应用名", "title"), ("安装量", "installs")])
    table.set_rows(
        [
            {"title": "a", "installs": "1,000,000+", "min_installs": 1_000_000},
            {"title": "b", "installs": "5,000+", "min_installs": 5_000},
            {"title": "c", "installs": "50,000,000+", "min_installs": 50_000_000},
        ]
    )
    table.sortByColumn(1, Qt.SortOrder.AscendingOrder)
    assert [table.item(r, 0).text() for r in range(table.rowCount())] == ["b", "a", "c"]


def test_cell_values_are_formatted_for_display():
    _app()
    table = AppTableWidget([("评分", "rating"), ("评分数", "ratings_count"), ("内购", "has_iap")])
    table.set_rows([{"rating": 4.6699653, "ratings_count": 1234567, "has_iap": True}])
    assert table.item(0, 0).text() == "4.67"  # float -> 2 decimals
    assert table.item(0, 1).text() == "1,234,567"  # int -> thousands separators
    assert table.item(0, 2).text() == "是"  # bool -> 是/否


def test_current_row_data_maps_back_after_sort():
    _app()
    table = AppTableWidget([("应用名", "title"), ("评分", "rating")])
    rows = [
        {"title": "B", "rating": 4.5},
        {"title": "A", "rating": 3.0},
        {"title": "C", "rating": 5.0},
    ]
    table.set_rows(rows)
    table.sortByColumn(1, Qt.SortOrder.AscendingOrder)  # rating asc -> A, B, C
    table.setCurrentCell(0, 0)
    assert table.current_row_data(rows)["title"] == "A"
    table.setCurrentCell(2, 0)
    assert table.current_row_data(rows)["title"] == "C"
