from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel

from app.constants import APP_VERSION
from app.ui.pages.base_page import BasePage
from app.ui.widgets.settings_form import SettingsFormWidget


class SettingsPage(BasePage):
    def __init__(self, services, window_api, logger):
        super().__init__(
            services, window_api, logger, "设置", "默认国家、语言、数据库路径和调度配置"
        )

        settings_card, settings_layout = self.create_card("全局配置")
        self.settings_form = SettingsFormWidget(services)
        settings_layout.addWidget(self.settings_form)
        self.root_layout.addWidget(settings_card)

        about_card, about_layout = self.create_card("关于 / 更新")
        self.version_label = QLabel(f"当前版本 v{APP_VERSION}")
        self.version_label.setStyleSheet("font-size: 14px; color: #0F172A;")
        self.check_update_button = self.create_primary_button("检查更新")
        self.check_update_button.clicked.connect(self.check_updates)
        header_row = QHBoxLayout()
        header_row.addWidget(self.version_label)
        header_row.addStretch()
        header_row.addWidget(self.check_update_button)
        about_layout.addLayout(header_row)
        self.update_status = QLabel("")
        self.update_status.setOpenExternalLinks(True)
        self.update_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.update_status.setStyleSheet("font-size: 13px; color: #64748B;")
        about_layout.addWidget(self.update_status)
        self.root_layout.addWidget(about_card)
        self.root_layout.addStretch()

    def on_activated(self) -> None:
        self.settings_form.load()

    def check_updates(self) -> None:
        self.update_status.setText("正在检查...")
        self.run_task(
            "正在检查更新...",
            self.services["update_service"].check,
            self._on_update_checked,
        )

    def _on_update_checked(self, result) -> None:
        if result.error:
            self.update_status.setText(result.error)
        elif result.has_update and result.download_url:
            self.update_status.setText(
                f"发现新版本 {result.latest_version}（当前 v{result.current_version}）　"
                f'<a href="{result.download_url}" style="color:#2563EB;">前往下载 →</a>'
            )
        elif result.latest_version is None:
            self.update_status.setText("仓库暂无发布版本。")
        else:
            self.update_status.setText(f"已是最新版本（{result.latest_version}）。")
