from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox

from app.ui.pages.base_page import BasePage
from app.ui.widgets.settings_form import SettingsFormWidget


class SettingsPage(BasePage):
    def __init__(self, services, window_api, logger):
        super().__init__(services, window_api, logger, "设置", "默认国家、语言、数据库路径和调度配置")
        self.update_service = services["update_service"]

        settings_card, settings_layout = self.create_card("全局配置")
        self.settings_form = SettingsFormWidget(services)
        settings_layout.addWidget(self.settings_form)
        self.root_layout.addWidget(settings_card)

        about_card, about_layout = self.create_card("关于 / 更新")
        self.version_label = QLabel(f"当前版本 {self.update_service.current_label()}")
        self.version_label.setStyleSheet("font-size: 14px; color: #0F172A;")
        self.check_update_button = self.create_primary_button("检查更新")
        self.check_update_button.clicked.connect(self.check_updates)
        header_row = QHBoxLayout()
        header_row.addWidget(self.version_label)
        header_row.addStretch()
        header_row.addWidget(self.check_update_button)
        about_layout.addLayout(header_row)
        self.update_status = QLabel("")
        self.update_status.setStyleSheet("font-size: 13px; color: #64748B;")
        about_layout.addWidget(self.update_status)
        self.root_layout.addWidget(about_card)
        self.root_layout.addStretch()

    def on_activated(self) -> None:
        self.settings_form.load()

    def check_updates(self) -> None:
        self.update_status.setText("正在检查...")
        self.run_task("正在检查更新...", self.update_service.check, self._on_update_checked)

    def _on_update_checked(self, result) -> None:
        if result.error:
            self.update_status.setText(f"检查更新失败：{result.error}")
            return
        if result.mode == "git":
            self._handle_git_result(result)
        else:
            self._handle_patch_result(result)

    def _handle_git_result(self, result) -> None:
        if result.up_to_date:
            self.update_status.setText("已是最新（源码 / 开发版）。")
            return
        self.update_status.setText(f"发现新版本（落后 {result.behind} 个提交）。")
        if self._confirm(
            "检查更新",
            f"发现新版本（落后 {result.behind} 个提交）。\n现在 git pull 更新并重启吗？",
        ):
            self.run_task("正在更新（git pull）...", self.update_service.git_pull, self._after_git)

    def _handle_patch_result(self, result) -> None:
        if result.up_to_date or not result.can_patch:
            self.update_status.setText(f"已是最新版本（{result.local_label}）。")
            return
        self.update_status.setText(f"发现新版本 {result.latest_label}。")
        changelog = f"{result.changelog}\n\n" if result.changelog else ""
        if self._confirm(
            "发现新版本 🎉",
            f"当前 {result.local_label} → 最新 {result.latest_label}\n\n{changelog}"
            "只下载几百 KB 代码补丁，完成后自动重启，登录态与数据都保留。\n现在更新吗？",
        ):
            self.run_task(
                "正在下载并应用更新补丁...",
                self.update_service.download_and_apply_patch,
                self._after_patch,
            )

    def _after_patch(self, _result) -> None:
        QMessageBox.information(self, "更新完成", "✅ 更新已应用，点击确定重启生效。")
        self.update_service.restart()

    def _after_git(self, result) -> None:
        ok, message = result
        if ok:
            QMessageBox.information(self, "更新完成", "✅ 更新成功，点击确定重启。")
            self.update_service.restart()
        else:
            self.update_status.setText(f"更新失败：{message}")

    def _confirm(self, title: str, message: str) -> bool:
        return (
            QMessageBox.question(
                self,
                title,
                message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        )
