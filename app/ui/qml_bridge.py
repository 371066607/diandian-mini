from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import QObject, Property, QThreadPool, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication

from app.config import DATA_DIR
from app.constants import DEFAULT_SETTINGS
from app.db.repositories import ChartRankRepository, KeywordRankRepository, SnapshotRepository
from app.ui.controllers.alert_controller import AlertController
from app.ui.controllers.api_log_controller import ApiLogController
from app.ui.controllers.chart_controller import ChartController
from app.ui.controllers.competitor_controller import CompetitorController
from app.ui.controllers.coverage_controller import CoverageController
from app.ui.controllers.dashboard_controller import DashboardController
from app.ui.controllers.detail_controller import (
    DetailController,
    dev_links as detail_dev_links,
    dev_plain as detail_dev_plain,
    metrics as detail_metrics,
    more_info as detail_more_info,
)
from app.ui.controllers.keyword_controller import KEYWORD_RANK_CHECK_LIMIT, KeywordController
from app.ui.controllers.review_controller import ReviewController
from app.ui.controllers.search_controller import (
    SearchController,
    search_items_signature,
)
from app.ui.controllers.settings_controller import SettingsController, SettingsError
from app.ui.controllers.tracking_controller import (
    TrackingController,
    bulk_app_ids,
    is_valid_app_id,
)
from app.ui.formatting import (
    data_safety_text,
    fmt_count,
    frequency_label,
    histogram_rows,
    price_label,
    review_row,
)
from app.utils.normalize import normalize_app_id, safe_int
from app.utils.proxy_pool import ProxyPool, load_proxies
from app.utils.worker import Worker


class QmlBridge(QObject):
    dashboardChanged = Signal()
    trackingChanged = Signal()
    settingsChanged = Signal()
    alertsChanged = Signal()
    searchChanged = Signal()
    detailChanged = Signal()
    chartsChanged = Signal()
    keywordsChanged = Signal()
    reviewsChanged = Signal()
    historyChanged = Signal()
    apiLogsChanged = Signal()
    busyChanged = Signal()
    statusMessage = Signal(str)
    errorMessage = Signal(str)
    pageRequested = Signal(str)
    platformChanged = Signal()
    inputHistoryChanged = Signal()
    updateStatusChanged = Signal()
    updatePrompt = Signal(str, str)  # (title, message) -> QML confirm dialog
    updateApplied = Signal(str)  # (message) -> QML restart dialog
    coverageChanged = Signal()
    coverageProgress = Signal(str, float)  # (message, fraction 0..1) during a scan
    competitorChanged = Signal()
    monitorTreeReady = Signal("QVariant")  # async result of requestMonitorTree()
    monitorSeriesReady = Signal("QVariant")  # async result of requestMonitorSeries()
    _apiLogEntry = Signal("QVariant")

    def __init__(self, database, services: dict[str, object], logger, parent=None):
        super().__init__(parent)
        self.database = database
        self.services = services
        self.logger = logger
        self.snapshot_repository = SnapshotRepository()
        self.keyword_rank_repository = KeywordRankRepository()
        self.chart_rank_repository = ChartRankRepository()
        self._workers: list[Worker] = []
        self._busy_count = 0
        self._platform = "google_play"
        self._input_history: dict[str, list[str]] = self._load_input_history()
        self._update_status = ""
        self._pending_update: Any | None = None
        self._last_update_prompt_key = ""
        self._coverage: dict[str, Any] = self._coverage_state()
        self._competitor: dict[str, Any] = self._competitor_state()
        # Candidate pools from finished scans, keyed by (platform, app_id, country, lang, deep)
        # — a re-scan of the same identity reuses them instead of re-paying the detail +
        # autocomplete requests (the candidates only derive from slow-moving metadata).
        self._coverage_pools: dict[tuple, tuple[list[str], str | None]] = {}
        self._coverage_pool_key: tuple | None = None
        self._dashboard: dict[str, Any] = {}
        self._tracking: dict[str, Any] = {}
        # API mode starts with defaults and then refreshSettings() reads the backend.
        # Legacy/offline mode keeps the old local settings bootstrap for the first frame.
        if self._api_mode_enabled():
            self._settings: dict[str, Any] = DEFAULT_SETTINGS.copy()
        else:
            self._settings = services["settings_service"].get_all()
        self._alerts: dict[str, Any] = {"rows": []}
        self._search: dict[str, Any] = {"rows": [], "summary": "等待搜索"}
        self._detail: dict[str, Any] = {"loaded": False}
        self._charts: dict[str, Any] = {"rows": [], "summary": "等待获取榜单"}
        self._keywords: dict[str, Any] = {"rows": [], "summary": "等待查询排名"}
        self._reviews: dict[str, Any] = {"rows": [], "summary": "等待抓取评论"}
        self._history: dict[str, Any] = {"apps": [], "snapshots": [], "keywords": []}
        self._search_items: list[Any] = []
        self._search_request_id = 0
        self._detail_item: Any | None = None
        self._detail_context: dict[str, str] = {}
        self._detail_gen = 0
        self._detail_request_id = 0
        self._chart_items: list[Any] = []
        self._chart_context: dict[str, Any] = {}
        self._chart_request_id = 0
        self._monitor_tree_request_id = 0
        self._monitor_series_request_id = 0
        self._keyword_result: Any | None = None
        self._keyword_result_remote = False
        self._keyword_request_id = 0
        self._reviews_request_id = 0
        self._reviews_items: list[Any] = []
        self._reviews_context: dict[str, str] = {}
        self._reviews_token: Any | None = None
        self._history_selection: tuple[str, str, str] | None = None
        self._api_log = ApiLogController(limit=200)
        self._settings_controller = SettingsController(self.services)
        self._alert_controller = AlertController(self.services)
        self._review_controller = ReviewController(self)
        self._chart_controller = ChartController(self)
        self._keyword_controller = KeywordController(self)
        self._detail_controller = DetailController(self)
        self._search_controller = SearchController(self)
        self._coverage_controller = CoverageController(self)
        self._competitor_controller = CompetitorController(self)
        self._tracking_controller = TrackingController(self)
        self._dashboard_controller = DashboardController(self)
        self._apiLogEntry.connect(self._append_api_log_entry)
        client = self.services.get("store_intel_api_client")
        if client is not None and hasattr(client, "set_log_sink"):
            client.set_log_sink(self._queue_api_log_entry)

    @Property("QVariant", notify=dashboardChanged)
    def dashboard(self) -> dict[str, Any]:
        return self._dashboard

    @Property("QVariant", notify=trackingChanged)
    def tracking(self) -> dict[str, Any]:
        return self._tracking

    @Property("QVariant", notify=settingsChanged)
    def settings(self) -> dict[str, Any]:
        return self._settings

    @Property("QVariant", notify=alertsChanged)
    def alerts(self) -> dict[str, Any]:
        return self._alerts

    @Property("QVariant", notify=searchChanged)
    def search(self) -> dict[str, Any]:
        return self._search

    @Property("QVariant", notify=detailChanged)
    def detail(self) -> dict[str, Any]:
        return self._detail

    @Property("QVariant", notify=chartsChanged)
    def charts(self) -> dict[str, Any]:
        return self._charts

    @Property("QVariant", notify=keywordsChanged)
    def keywords(self) -> dict[str, Any]:
        return self._keywords

    @Property("QVariant", notify=reviewsChanged)
    def reviews(self) -> dict[str, Any]:
        return self._reviews

    @Property("QVariant", notify=historyChanged)
    def history(self) -> dict[str, Any]:
        return self._history

    @Property("QVariant", notify=apiLogsChanged)
    def apiLogs(self) -> list[dict[str, Any]]:
        return self._api_log.entries

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy_count > 0

    @Property(str, notify=platformChanged)
    def platform(self) -> str:
        return self._platform

    def _api_mode_enabled(self) -> bool:
        client = self.services.get("store_intel_api_client")
        return client is not None and bool(getattr(client, "enabled", False))

    @Property(str, constant=True)
    def legacyModeNotice(self) -> str:
        if self._api_mode_enabled():
            return ""
        return "诊断模式：本地抓取数据不回写服务器。"

    @Slot(str)
    def copyText(self, text: str) -> None:
        text = "" if text is None else str(text)
        if not text:
            self.errorMessage.emit("没有可复制的内容。")
            return
        QApplication.clipboard().setText(text)
        self.statusMessage.emit("已复制到剪贴板。")

    @Slot(str)
    def setPlatform(self, platform: str) -> None:
        platform = (platform or "").strip()
        if platform not in ("google_play", "app_store") or platform == self._platform:
            return
        self._platform = platform
        self.platformChanged.emit()
        self._clear_platform_results()
        if platform == "app_store":
            self.statusMessage.emit("已切换到 App Store（iTunes 官方接口）")
        else:
            self.statusMessage.emit("已切换到 Google Play")

    def _clear_platform_results(self) -> None:
        """Drop fetched rows from the previous platform — stale rows carry the other
        store's app ids, so acting on them (open detail / load more) would mis-route.
        Bumping every request counter also discards in-flight fetches started on the
        old platform, so a late result can't repopulate the page after the switch."""
        self._search_request_id += 1
        self._chart_request_id += 1
        self._keyword_request_id += 1
        self._reviews_request_id += 1
        self._search_items = []
        self._search = {"rows": [], "summary": "等待搜索"}
        self.searchChanged.emit()
        self._chart_items = []
        self._chart_context = {}
        self._charts = {"rows": [], "summary": "等待获取榜单"}
        self.chartsChanged.emit()
        self._keyword_result = None
        self._keyword_result_remote = False
        self._keywords = {"rows": [], "summary": "等待查询排名"}
        self.keywordsChanged.emit()
        self._reviews_items = []
        self._reviews_token = None
        self._reviews_context = {}
        self._reviews = {"rows": [], "summary": "等待抓取评论"}
        self.reviewsChanged.emit()
        self._detail_item = None
        self._detail_gen += 1
        self._detail = {"loaded": False}
        self.detailChanged.emit()
        self._set_coverage()
        self.coverageProgress.emit("", 0.0)

    @staticmethod
    def _coverage_state(
        *,
        rows: list | None = None,
        summary: str = "输入 App 包名 / ID 后点「发现覆盖关键词」",
        running: bool = False,
        app_id: str = "",
        country: str = "",
        lang: str = "",
    ) -> dict[str, Any]:
        """The one shape of the coverage payload — every writer goes through here so the
        QML side can rely on all keys existing."""
        return {
            "rows": rows or [],
            "summary": summary,
            "running": running,
            "appId": app_id,
            "country": country,
            "lang": lang,
        }

    def _set_coverage(self, **kwargs) -> None:
        self._coverage = self._coverage_state(**kwargs)
        self.coverageChanged.emit()

    @staticmethod
    def _competitor_state(**overrides) -> dict:
        state = {
            "mode": "single",
            "queried": False,
            "running": False,
            "appId": "",
            "competitorAppId": "",
            "country": "",
            "lang": "",
            "summary": "",
            "rows": [],
            "gapRows": [],
            "overlapRows": [],
            "exclusiveRows": [],
            "gapTotal": 0,
            "overlapTotal": 0,
            "exclusiveTotal": 0,
        }
        state.update(overrides)
        return state

    def _set_competitor(self, payload: dict) -> None:
        self._competitor = payload
        self.competitorChanged.emit()

    def _active_store(self):
        """The scraping service matching the currently selected platform."""
        if self._platform == "app_store":
            return self.services["app_store_service"]
        return self.services["google_play_service"]

    def _store_intel_api(self, platform: str | None = None):
        """Go backend adapter used in the default API shell mode. The backend now
        serves both platforms; only explicit legacy/offline mode (client.enabled
        False) falls back to _active_store()'s local scrapers.
        """
        client = self.services.get("store_intel_api_client")
        if client is not None and getattr(client, "enabled", False):
            return client
        return None

    def _queue_api_log_entry(self, entry: dict[str, Any]) -> None:
        self._apiLogEntry.emit(entry)

    @Slot("QVariant")
    def _append_api_log_entry(self, entry: Any) -> None:
        if self._api_log.append(entry):
            self.apiLogsChanged.emit()

    @Slot()
    def clearApiLogs(self) -> None:
        self._api_log.clear()
        self.apiLogsChanged.emit()

    @Property("QVariant", notify=inputHistoryChanged)
    def inputHistory(self) -> dict[str, list[str]]:
        return self._input_history

    def _load_input_history(self) -> dict[str, list[str]]:
        try:
            data = json.loads(self.services["settings_service"].get("input_history") or "{}")
        except Exception:  # pragma: no cover - corrupt value must never block startup
            return {}
        if not isinstance(data, dict):
            return {}
        return {
            str(key): [str(v) for v in values if str(v).strip()]
            for key, values in data.items()
            if isinstance(values, list)
        }

    def _remember_input(self, field: str, value: str) -> None:
        """Push a submitted value to the front of its per-platform history (max 12),
        persisting the whole map as one JSON settings row."""
        value = (value or "").strip()
        if not value:
            return
        key = f"{self._platform}:{field}"
        current = self._input_history.get(key) or []
        if current and current[0] == value:
            return
        self._input_history = {
            **self._input_history,
            key: ([value] + [v for v in current if v != value])[:12],
        }
        self.inputHistoryChanged.emit()
        payload = json.dumps(self._input_history, ensure_ascii=False)
        self._run(
            lambda: self.services["settings_service"].set_many({"input_history": payload}),
            lambda _: None,
            label="正在保存输入历史...",
            busy=False,
        )

    # --- updates -------------------------------------------------------------

    @Property(str, constant=True)
    def appVersion(self) -> str:
        service = self.services.get("update_service")
        if service is None:
            return "开发版"
        try:
            return service.current_label()
        except Exception:  # pragma: no cover - version read must never break the UI
            return "开发版"

    @Property(str, notify=updateStatusChanged)
    def updateStatus(self) -> str:
        return self._update_status

    def _set_update_status(self, text: str) -> None:
        self._update_status = text
        self.updateStatusChanged.emit()

    @Slot()
    def checkUpdates(self) -> None:
        service = self.services.get("update_service")
        if service is None:
            self._set_update_status("更新服务不可用。")
            return
        self._set_update_status("正在检查更新...")
        self._run(
            service.check,
            lambda result: self._on_update_checked(result, quiet=False),
            label="正在检查更新...",
            busy=False,
        )

    @Slot()
    def checkUpdatesQuietly(self) -> None:
        service = self.services.get("update_service")
        if service is None:
            return
        self._run(
            service.check,
            lambda result: self._on_update_checked(result, quiet=True),
            label="正在后台检查更新...",
            busy=False,
        )

    def _update_prompt_key(self, result) -> str:
        if result.mode == "git":
            return f"git:{getattr(result, 'behind', 0)}"
        return f"patch:{getattr(result, 'latest_version', 0)}"

    def _emit_update_prompt(self, result, title: str, message: str, *, quiet: bool) -> None:
        key = self._update_prompt_key(result)
        if quiet and key and key == self._last_update_prompt_key:
            return
        self._last_update_prompt_key = key
        self._pending_update = result
        self.updatePrompt.emit(title, message)

    def _on_update_checked(self, result, *, quiet: bool = False) -> None:
        if getattr(result, "error", None):
            if not quiet:
                self._set_update_status(f"检查更新失败：{result.error}")
            return
        if result.mode == "git":
            if result.up_to_date:
                self._pending_update = None
                if not quiet:
                    self._set_update_status("已是最新（源码 / 开发版）。")
                return
            self._set_update_status(f"发现新版本（落后 {result.behind} 个提交）。")
            self._emit_update_prompt(
                result,
                "检查更新",
                f"发现新版本（落后 {result.behind} 个提交）。\n现在 git pull 更新并重启吗？",
                quiet=quiet,
            )
            return
        if result.up_to_date or not result.can_patch:
            self._pending_update = None
            if not quiet:
                self._set_update_status(f"已是最新版本（{result.local_label}）。")
            return
        self._set_update_status(f"发现新版本 {result.latest_label}。")
        changelog = f"{result.changelog}\n\n" if result.changelog else ""
        self._emit_update_prompt(
            result,
            "发现新版本 🎉",
            f"当前 {result.local_label} → 最新 {result.latest_label}\n\n{changelog}"
            "只下载几百 KB 代码补丁，完成后自动重启，登录态与数据都保留。\n现在更新吗？",
            quiet=quiet,
        )

    @Slot()
    def confirmUpdate(self) -> None:
        result = self._pending_update
        service = self.services.get("update_service")
        self._pending_update = None
        if result is None or service is None:
            return
        if result.mode == "git":
            self._set_update_status("正在更新（git pull）...")
            self._run(service.git_pull, self._after_git, label="正在更新（git pull）...")
        else:
            self._set_update_status("正在下载并应用更新补丁...")
            # check() already parsed the release body: "" means it publishes no
            # checksum (skip the refetch inside download_and_apply_patch).
            expected_sha = getattr(result, "sha256", "")
            self._run(
                lambda: service.download_and_apply_patch(expected_sha256=expected_sha),
                lambda _: self._after_patch(),
                label="正在下载并应用更新补丁...",
            )

    @Slot()
    def dismissUpdate(self) -> None:
        self._pending_update = None

    def _after_git(self, result) -> None:
        ok, message = result
        if ok:
            self._set_update_status("✅ 更新成功，即将重启。")
            self.updateApplied.emit("✅ 更新成功，点击「立即重启」生效。")
        else:
            self._set_update_status(f"更新失败：{message}")

    def _after_patch(self) -> None:
        self._set_update_status("✅ 更新已应用，即将重启。")
        self.updateApplied.emit("✅ 更新已应用，点击「立即重启」生效。")

    @Slot()
    def restartApp(self) -> None:
        service = self.services.get("update_service")
        if service is not None:
            service.restart()

    @Slot()
    def refreshAll(self) -> None:
        self.refreshDashboard()
        self.refreshTracking()
        self.refreshSettings()
        self.refreshAlerts()
        self.refreshHistory()

    @Slot()
    def refreshDashboard(self) -> None:
        self._run(
            self._collect_dashboard,
            self._set_dashboard,
            label="正在刷新首页...",
            busy=False,
        )

    @Slot(result="QVariant")
    def monitorTree(self) -> dict[str, Any]:
        """App-centric tree of monitored objects: each tracked app with its own tracked
        keywords and chart positions nested under it (grouped by app_id).

        Synchronous — in API mode this issues one HTTP call per tracked keyword/chart,
        so the QML page must use requestMonitorTree() instead of blocking the UI thread."""
        return self._dashboard_controller.monitor_tree()

    @Slot()
    def requestMonitorTree(self) -> None:
        """Async monitorTree: computes off the UI thread, result arrives via
        monitorTreeReady. Guarded so an older refresh can't overwrite a newer one."""
        self._monitor_tree_request_id += 1
        self._run(
            self._dashboard_controller.monitor_tree,
            self._guarded(
                "_monitor_tree_request_id", self._monitor_tree_request_id,
                self.monitorTreeReady.emit,
            ),
            label="正在加载监控列表...",
            busy=False,
        )

    @Slot(str, str, str, str, str, int, result="QVariant")
    def monitorSeries(
        self, kind: str, app_id: str, country: str, lang: str, key: str, days: int = 30
    ) -> dict[str, Any]:
        """Time-series for a selected monitored object, ready to chart. kind: 'app'
        (rating/installs/reviews) | 'keyword' (rank) | 'chart' (rank). key: the keyword,
        or 'collection|category' for a chart. ``days`` windows to the last N days
        (<=0 = all history) — drives the date-range selector in the UI.

        Synchronous — QML uses requestMonitorSeries() to keep the UI thread free."""
        return self._dashboard_controller.monitor_series(kind, app_id, country, lang, key, days)

    @Slot(str, str, str, str, str, int)
    def requestMonitorSeries(
        self, kind: str, app_id: str, country: str, lang: str, key: str, days: int = 30
    ) -> None:
        """Async monitorSeries: result arrives via monitorSeriesReady. Guarded so
        clicking through items quickly can't apply a stale series last."""
        self._monitor_series_request_id += 1
        self._run(
            lambda: self._dashboard_controller.monitor_series(
                kind, app_id, country, lang, key, days
            ),
            self._guarded(
                "_monitor_series_request_id", self._monitor_series_request_id,
                self.monitorSeriesReady.emit,
            ),
            label="正在加载监控趋势...",
            busy=False,
        )

    def _monitor_target(
        self, kind: str, app_id: str, country: str, lang: str, key: str
    ) -> tuple[str, str, str, str, str] | None:
        kind = (kind or "").strip()
        app_id = (app_id or "").strip()
        country = (country or "").strip() or "us"
        lang = (lang or "").strip() or "en"
        key = (key or "").strip()
        if kind not in {"app", "keyword", "chart"} or not app_id:
            self.errorMessage.emit("请先选择一个监控对象。")
            return None
        if kind in {"keyword", "chart"} and not key:
            self.errorMessage.emit("请先选择一个关键词或榜单监控。")
            return None
        return kind, app_id, country, lang, key

    @Slot()
    def refreshTracking(self) -> None:
        self._run(
            self._collect_tracking,
            self._set_tracking,
            label="正在刷新监控...",
            busy=False,
        )

    @Slot()
    def refreshSettings(self) -> None:
        api = self._store_intel_api()
        self._run(
            lambda: api.get_settings()
            if api is not None
            else self.services["settings_service"].get_all(),
            self._set_settings,
            label="正在读取设置...",
            busy=False,
        )

    @Slot()
    def refreshAlerts(self) -> None:
        self._run(self._collect_alerts, self._set_alerts, label="正在刷新提醒...", busy=False)

    @Slot()
    def refreshHistory(self) -> None:
        self._run(self._collect_history, self._set_history, label="正在刷新历史...", busy=False)

    @Slot()
    def cleanupHistory(self) -> None:
        api = self._store_intel_api()
        retention_service = self.services.get("history_retention_service")
        if api is None and retention_service is None:
            self.errorMessage.emit("历史清理服务不可用。")
            return
        self._run(
            lambda: api.cleanup_history() if api is not None else retention_service.cleanup(),
            self._after_history_cleanup,
            label="正在清理历史...",
        )

    @Slot(str, str, str, str)
    def addApp(self, app_id: str, country: str, lang: str, frequency: str) -> None:
        app_id = app_id.strip()
        if not app_id:
            self.errorMessage.emit("请输入要监控的包名。")
            return
        if not is_valid_app_id(app_id, self._platform):
            if self._platform == "app_store":
                self.errorMessage.emit("App Store 目标请填数字 App ID，如 587366035。")
            else:
                self.errorMessage.emit("Google Play 目标请填包名，如 com.example.app。")
            return
        self._remember_input("app_id", app_id)
        country = country.strip() or "us"
        lang = lang.strip() or "en"
        frequency = frequency.strip() or "daily"
        platform = self._platform
        api = self._store_intel_api()
        self._run(
            lambda: self._tracking_controller.add_app(
                api, app_id, country, lang, frequency, platform
            ),
            lambda _: self._after_mutation("已添加 App 监控。"),
            label="正在添加 App 监控...",
        )

    @Slot(str, str, str, str)
    def bulkImportApps(self, raw_text: str, country: str, lang: str, frequency: str) -> None:
        app_ids = bulk_app_ids(raw_text)
        if not app_ids:
            self.errorMessage.emit("请粘贴至少一个包名。")
            return
        if len(app_ids) > 200:
            self.errorMessage.emit("一次最多导入 200 个包名。")
            return
        country = (country or "").strip() or "us"
        lang = (lang or "").strip() or "en"
        frequency = (frequency or "").strip() or "daily"
        platform = self._platform
        api = self._store_intel_api()
        self._run(
            lambda: self._tracking_controller.bulk_import(
                api, app_ids, country, lang, frequency, platform
            ),
            self._after_bulk_imported,
            label="正在批量导入...",
        )

    @Slot(str, str, str, str, str)
    def addChartApp(
        self,
        app_id: str,
        collection: str,
        category: str,
        country: str,
        lang: str,
    ) -> None:
        app_id = app_id.strip()
        if not app_id:
            self.errorMessage.emit("请输入要监控榜单的包名。")
            return
        if not is_valid_app_id(app_id, self._platform):
            if self._platform == "app_store":
                self.errorMessage.emit("App Store 目标请填数字 App ID，如 587366035。")
            else:
                self.errorMessage.emit("Google Play 目标请填包名，如 com.example.app。")
            return
        self._remember_input("app_id", app_id)
        platform = self._platform
        api = self._store_intel_api()
        self._run(
            lambda: self._tracking_controller.add_chart_app(
                api,
                app_id,
                collection.strip(),
                category.strip(),
                country.strip() or "us",
                lang.strip() or "en",
                platform,
            ),
            lambda _: self._after_mutation("已添加榜单监控。"),
            label="正在添加榜单监控...",
        )

    @Slot()
    def syncAll(self) -> None:
        api = self._store_intel_api()
        if api is not None:
            self._run(
                lambda: api.request_refresh("all", due_only=False),
                lambda job: self._after_mutation(
                    f"已提交服务器后台刷新全部监控项（任务 {getattr(job, 'job_id', '-')}）。"
                ),
                label="正在提交刷新请求...",
            )
            return
        self._run(
            lambda: self.services["tracking_service"].sync_all(False),
            lambda result: self._after_mutation(
                f"已同步 {result['apps']} 个应用，{result['keywords']} 个关键词，"
                f"{result['charts']} 个榜单。"
            ),
            label="正在同步全部监控项...",
        )

    @Slot()
    def syncDue(self) -> None:
        api = self._store_intel_api()
        if api is not None:
            self._run(
                lambda: api.request_refresh("due", due_only=True),
                lambda job: self._after_mutation(
                    f"已提交服务器后台刷新到期项（任务 {getattr(job, 'job_id', '-')}）。"
                ),
                label="正在提交刷新请求...",
            )
            return
        self._run(
            lambda: self.services["tracking_service"].sync_all(True),
            lambda result: self._after_mutation(
                f"已同步到期项：{result['apps']} 个应用，{result['keywords']} 个关键词，"
                f"{result['charts']} 个榜单。"
            ),
            label="正在同步到期项...",
        )

    @Slot(str, str, str, str, str)
    def syncMonitor(self, kind: str, app_id: str, country: str, lang: str, key: str) -> None:
        target = self._monitor_target(kind, app_id, country, lang, key)
        if target is None:
            return
        api = self._store_intel_api()
        label = "正在提交刷新请求..." if api is not None else "正在同步选中监控项..."
        self._run(
            lambda: self._tracking_controller.sync_one(api, target),
            self._after_mutation,
            label=label,
        )

    @Slot(str, str, str, str, str)
    def toggleMonitor(self, kind: str, app_id: str, country: str, lang: str, key: str) -> None:
        target = self._monitor_target(kind, app_id, country, lang, key)
        if target is None:
            return
        api = self._store_intel_api()

        def done(result: tuple[str, bool]) -> None:
            target_kind, enabled = result
            label = {"app": "应用监控", "keyword": "关键词监控", "chart": "榜单监控"}[target_kind]
            self._after_mutation(f"{label}已{'启用' if enabled else '禁用'}。")

        self._run(
            lambda: self._tracking_controller.toggle_one(api, target),
            done,
            label="正在切换监控状态...",
        )

    @Slot(str, str, str, str, str, str)
    def setMonitorFrequency(
        self, kind: str, app_id: str, country: str, lang: str, key: str, frequency: str
    ) -> None:
        target = self._monitor_target(kind, app_id, country, lang, key)
        if target is None:
            return
        target_kind = target[0]
        frequency = (frequency or "").strip() or "daily"
        if target_kind == "chart":
            self.errorMessage.emit("榜单监控暂不支持修改频率。")
            return
        api = self._store_intel_api()
        self._run(
            lambda: self._tracking_controller.set_frequency(api, target, frequency),
            lambda result: self._after_mutation(f"同步频率已设为「{frequency_label(result)}」。"),
            label="正在设置同步频率...",
        )

    @Slot(str, str, str, str, str, str)
    def setMonitorTag(
        self, kind: str, app_id: str, country: str, lang: str, key: str, tag: str
    ) -> None:
        target = self._monitor_target(kind, app_id, country, lang, key)
        if target is None:
            return
        if target[0] != "app":
            self.errorMessage.emit("只有 App 监控支持标签。")
            return
        tag = (tag or "").strip()
        api = self._store_intel_api()
        self._run(
            lambda: self._tracking_controller.set_tag(api, target, tag),
            lambda result: self._after_mutation(
                f"已设置标签「{result}」。" if result else "已清除标签。"
            ),
            label="正在设置标签...",
        )

    @Slot(str, str, str, str, str)
    def removeMonitor(self, kind: str, app_id: str, country: str, lang: str, key: str) -> None:
        target = self._monitor_target(kind, app_id, country, lang, key)
        if target is None:
            return
        api = self._store_intel_api()
        self._run(
            lambda: self._tracking_controller.remove_one(api, target),
            self._after_mutation,
            label="正在删除监控项...",
        )

    @Slot()
    def markAllAlertsRead(self) -> None:
        api = self._store_intel_api()
        self._run(
            self._alert_controller.mark_all_read_fn(api),
            lambda count: self._after_mutation(f"已标记 {count} 条为已读。"),
            label="正在标记提醒...",
        )

    @Slot(int)
    def markAlertRead(self, alert_id: int) -> None:
        if alert_id <= 0:
            self.errorMessage.emit("请先选择一条提醒。")
            return
        api = self._store_intel_api()
        self._run(
            lambda: self._alert_controller.mark_read(api, alert_id),
            lambda count: self._after_mutation(f"已标记 {count} 条为已读。"),
            label="正在标记提醒...",
        )

    @Slot(str)
    def setTheme(self, name: str) -> None:
        """Persist + apply the UI accent theme. A cheap local write; emits
        settingsChanged so the QML palette (bound to settings.theme) recolors live."""
        name = (name or "").strip() or "teal"
        api = self._store_intel_api()
        if api is None:
            try:
                self.services["settings_service"].set_many({"theme": name})
            except Exception:  # noqa: BLE001
                pass
        else:
            self._run(
                lambda: api.set_settings({"theme": name}),
                self._set_settings,
                label="正在保存主题...",
                busy=False,
            )
        self._settings = {**self._settings, "theme": name}
        self.settingsChanged.emit()

    @Slot("QVariant")
    def saveSettings(self, payload) -> None:
        values = self._to_dict(payload)
        api = self._store_intel_api()
        current = (
            dict(self._settings) if api is not None else self.services["settings_service"].get_all()
        )
        try:
            updates = self._settings_controller.build_updates(current, values)
        except SettingsError as exc:
            self.errorMessage.emit(str(exc))
            return

        def save() -> None:
            if api is not None:
                api.set_settings(updates)
            else:
                self._settings_controller.apply_legacy(updates)
            self._settings_controller.reload_scheduler()

        self._run(save, lambda _: self._after_mutation("设置已保存。"), label="正在保存设置...")

    @Slot(str, str, str, str)
    def searchApps(self, keyword: str, country: str, lang: str, limit: str) -> None:
        keyword = keyword.strip()
        if not keyword:
            self.errorMessage.emit("请输入搜索关键词。")
            return
        self._remember_input("search_keyword", keyword)
        api = self._store_intel_api()
        country_value = country.strip() or "us"
        lang_value = lang.strip() or "en"
        limit_value = safe_int(limit, 50)
        platform = self._platform
        self._search_request_id += 1
        request_id = self._search_request_id

        def search():
            payload = self._search_controller.search(
                keyword, country_value, lang_value, limit_value, platform
            )
            payload["request_id"] = request_id
            return payload

        def finish(payload):
            self._set_search_result_payload(payload)
            if (
                api is not None
                and isinstance(payload, dict)
                and payload.get("refresh_in_background")
                and payload.get("request_id") == self._search_request_id
            ):
                self._refresh_search_cache_in_background(
                    api,
                    request_id,
                    keyword,
                    country_value,
                    lang_value,
                    limit_value,
                    platform,
                )

        self._run(
            search,
            finish,
            label="正在搜索应用...",
        )

    @Slot(int, str, str)
    def openSearchResult(self, index: int, country: str, lang: str) -> None:
        item = self._item_at(self._search_items, index, "请先选择一条搜索结果。")
        if item is None:
            return
        self.pageRequested.emit("app_detail")
        self.fetchAppDetail(item.app_id, country, lang)

    @Slot(int, str, str)
    def addSearchResultTracking(self, index: int, country: str, lang: str) -> None:
        item = self._item_at(self._search_items, index, "请先选择一条搜索结果。")
        if item is None:
            return
        item_platform = getattr(item, "platform", "google_play") or "google_play"
        api = self._store_intel_api()
        self._run(
            lambda: (
                api.add_tracked_app(
                    item.app_id,
                    country.strip() or "us",
                    lang.strip() or "en",
                    platform=item_platform,
                )
                if api is not None
                else self.services["tracking_service"].add_app(
                    item.app_id,
                    country.strip() or "us",
                    lang.strip() or "en",
                )
            ),
            lambda _: self._after_mutation("已加入 App 监控。"),
            label="正在加入监控...",
        )

    @Slot(str, str, str)
    def fetchAppDetail(self, app_id: str, country: str, lang: str) -> None:
        app_id = app_id.strip()
        if not app_id:
            self.errorMessage.emit("请输入包名。")
            return
        self._remember_input("app_id", app_id)
        context = {
            "country": country.strip() or "us",
            "lang": lang.strip() or "en",
        }
        self._detail_context = context
        self._detail_request_id += 1
        request_id = self._detail_request_id
        platform = self._platform
        self._run(
            lambda: self._detail_controller.fetch(app_id, context, platform, request_id),
            self._set_detail_payload,
            label="正在获取应用详情...",
        )

    @Slot()
    def fetchDetailPermissions(self) -> None:
        if self._detail_item is None:
            self.errorMessage.emit("请先获取应用详情。")
            return
        app_id = self._detail_item.app_id
        ctx = self._detail_context or {"country": "us", "lang": "en"}
        gen = self._detail_gen
        api = self._store_intel_api(getattr(self._detail_item, "platform", "google_play"))
        self._run(
            lambda: (
                getattr(self._detail_item, "permissions", {}) or {}
                if api is not None
                else self.services["google_play_service"].permissions(
                    app_id, country=ctx["country"], lang=ctx["lang"]
                )
            ),
            lambda data: self._apply_detail_permissions(gen, data),
            label="正在获取权限...",
        )

    @Slot(str, str)
    def saveDetailSnapshot(self, country: str, lang: str) -> None:
        if self._detail_item is None:
            self.errorMessage.emit("请先获取应用详情。")
            return
        app_id = self._detail_item.app_id
        platform = getattr(self._detail_item, "platform", "google_play") or "google_play"
        api = self._store_intel_api()
        if api is not None:
            self._run(
                lambda: api.request_refresh(
                    "app",
                    app_id=app_id,
                    country=country.strip() or "us",
                    lang=lang.strip() or "en",
                    platform=platform,
                ),
                lambda job: self._after_mutation(
                    f"已请求服务器刷新应用快照（任务 {getattr(job, 'job_id', '-')}）。"
                ),
                label="正在提交刷新请求...",
            )
            return
        gen = self._detail_gen
        self._run(
            lambda: self.services["tracking_service"].sync_app_now(
                app_id,
                country=country.strip() or "us",
                lang=lang.strip() or "en",
            ),
            lambda detail: self._after_detail_saved(detail, gen),
            label="正在保存快照...",
        )

    @Slot(str, str)
    def addDetailTracking(self, country: str, lang: str) -> None:
        if self._detail_item is None:
            self.errorMessage.emit("请先获取应用详情。")
            return
        app_id = self._detail_item.app_id
        platform = getattr(self._detail_item, "platform", "google_play") or "google_play"
        api = self._store_intel_api()
        self._run(
            lambda: (
                api.add_tracked_app(
                    app_id, country.strip() or "us", lang.strip() or "en", platform=platform
                )
                if api is not None
                else self.services["tracking_service"].add_app(
                    app_id,
                    country.strip() or "us",
                    lang.strip() or "en",
                )
            ),
            lambda _: self._after_mutation("已加入 App 监控。"),
            label="正在加入监控...",
        )

    @Slot(str, str)
    def openDetailHistory(self, country: str, lang: str) -> None:
        if self._detail_item is None:
            self.errorMessage.emit("请先获取应用详情。")
            return
        self._history_selection = (
            self._detail_item.app_id,
            country.strip() or "us",
            lang.strip() or "en",
        )
        self.pageRequested.emit("history")
        self.refreshHistory()

    @Slot(str, str, str)
    def openStore(self, app_id: str, country: str, lang: str) -> None:
        target_url = ""
        if self._detail_item is not None and getattr(self._detail_item, "store_url", None):
            target_url = self._detail_item.store_url or ""
        elif app_id.strip():
            ident = app_id.strip()
            if self._platform == "app_store":
                if not ident.isdigit():
                    self.errorMessage.emit("App Store 链接需要数字 App ID，请先获取详情。")
                    return
                target_url = f"https://apps.apple.com/{country.strip() or 'us'}/app/id{ident}"
            else:
                target_url = (
                    "https://play.google.com/store/apps/details?"
                    f"id={ident}&gl={country.strip() or 'us'}&hl={lang.strip() or 'en'}"
                )
        if not target_url:
            self.errorMessage.emit("请先输入或获取包名。")
            return
        QDesktopServices.openUrl(QUrl(target_url))

    @Slot(str, str, str, str, str)
    def fetchChart(
        self, chart_type: str, category: str, country: str, lang: str, limit: str
    ) -> None:
        self._chart_context = {
            "chart_type": chart_type.strip() or "top_free",
            "category": category.strip() or None,
            "country": country.strip() or "us",
            "lang": lang.strip() or "en",
            "platform": self._platform,
        }
        if self._chart_context["category"]:
            self._remember_input("chart_category", self._chart_context["category"])
        self._chart_request_id += 1
        context = self._chart_context
        self._run(
            lambda: self._chart_controller.fetch(context, safe_int(limit, 100)),
            self._guarded("_chart_request_id", self._chart_request_id, self._set_chart_result_payload),
            label="正在获取榜单...",
        )

    @Slot()
    def saveChartSnapshot(self) -> None:
        if not self._chart_items:
            self.errorMessage.emit("请先获取榜单。")
            return
        ctx = self._chart_context or {
            "chart_type": "top_free",
            "category": None,
            "country": "us",
            "lang": "en",
            "platform": self._platform,
        }
        api = self._store_intel_api(ctx.get("platform"))
        if api is not None:
            self.statusMessage.emit("API 模式下榜单快照由服务器后台维护。")
            return
        self._run(
            lambda: self._chart_controller.save_legacy(ctx, self._chart_items),
            lambda count: self._after_mutation(f"已保存 {count} 条榜单快照。"),
            label="正在保存榜单快照...",
        )

    @Slot(int, str, str)
    def openChartResult(self, index: int, country: str, lang: str) -> None:
        item = self._item_at(self._chart_items, index, "请先选择一条榜单记录。")
        if item is None:
            return
        self.pageRequested.emit("app_detail")
        self.fetchAppDetail(item.app_id, country, lang)

    @Slot(str, str, str, str, str)
    def fetchKeywordRank(
        self, keyword: str, app_id: str, country: str, lang: str, limit: str
    ) -> None:
        if not keyword.strip() or not app_id.strip():
            self.errorMessage.emit("请输入关键词和目标包名。")
            return
        keyword_value = keyword.strip()
        app_id_value = app_id.strip()
        self._remember_input("keyword", keyword_value)
        self._remember_input("app_id", app_id_value)
        platform = self._platform
        api = self._store_intel_api()
        self._keyword_request_id += 1
        request_id = self._keyword_request_id
        if api is not None:
            self._run(
                lambda: self._keyword_controller.fetch_rank_api(
                    api,
                    keyword_value,
                    app_id_value,
                    country.strip() or "us",
                    lang.strip() or "en",
                    platform,
                ),
                self._guarded("_keyword_request_id", request_id, self._set_keyword_payload_from_api),
                label="正在同步关键词排名...",
            )
            return
        self._run(
            lambda: self._keyword_controller.fetch_rank_legacy(
                keyword.strip(),
                app_id.strip(),
                country.strip() or "us",
                lang.strip() or "en",
                self._platform,
            ),
            self._guarded("_keyword_request_id", request_id, self._set_keyword_result),
            label="正在查询关键词排名...",
        )

    @Slot()
    def saveKeywordRank(self) -> None:
        if self._keyword_result is None:
            self.errorMessage.emit("请先查询关键词排名。")
            return
        if self._keyword_result_remote:
            self._after_mutation("关键词排名已保存。")
            return
        self._run(
            lambda: self._keyword_controller.save_legacy(self._keyword_result),
            lambda _: self._after_mutation("关键词排名已保存。"),
            label="正在保存关键词排名...",
        )

    @Slot(str, str, str, str)
    def addKeywordTracking(self, keyword: str, app_id: str, country: str, lang: str) -> None:
        keyword = keyword.strip()
        app_id = app_id.strip()
        if not keyword or not app_id:
            self.errorMessage.emit("请输入关键词和目标 App。")
            return
        platform = self._platform
        if platform == "app_store":
            if not app_id.isdigit():
                self.errorMessage.emit("App Store 目标请填数字 App ID，如 587366035。")
                return
        elif "." not in app_id or " " in app_id:
            self.errorMessage.emit("目标请填包名，形如 com.example.app。")
            return
        self._remember_input("keyword", keyword)
        self._remember_input("app_id", app_id)
        api = self._store_intel_api(platform)
        self._run(
            lambda: (
                api.add_tracked_keyword(
                    keyword,
                    app_id,
                    country=country.strip() or "us",
                    lang=lang.strip() or "en",
                    platform=platform,
                )
                if api is not None
                else self.services["tracking_service"].add_keyword(
                    keyword,
                    app_id,
                    country=country.strip() or "us",
                    lang=lang.strip() or "en",
                    platform=platform,
                )
            ),
            lambda _: self._after_mutation("已加入关键词监控。"),
            label="正在加入关键词监控...",
        )

    # --- keyword coverage ("what keywords can find my app") ------------------

    @Property("QVariant", notify=coverageChanged)
    def coverage(self) -> dict[str, Any]:
        return self._coverage

    @Property("QVariant", notify=competitorChanged)
    def competitor(self) -> dict[str, Any]:
        return self._competitor

    @Slot(str, str, str, bool)
    def discoverCoverage(self, app_id: str, country: str, lang: str, deep: bool = False) -> None:
        if self._coverage.get("running"):
            self.statusMessage.emit("已有覆盖扫描进行中，请等待其完成。")
            return
        app_id = app_id.strip()
        if not app_id:
            self.errorMessage.emit("请输入要分析的 App 包名 / ID。")
            return
        self._remember_input("app_id", app_id)
        country = country.strip() or "us"
        lang = lang.strip() or "en"
        platform = self._platform
        # deep scans expand autocomplete one level further, so they build a different
        # (larger) candidate set — cache them separately from shallow scans.
        pool_key = (platform, normalize_app_id(app_id), country, lang, deep)
        self._coverage_pool_key = pool_key
        cached_pool = self._coverage_pools.get(pool_key)
        api = self._store_intel_api(platform)
        proxy_pool = None
        max_workers = 1
        if api is None:
            # Build a proxy pool from settings + data/proxies.txt. Concurrency is honoured
            # ONLY when proxies exist — parallel same-IP scraping just multiplies ban risk.
            proxies = load_proxies(self.services.get("settings_service"), DATA_DIR)
            proxy_pool = ProxyPool(proxies) if proxies else None
            max_workers = self._coverage_controller.concurrency() if proxy_pool else 1
            if proxy_pool:
                self.statusMessage.emit(
                    f"覆盖扫描启用 {len(proxy_pool)} 个代理 · {max_workers} 并发"
                )
        self._set_coverage(
            summary="正在深度挖掘覆盖关键词，请稍候..."
            if deep
            else "正在分析覆盖关键词，请稍候...",
            running=True,
            app_id=app_id,
            country=country,
            lang=lang,
        )
        # Reset the progress card immediately — otherwise it briefly replays the
        # previous scan's final "覆盖检测 N/N" text until the worker's first tick.
        self.coverageProgress.emit("正在生成候选关键词...", 0.0)

        def work():
            try:
                result = self._coverage_controller.analyze(
                    api, app_id, country, lang, deep, platform, cached_pool, proxy_pool, max_workers
                )
                return ("ok", result)
            except Exception as exc:  # surface a clean message, never leave it "running"
                return ("error", str(exc))

        # busy=False: a coverage scan runs ~1-2 min, so use inline progress (the
        # CoveragePage shows a bar) instead of blocking the whole UI with the overlay.
        self._run(work, self._on_coverage_done, label="正在分析覆盖关键词...", busy=False)

    def _on_coverage_done(self, payload) -> None:
        status, value = payload
        previous = self._coverage
        if status == "error":
            self._set_coverage(
                summary=f"分析失败：{value}",
                app_id=previous.get("appId", ""),
                country=previous.get("country", ""),
                lang=previous.get("lang", ""),
            )
            self.errorMessage.emit(f"覆盖分析失败：{value}")
            return
        pool_key = self._coverage_pool_key or (
            value.platform,
            normalize_app_id(value.app_id),
            value.country,
            value.lang,
            False,
        )
        self._coverage_pools[pool_key] = (value.candidates, value.canonical_app_id)
        rows = [{"keyword": c["keyword"], "rank": c["rank"]} for c in value.covered]
        self._set_coverage(
            rows=rows,
            summary=(
                f"共扫描 {value.candidate_count} 个候选词，命中 {len(rows)} 个覆盖关键词"
                f"（排名 ≤ {value.checked_limit}）"
            ),
            # Prefer the store's canonical id: it is what "加入监控" must be keyed on
            # (an App Store Bundle-ID input resolves to the numeric trackId here).
            app_id=value.canonical_app_id or value.app_id,
            country=value.country,
            lang=value.lang,
        )

    @Slot(str, str, str, str)
    def analyzeCompetitor(
        self, app_id: str, competitor_app_id: str, country: str, lang: str
    ) -> None:
        if self._competitor.get("running"):
            self.statusMessage.emit("已有竞品词查询进行中，请等待其完成。")
            return
        app_id = (app_id or "").strip()
        competitor_app_id = (competitor_app_id or "").strip()
        self._remember_input("app_id", app_id)
        if competitor_app_id:
            self._remember_input("app_id", competitor_app_id)
        country = (country or "").strip() or "us"
        lang = (lang or "").strip() or "en"
        label = "正在对比竞品关键词..." if competitor_app_id else "正在反查关键词覆盖..."
        # Reset to a running placeholder before the request lands — otherwise the
        # previous query's rows/tables stay bound to the UI (and selectable/
        # trackable) for the entire duration of this new, un-cached, synchronous
        # request, same as discoverCoverage's pre-run _set_coverage(...).
        self._set_competitor(self._competitor_state(running=True, summary=label))

        def work():
            try:
                return ("ok", self._competitor_controller.analyze(
                    self._store_intel_api(),
                    app_id,
                    competitor_app_id,
                    country,
                    lang,
                    self._platform,
                ))
            except Exception as exc:  # surface a clean message, never leave it "running"
                return ("error", str(exc))

        def on_done(payload):
            status, value = payload
            if status == "error":
                self._set_competitor(self._competitor_state(
                    appId=app_id, competitorAppId=competitor_app_id,
                    country=country, lang=lang,
                ))
                self.errorMessage.emit(value)
                return
            self._set_competitor({**value, "running": False})

        self._run(work, on_done, label=label, busy=False)

    @Slot(str, str, str, str)
    def fetchReviews(self, app_id: str, country: str, lang: str, sort: str) -> None:
        app_id = app_id.strip()
        if not app_id:
            self.errorMessage.emit("请输入包名。")
            return
        self._remember_input("app_id", app_id)
        self._reviews_context = {
            "app_id": app_id,
            "country": country.strip() or "us",
            "lang": lang.strip() or "en",
            "sort": sort.strip() or "newest",
            "platform": self._platform,
        }
        self._reviews_items = []
        self._reviews_token = None
        self._reviews_request_id += 1
        context = self._reviews_context
        self._run(
            lambda: self._review_controller.fetch_page(context, None),
            self._guarded("_reviews_request_id", self._reviews_request_id, self._set_reviews_result),
            label="正在获取评论...",
        )

    @Slot()
    def loadMoreReviews(self) -> None:
        ctx = self._reviews_context
        token = self._reviews_token
        if not ctx.get("app_id") or token is None:
            self.errorMessage.emit("没有更多评论可加载。")
            return
        # Same counter as fetchReviews: a new fetch (or platform switch) makes any
        # in-flight load-more page stale — its items belong to the old listing.
        self._run(
            lambda: self._review_controller.fetch_page(ctx, token),
            self._guarded(
                "_reviews_request_id", self._reviews_request_id, self._append_reviews_result
            ),
            label="正在加载更多评论...",
        )

    @Slot(str, str, str)
    def saveReviews(self, app_id: str, country: str, lang: str) -> None:
        app_id = (app_id or self._reviews_context.get("app_id", "")).strip()
        country = (country or self._reviews_context.get("country", "")).strip() or "us"
        lang = (lang or self._reviews_context.get("lang", "")).strip() or "en"
        if not app_id or not self._reviews_items:
            self.errorMessage.emit("请先获取评论。")
            return
        reviews_platform = self._reviews_context.get("platform") or "google_play"
        self._run(
            lambda: self._review_controller.save(
                app_id, country, lang, self._reviews_items, reviews_platform
            ),
            lambda saved: self._after_mutation(f"新保存 {saved} 条评论。"),
            label="正在保存评论...",
        )

    @Slot(int)
    def loadHistoryIndex(self, index: int) -> None:
        apps = self._history.get("apps") or []
        if index < 0 or index >= len(apps):
            return
        row = apps[index]
        self._history_selection = (
            row.get("appId", ""),
            row.get("country", "us"),
            row.get("lang", "en"),
        )
        self.refreshHistory()

    def notify(self, alerts) -> None:
        self.statusMessage.emit(f"后台同步产生 {len(alerts)} 条新提醒。")
        self.refreshDashboard()
        self.refreshAlerts()

    def _run(self, fn, on_success, *, label: str, busy: bool = True) -> None:
        worker = Worker(fn)
        self._workers.append(worker)

        if busy:
            self._busy_count += 1
            self.busyChanged.emit()
            self.statusMessage.emit(label)

        def finish(result):
            try:
                on_success(result)
            finally:
                self._finish_worker(worker, busy)

        def fail(message: str):
            self.errorMessage.emit(message)
            self._finish_worker(worker, busy)

        worker.signals.finished.connect(finish)
        worker.signals.error.connect(fail)
        QThreadPool.globalInstance().start(worker)

    def _request_api_refresh(self, api, kind: str, **kwargs):
        job = api.request_refresh(kind, **kwargs)
        job_id = getattr(job, "job_id", "") or getattr(job, "id", "")
        if job_id:
            job = api.wait_refresh_job(job_id, timeout=60.0, interval=1.0)
        if str(getattr(job, "status", "")).lower() == "failed":
            message = getattr(job, "error", "") or getattr(job, "message", "")
            raise RuntimeError(message or "服务器刷新任务失败。")
        return job

    def _refresh_search_cache_in_background(
        self,
        api,
        request_id: int,
        keyword: str,
        country: str,
        lang: str,
        limit: int,
        platform: str = "google_play",
    ) -> None:
        def refresh():
            return {
                "items": self._search_controller.refresh_cache(
                    api, keyword, country, lang, limit, platform
                ),
                "request_id": request_id,
            }

        def finish(payload):
            if (
                not isinstance(payload, dict)
                or payload.get("request_id") != self._search_request_id
            ):
                return
            items = payload.get("items") or []
            if not items:
                return
            if search_items_signature(items) == search_items_signature(self._search_items):
                self.statusMessage.emit("搜索结果已是最新。")
                return
            self._set_search_results(items)
            self.statusMessage.emit("搜索结果已刷新。")

        self._run(
            refresh,
            finish,
            label="正在后台刷新搜索结果...",
            busy=False,
        )

    def _finish_worker(self, worker: Worker, busy: bool) -> None:
        if worker in self._workers:
            self._workers.remove(worker)
        if busy:
            self._busy_count = max(0, self._busy_count - 1)
            self.busyChanged.emit()

    def _after_mutation(self, message: str) -> None:
        self.statusMessage.emit(message)
        self.refreshDashboard()
        self.refreshTracking()
        self.refreshSettings()
        self.refreshAlerts()
        self.refreshHistory()

    def _after_bulk_imported(self, result: dict[str, Any]) -> None:
        failed = result.get("failed", [])
        message = (
            f"新增 {result.get('added', 0)} 个，已存在 {result.get('existing', 0)} 个，"
            f"失败 {len(failed)} 个"
        )
        if failed:
            sample = "、".join(str(item.get("app_id", "?")) for item in failed[:3])
            message = f"{message}（如：{sample}）"
        self._after_mutation(message)

    def _after_history_cleanup(self, result: dict[str, Any]) -> None:
        message = (
            f"已清理：快照 {int(result.get('snapshots') or 0)}、"
            f"排名 {int(result.get('keywords') or 0)}、"
            f"榜单 {int(result.get('charts') or 0)}、"
            f"告警 {int(result.get('alerts') or 0)}、"
            f"评论 {int(result.get('reviews') or 0)} 条。"
        )
        self._after_mutation(message)

    def _after_detail_saved(self, detail, gen: int) -> None:
        # The save succeeded either way, but only refresh the on-screen detail if
        # the user is still looking at the same app (guards navigate-away races).
        if gen == self._detail_gen:
            self._set_detail_result(detail)
        self._after_mutation("快照已保存。")

    def _collect_dashboard(self) -> dict[str, Any]:
        return self._dashboard_controller.collect_dashboard()

    def _collect_tracking(self) -> dict[str, Any]:
        return self._dashboard_controller.collect_tracking()

    def _collect_alerts(self) -> dict[str, Any]:
        return self._alert_controller.collect(self._store_intel_api())

    def _collect_history(self) -> dict[str, Any]:
        return self._dashboard_controller.collect_history()

    def _set_dashboard(self, data: dict[str, Any]) -> None:
        self._dashboard = data
        self.dashboardChanged.emit()

    def _set_tracking(self, data: dict[str, Any]) -> None:
        self._tracking = data
        self.trackingChanged.emit()

    def _set_settings(self, data: dict[str, Any]) -> None:
        self._settings = data
        self.settingsChanged.emit()

    def _set_alerts(self, data: dict[str, Any]) -> None:
        self._alerts = data
        self.alertsChanged.emit()

    def _set_history(self, data: dict[str, Any]) -> None:
        self._history = data
        self.historyChanged.emit()

    def _set_search_results(self, items) -> None:
        self._search_items = list(items)
        rows = [
            {
                "iconUrl": getattr(item, "icon_url", "") or "",
                "title": getattr(item, "title", "") or getattr(item, "app_id", ""),
                "appId": getattr(item, "app_id", ""),
                "developer": getattr(item, "developer", "") or "-",
                "rating": (
                    getattr(item, "rating", None)
                    if getattr(item, "rating", None) is not None
                    else "-"
                ),
                "ratings": fmt_count(getattr(item, "ratings_count", None)),
                "installs": getattr(item, "installs", "") or "-",
                "price": getattr(item, "price", "") or "免费",
                "hasIap": "内购" if getattr(item, "has_iap", False) else "",
                "category": getattr(item, "category", "") or "-",
                "summary": getattr(item, "summary", "") or "-",
            }
            for item in items
        ]
        self._search = {"rows": rows, "summary": f"已获取 {len(rows)} 条搜索结果"}
        self.searchChanged.emit()

    def _set_search_result_payload(self, payload) -> None:
        if isinstance(payload, dict):
            self._set_search_results(payload.get("items") or [])
            return
        self._set_search_results(payload)

    def _set_detail_payload(self, payload) -> None:
        if isinstance(payload, dict):
            if payload.get("request_id") != self._detail_request_id:
                return
            detail = payload.get("detail")
            if detail is not None:
                self._set_detail_result(detail)
                return
        self._set_detail_result(payload)

    def _set_detail_result(self, item) -> None:
        self._detail_item = item
        self._detail_gen += 1
        gen = self._detail_gen
        is_ios = item.platform == "app_store"
        api = self._store_intel_api(getattr(item, "platform", "google_play"))
        monetization = self.services.get("monetization_service")
        score: dict[str, Any] = {"score": 0, "signals": [], "note": ""}
        if monetization is not None and not is_ios:
            try:
                score = monetization.score(item)
            except Exception:  # pragma: no cover - defensive; scoring must not break detail
                pass
        self._detail = {
            "loaded": True,
            # --- hero ---
            "title": item.title or item.app_id,
            "appId": item.app_id,
            "developer": item.developer or "-",
            "developerId": item.developer_id or "",
            "iconUrl": item.icon_url or "",
            "headerImage": item.header_image or "",
            "categories": list(item.categories or ([] if not item.category else [item.category])),
            "summary": item.summary or "",
            "storeUrl": item.store_url or "",
            "priceLabel": price_label(item),
            "available": item.available,
            # --- metric chips (label/value computed bridge-side; QML just repeats) ---
            "metrics": detail_metrics(item),
            # --- rating histogram ---
            "histogram": histogram_rows(item.histogram),
            # --- developer / links ---
            "devLinks": detail_dev_links(item, is_ios),
            "devPlain": detail_dev_plain(item, is_ios),
            # --- more info ---
            "moreInfo": detail_more_info(item, is_ios),
            "contentRatingDescription": item.content_rating_description or "",
            "dataSafety": data_safety_text(item.data_safety),
            # --- monetization ---
            "monetizationScore": score.get("score", 0),
            "monetizationNote": "；".join(score.get("signals", [])[:3]) or score.get("note", ""),
            # --- media / text ---
            "screenshots": list(item.screenshots or []),
            "video": item.video or "",
            "videoImage": item.video_image or "",
            "description": (item.description or "")[:4000],
            "changelog": (item.changelog or "")[:2000],
            # --- async-loaded sections (placeholders until the extras land) ---
            "historyLabels": [],
            "ratingValues": [],
            "reviewsValues": [],
            "installsValues": [],
            "similar": [],
            "similarLoading": not is_ios and api is None,
            "recentAlerts": [],
            "recentReviews": [],
            "permissions": [],
            "permissionsLoaded": False,
        }
        self.detailChanged.emit()
        # GP-only follow-ups: local monitoring extras and the slow network `similar`.
        # iTunes has no similar-apps API, and App Store apps are never tracked locally,
        # so on iOS the detail is complete as-is (the QML hides those sections too).
        if is_ios:
            return
        self._run(
            lambda: self._detail_controller.collect_extras(item),
            lambda extras: self._apply_detail_extras(gen, extras),
            label="正在加载本地历史...",
            busy=False,
        )
        ctx = self._detail_context or {"country": "us", "lang": "en"}
        if api is not None:
            return
        self._run(
            lambda: self.services["google_play_service"].similar(
                item.app_id, country=ctx["country"], lang=ctx["lang"], limit=10
            ),
            lambda similar: self._apply_detail_similar(gen, similar),
            label="正在获取相似应用...",
            busy=False,
        )

    def _apply_detail_extras(self, gen: int, extras: dict[str, Any]) -> None:
        if gen != self._detail_gen or not self._detail.get("loaded"):
            return
        self._detail = {**self._detail, **extras}
        self.detailChanged.emit()

    def _apply_detail_similar(self, gen: int, similar) -> None:
        if gen != self._detail_gen or not self._detail.get("loaded"):
            return
        rows = [
            {
                "iconUrl": getattr(entry, "icon_url", "") or "",
                "title": getattr(entry, "title", "") or getattr(entry, "app_id", ""),
                "appId": getattr(entry, "app_id", ""),
                "developer": getattr(entry, "developer", "") or "-",
                "rating": (
                    f"{getattr(entry, 'rating'):.1f}"
                    if getattr(entry, "rating", None) is not None
                    else "-"
                ),
                "installs": getattr(entry, "installs", "") or "-",
            }
            for entry in similar
        ]
        self._detail = {**self._detail, "similar": rows, "similarLoading": False}
        self.detailChanged.emit()

    @Slot(int, str, str)
    def openSimilarResult(self, index: int, country: str, lang: str) -> None:
        rows = self._detail.get("similar") or []
        if index < 0 or index >= len(rows):
            self.errorMessage.emit("请先选择一条相似应用。")
            return
        self.fetchAppDetail(rows[index]["appId"], country, lang)

    def _apply_detail_permissions(self, gen: int, data: dict) -> None:
        if gen != self._detail_gen or not self._detail.get("loaded"):
            return
        groups = [
            {"group": group, "count": len(items), "items": list(items)}
            for group, items in (data or {}).items()
            if items
        ]
        self._detail = {**self._detail, "permissions": groups, "permissionsLoaded": True}
        self.detailChanged.emit()
        total = sum(g["count"] for g in groups)
        self.statusMessage.emit(f"权限：{len(groups)} 组，共 {total} 条。")

    def _set_chart_results(self, items) -> None:
        self._chart_items = list(items)
        rows = [
            {
                "rank": getattr(item, "rank", 0),
                "iconUrl": getattr(item, "icon_url", "") or "",
                "title": getattr(item, "title", ""),
                "appId": getattr(item, "app_id", ""),
                "developer": getattr(item, "developer", "") or "-",
                "rating": (
                    getattr(item, "rating", None)
                    if getattr(item, "rating", None) is not None
                    else "-"
                ),
                "installs": getattr(item, "installs", "") or "-",
                "price": getattr(item, "price", "")
                or ("免费" if getattr(item, "free", False) else "-"),
                "category": getattr(item, "category", "") or "-",
            }
            for item in items
        ]
        self._charts = {"rows": rows, "summary": f"已获取 {len(rows)} 条榜单结果"}
        self.chartsChanged.emit()

    def _set_chart_result_payload(self, payload) -> None:
        if isinstance(payload, dict):
            self._set_chart_results(payload.get("items") or [])
            return
        self._set_chart_results(payload)

    def _set_keyword_result(self, result) -> None:
        self._keyword_result_remote = False
        self._keyword_result = result
        app_id = getattr(result, "app_id", "")
        found = bool(getattr(result, "found", False))
        rank = getattr(result, "rank", None)
        checked_limit = int(getattr(result, "checked_limit", 0) or 0)
        results = getattr(result, "results", []) or []
        rows = [
            {
                "rank": index,
                "iconUrl": getattr(item, "icon_url", "") or "",
                "title": getattr(item, "title", ""),
                "appId": getattr(item, "app_id", ""),
                "developer": getattr(item, "developer", "") or "-",
                "rating": (
                    getattr(item, "rating", None)
                    if getattr(item, "rating", None) is not None
                    else "-"
                ),
                "installs": getattr(item, "installs", "") or "-",
                "hit": getattr(item, "app_id", "") == app_id,
            }
            for index, item in enumerate(results, start=1)
        ]
        if not rows and found:
            rows = [
                {
                    "rank": rank or "-",
                    "iconUrl": "",
                    "title": app_id or "-",
                    "appId": app_id,
                    "developer": "-",
                    "rating": "-",
                    "installs": "-",
                    "hit": True,
                }
            ]
        summary = (
            f"前 {KEYWORD_RANK_CHECK_LIMIT} 条内排名 #{rank}"
            if found and rank is not None
            else f"前 {KEYWORD_RANK_CHECK_LIMIT} 条未找到目标应用"
        )
        requested_limit = getattr(result, "requested_limit", None) or checked_limit
        returned_count = getattr(result, "returned_count", None) or checked_limit
        coverage_complete = bool(getattr(result, "coverage_complete", True))
        limit_text = f"仅检查前 {KEYWORD_RANK_CHECK_LIMIT} 条"
        if not coverage_complete:
            summary = f"{summary}（上游仅返回 {returned_count}/{requested_limit}）"
        self._keywords = {
            "rows": rows,
            "summary": f"{summary} · {limit_text}",
        }
        self.keywordsChanged.emit()

    def _set_keyword_result_from_api(self, result) -> None:
        self._set_keyword_result(result)
        self._keyword_result_remote = True

    def _set_keyword_payload_from_api(self, payload) -> None:
        if isinstance(payload, dict):
            result = payload.get("result")
            if result is not None:
                self._set_keyword_result_from_api(result)
                return
        self._set_keyword_result_from_api(payload)

    def _set_reviews_result(self, result) -> None:
        items, token = result
        self._reviews_items = list(items)
        self._reviews_token = token
        summary = f"已获取 {len(items)} 条评论"
        self._emit_reviews(summary)

    def _append_reviews_result(self, result) -> None:
        items, token = result
        self._reviews_items.extend(items)
        self._reviews_token = token if items else None
        self._emit_reviews(f"共 {len(self._reviews_items)} 条评论")

    def _emit_reviews(self, summary: str) -> None:
        rows = [review_row(item) for item in self._reviews_items]
        self._reviews = {
            "rows": rows,
            "summary": summary,
            "hasMore": self._reviews_token is not None and len(self._reviews_items) > 0,
        }
        self.reviewsChanged.emit()

    def _guarded(self, counter_attr: str, request_id: int, applier):
        """Wrap a result applier so it only runs if its request is still the latest.

        Guards against a slow, older fetch landing after a newer one (or after a
        platform switch bumped the counter) and overwriting the fresher state."""

        def apply(result):
            if getattr(self, counter_attr) == request_id:
                applier(result)

        return apply

    def _item_at(self, items: list[Any], index: int, message: str) -> Any | None:
        if index < 0 or index >= len(items):
            self.errorMessage.emit(message)
            return None
        return items[index]

    @staticmethod
    def _to_dict(payload) -> dict[str, Any]:
        if hasattr(payload, "toVariant"):
            payload = payload.toVariant()
        return dict(payload or {})
