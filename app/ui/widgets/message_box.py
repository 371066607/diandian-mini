from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget


def show_error(parent: QWidget, message: str) -> None:
    QMessageBox.critical(parent, "提示", message)


def show_info(parent: QWidget, message: str) -> None:
    QMessageBox.information(parent, "提示", message)
