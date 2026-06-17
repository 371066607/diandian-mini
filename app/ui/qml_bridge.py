from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from PySide6.QtCore import QObject, Property, QThreadPool, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices

from app.config import DATA_DIR
from app.constants import DEFAULT_SETTINGS
from app.db.repositories import ChartRankRepository, KeywordRankRepository, SnapshotRepository
from app.ui.alert_labels import ALERT_SEVERITY_COLORS, alert_severity_label, alert_type_label
from app.utils.network import apply_proxy_env
from app.utils.normalize import normalize_app_id, safe_float, safe_int
from app.utils.proxy_pool import ProxyPool, load_proxies
from app.utils.time_utils import (
    DEFAULT_SYNC_TIME,
    FREQUENCY_HOURS,
    is_sync_due,
    is_valid_time_of_day,
    now_iso,
)
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
        self._coverage: dict[str, Any] = self._coverage_state()
        # Candidate pools from finished scans, keyed by (platform, app_id, country, lang)
        # — a re-scan of the same identity reuses them instead of re-paying the detail +
        # autocomplete requests (the candidates only derive from slow-moving metadata).
        self._coverage_pools: dict[tuple, tuple[list[str], str | None]] = {}
        self._dashboard: dict[str, Any] = {}
        self._tracking: dict[str, Any] = {}
        # Eagerly loaded so the QML palette (bound to settings.theme) gets the right
        # accent on the very first frame — not after the first refreshSettings().
        self._settings: dict[str, Any] = services["settings_service"].get_all()
        self._alerts: dict[str, Any] = {"rows": []}
        self._search: dict[str, Any] = {"rows": [], "summary": "等待搜索"}
        self._detail: dict[str, Any] = {"loaded": False}
        self._charts: dict[str, Any] = {"rows": [], "summary": "等待获取榜单"}
        self._keywords: dict[str, Any] = {"rows": [], "summary": "等待查询排名"}
        self._reviews: dict[str, Any] = {"rows": [], "summary": "等待抓取评论"}
        self._history: dict[str, Any] = {"apps": [], "snapshots": [], "keywords": []}
        self._search_items: list[Any] = []
        self._detail_item: Any | None = None
        self._detail_context: dict[str, str] = {}
        self._detail_gen = 0
        self._chart_items: list[Any] = []
        self._chart_context: dict[str, Any] = {}
        self._keyword_result: Any | None = None
        self._reviews_items: list[Any] = []
        self._reviews_context: dict[str, str] = {}
        self._reviews_token: Any | None = None
        self._history_selection: tuple[str, str, str] | None = None

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

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return self._busy_count > 0

    @Property(str, notify=platformChanged)
    def platform(self) -> str:
        return self._platform

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
        store's app ids, so acting on them (open detail / load more) would mis-route."""
        self._search_items = []
        self._search = {"rows": [], "summary": "等待搜索"}
        self.searchChanged.emit()
        self._chart_items = []
        self._chart_context = {}
        self._charts = {"rows": [], "summary": "等待获取榜单"}
        self.chartsChanged.emit()
        self._keyword_result = None
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

    def _active_store(self):
        """The scraping service matching the currently selected platform."""
        if self._platform == "app_store":
            return self.services["app_store_service"]
        return self.services["google_play_service"]

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
        self._run(service.check, self._on_update_checked, label="正在检查更新...", busy=False)

    def _on_update_checked(self, result) -> None:
        if getattr(result, "error", None):
            self._set_update_status(f"检查更新失败：{result.error}")
            return
        if result.mode == "git":
            if result.up_to_date:
                self._pending_update = None
                self._set_update_status("已是最新（源码 / 开发版）。")
                return
            self._pending_update = result
            self._set_update_status(f"发现新版本（落后 {result.behind} 个提交）。")
            self.updatePrompt.emit(
                "检查更新",
                f"发现新版本（落后 {result.behind} 个提交）。\n现在 git pull 更新并重启吗？",
            )
            return
        if result.up_to_date or not result.can_patch:
            self._pending_update = None
            self._set_update_status(f"已是最新版本（{result.local_label}）。")
            return
        self._pending_update = result
        self._set_update_status(f"发现新版本 {result.latest_label}。")
        changelog = f"{result.changelog}\n\n" if result.changelog else ""
        self.updatePrompt.emit(
            "发现新版本 🎉",
            f"当前 {result.local_label} → 最新 {result.latest_label}\n\n{changelog}"
            "只下载几百 KB 代码补丁，完成后自动重启，登录态与数据都保留。\n现在更新吗？",
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
            self._run(
                service.download_and_apply_patch,
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

    def _guard_google_play_only(self, feature: str) -> bool:
        """True (and an error toast) when the feature is unavailable on App Store."""
        if self._platform == "app_store":
            self.errorMessage.emit(f"{feature}目前仅支持 Google Play，请先切回平台。")
            return True
        return False

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

    @staticmethod
    def _rank_text(rank) -> str:
        return ("#" + str(rank)) if rank else "未命中"

    @Slot(result="QVariant")
    def monitorTree(self) -> dict[str, Any]:
        """App-centric tree of monitored objects: each tracked app with its own tracked
        keywords and chart positions nested under it (grouped by app_id)."""
        ts = self.services["tracking_service"]
        apps = ts.list_apps()
        keywords = ts.list_keywords()
        chart_apps = ts.list_chart_apps()
        tree = []
        for a in apps:
            tree.append({
                "title": a.title or a.app_id,
                "appId": a.app_id,
                "country": a.country,
                "lang": a.lang,
                "lastSynced": self._fmt_dt(a.last_synced_at),
                "keywords": [
                    {"keyword": k.keyword, "country": k.country, "lang": k.lang,
                     "rank": self._keyword_rank_label(k)}
                    for k in keywords if k.app_id == a.app_id
                ],
                "charts": [
                    {"collection": c.collection, "category": c.category or "",
                     "country": c.country, "lang": c.lang, "rank": self._chart_rank_label(c)}
                    for c in chart_apps if c.app_id == a.app_id
                ],
            })
        return {"apps": tree}

    @Slot(str, str, str, str, str, int, result="QVariant")
    def monitorSeries(self, kind: str, app_id: str, country: str, lang: str, key: str,
                      days: int = 30) -> dict[str, Any]:
        """Time-series for a selected monitored object, ready to chart. kind: 'app'
        (rating/installs/reviews) | 'keyword' (rank) | 'chart' (rank). key: the keyword,
        or 'collection|category' for a chart. ``days`` windows to the last N days
        (<=0 = all history) — drives the date-range selector in the UI."""
        country = country or "us"
        lang = lang or "en"
        cutoff = "" if days <= 0 else (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")

        def win(items):
            return [r for r in items if not cutoff or (r.captured_at or "") >= cutoff]

        try:
            with self.database.session() as session:
                if kind == "keyword":
                    rows = win(self.keyword_rank_repository.history(session, key, app_id, country, lang))
                    labels = [r.captured_at[5:10] for r in rows]
                    values = [r.rank if r.rank else 0 for r in rows]
                    cur = self._rank_text(rows[-1].rank if rows else None)
                    return {"title": key, "subtitle": f"{app_id} · {country}/{lang}",
                            "charts": [{"name": "排名", "labels": labels, "values": values,
                                        "current": cur, "invert": True}]}
                if kind == "chart":
                    coll, _, cat = key.partition("|")
                    rows = self.chart_rank_repository.history(
                        session, app_id, coll, cat or None, country, lang)
                    labels = [r.captured_at[5:10] for r in rows]
                    values = [r.rank if r.rank else 0 for r in rows]
                    cur = self._rank_text(rows[-1].rank if rows else None)
                    return {"title": coll + (f" · {cat}" if cat else ""), "subtitle": app_id,
                            "charts": [{"name": "榜单名次", "labels": labels, "values": values,
                                        "current": cur, "invert": True}]}
                rows = self.snapshot_repository.get_history(session, app_id, country, lang)
                labels = [r.captured_at[5:10] for r in rows]
                last = rows[-1] if rows else None
                return {"title": (last.title if last and last.title else app_id),
                        "subtitle": f"{app_id} · {country}/{lang}",
                        "charts": [
                            {"name": "评分", "labels": labels,
                             "values": [round(r.rating, 2) if r.rating else 0 for r in rows],
                             "current": (f"{last.rating:.2f}" if last and last.rating else "-"),
                             "invert": False},
                            {"name": "安装量", "labels": labels,
                             "values": [r.real_installs or r.min_installs or 0 for r in rows],
                             "current": (str(last.real_installs or last.min_installs or 0) if last else "-"),
                             "invert": False},
                            {"name": "评论数", "labels": labels,
                             "values": [r.reviews_count or 0 for r in rows],
                             "current": (str(last.reviews_count or 0) if last else "-"),
                             "invert": False},
                        ]}
        except Exception:  # noqa: BLE001
            return {"title": "", "subtitle": "", "charts": []}

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
        self._run(
            lambda: self.services["settings_service"].get_all(),
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

    @Slot(str, str, str, str)
    def addApp(self, app_id: str, country: str, lang: str, frequency: str) -> None:
        if self._guard_google_play_only("App 监控"):
            return
        app_id = app_id.strip()
        if not app_id:
            self.errorMessage.emit("请输入要监控的包名。")
            return
        self._remember_input("app_id", app_id)
        country = country.strip() or "us"
        lang = lang.strip() or "en"
        frequency = frequency.strip() or "daily"
        self._run(
            lambda: self.services["tracking_service"].add_app(app_id, country, lang, frequency),
            lambda _: self._after_mutation("已添加 App 监控。"),
            label="正在添加 App 监控...",
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
        if self._guard_google_play_only("榜单监控"):
            return
        app_id = app_id.strip()
        if not app_id:
            self.errorMessage.emit("请输入要监控榜单的包名。")
            return
        self._remember_input("app_id", app_id)
        self._run(
            lambda: self.services["tracking_service"].add_chart_app(
                app_id,
                collection.strip() or "top_free",
                category.strip() or "APPLICATION",
                country.strip() or "us",
                lang.strip() or "en",
            ),
            lambda _: self._after_mutation("已添加榜单监控。"),
            label="正在添加榜单监控...",
        )

    @Slot()
    def syncAll(self) -> None:
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
        self._run(
            lambda: self.services["tracking_service"].sync_all(True),
            lambda result: self._after_mutation(
                f"已同步到期项：{result['apps']} 个应用，{result['keywords']} 个关键词，"
                f"{result['charts']} 个榜单。"
            ),
            label="正在同步到期项...",
        )

    @Slot()
    def markAllAlertsRead(self) -> None:
        self._run(
            self.services["alert_service"].mark_all_read,
            lambda count: self._after_mutation(f"已标记 {count} 条为已读。"),
            label="正在标记提醒...",
        )

    @Slot(int)
    def markAlertRead(self, alert_id: int) -> None:
        if alert_id <= 0:
            self.errorMessage.emit("请先选择一条提醒。")
            return
        self._run(
            lambda: self.services["alert_service"].mark_read([alert_id]),
            lambda count: self._after_mutation(f"已标记 {count} 条为已读。"),
            label="正在标记提醒...",
        )

    @Slot(str)
    def setTheme(self, name: str) -> None:
        """Persist + apply the UI accent theme. A cheap local write; emits
        settingsChanged so the QML palette (bound to settings.theme) recolors live."""
        name = (name or "").strip() or "teal"
        try:
            self.services["settings_service"].set_many({"theme": name})
        except Exception:  # noqa: BLE001
            pass
        self._settings = {**self._settings, "theme": name}
        self.settingsChanged.emit()

    @Slot("QVariant")
    def saveSettings(self, payload) -> None:
        values = self._to_dict(payload)
        current = self.services["settings_service"].get_all()
        updates = DEFAULT_SETTINGS.copy()
        updates.update(current)
        for key in updates:
            if key in values:
                updates[key] = str(values[key]).strip()

        sync_time = updates.get("daily_sync_time") or DEFAULT_SYNC_TIME
        if not is_valid_time_of_day(sync_time):
            self.errorMessage.emit("每日同步时间格式不正确，请使用 HH:MM（例如 09:00）。")
            return
        updates["daily_sync_time"] = sync_time
        updates["default_country"] = updates.get("default_country") or "us"
        updates["default_lang"] = updates.get("default_lang") or "en"
        updates["default_limit"] = updates.get("default_limit") or "50"
        updates["request_delay_seconds"] = updates.get("request_delay_seconds") or "1"

        def save() -> None:
            self.services["settings_service"].set_many(updates)
            apply_proxy_env(updates.get("proxy", ""))
            google_play_service = self.services.get("google_play_service")
            if google_play_service is not None and hasattr(google_play_service, "configure"):
                google_play_service.configure(
                    request_delay_seconds=safe_float(updates["request_delay_seconds"], 1.0)
                )
            scheduler = self.services.get("scheduler")
            if scheduler is not None and hasattr(scheduler, "reload_jobs"):
                scheduler.reload_jobs()

        self._run(save, lambda _: self._after_mutation("设置已保存。"), label="正在保存设置...")

    @Slot(str, str, str, str)
    def searchApps(self, keyword: str, country: str, lang: str, limit: str) -> None:
        keyword = keyword.strip()
        if not keyword:
            self.errorMessage.emit("请输入搜索关键词。")
            return
        self._remember_input("search_keyword", keyword)
        store = self._active_store()
        self._run(
            lambda: store.search(
                keyword,
                country=country.strip() or "us",
                lang=lang.strip() or "en",
                limit=safe_int(limit, 50),
            ),
            self._set_search_results,
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
        if self._guard_google_play_only("App 监控"):
            return
        item = self._item_at(self._search_items, index, "请先选择一条搜索结果。")
        if item is None:
            return
        self._run(
            lambda: self.services["tracking_service"].add_app(
                item.app_id,
                country.strip() or "us",
                lang.strip() or "en",
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
        self._detail_context = {
            "country": country.strip() or "us",
            "lang": lang.strip() or "en",
        }
        store = self._active_store()
        self._run(
            lambda: store.app_detail(
                app_id,
                country=self._detail_context["country"],
                lang=self._detail_context["lang"],
            ),
            self._set_detail_result,
            label="正在获取应用详情...",
        )

    @Slot()
    def fetchDetailPermissions(self) -> None:
        if self._guard_google_play_only("权限数据"):
            return
        if self._detail_item is None:
            self.errorMessage.emit("请先获取应用详情。")
            return
        app_id = self._detail_item.app_id
        ctx = self._detail_context or {"country": "us", "lang": "en"}
        gen = self._detail_gen
        self._run(
            lambda: self.services["google_play_service"].permissions(
                app_id, country=ctx["country"], lang=ctx["lang"]
            ),
            lambda data: self._apply_detail_permissions(gen, data),
            label="正在获取权限...",
        )

    @Slot(str, str)
    def saveDetailSnapshot(self, country: str, lang: str) -> None:
        if self._guard_google_play_only("快照"):
            return
        if self._detail_item is None:
            self.errorMessage.emit("请先获取应用详情。")
            return
        app_id = self._detail_item.app_id
        self._run(
            lambda: self.services["tracking_service"].sync_app_now(
                app_id,
                country=country.strip() or "us",
                lang=lang.strip() or "en",
            ),
            lambda detail: self._after_detail_saved(detail),
            label="正在保存快照...",
        )

    @Slot(str, str)
    def addDetailTracking(self, country: str, lang: str) -> None:
        if self._guard_google_play_only("App 监控"):
            return
        if self._detail_item is None:
            self.errorMessage.emit("请先获取应用详情。")
            return
        app_id = self._detail_item.app_id
        self._run(
            lambda: self.services["tracking_service"].add_app(
                app_id,
                country.strip() or "us",
                lang.strip() or "en",
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
        self._run(
            lambda: self.services["chart_service"].fetch(
                self._chart_context["chart_type"],
                self._chart_context["category"],
                self._chart_context["country"],
                self._chart_context["lang"],
                safe_int(limit, 100),
                platform=self._chart_context["platform"],
            ),
            self._set_chart_results,
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
        }
        self._run(
            lambda: self.services["chart_service"].save(
                ctx["chart_type"],
                ctx["category"],
                ctx["country"],
                ctx["lang"],
                self._chart_items,
            ),
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
        self._remember_input("keyword", keyword.strip())
        self._remember_input("app_id", app_id.strip())
        # Strict lookup: a missing platform service must fail loudly, not silently
        # answer with Google Play data labeled as the other store.
        keyword_service = self.services[
            "keyword_service_app_store" if self._platform == "app_store" else "keyword_service"
        ]
        self._run(
            lambda: keyword_service.rank(
                keyword.strip(),
                app_id.strip(),
                country=country.strip() or "us",
                lang=lang.strip() or "en",
                limit=safe_int(limit, 100),
            ),
            self._set_keyword_result,
            label="正在查询关键词排名...",
        )

    @Slot()
    def saveKeywordRank(self) -> None:
        if self._keyword_result is None:
            self.errorMessage.emit("请先查询关键词排名。")
            return
        self._run(
            lambda: self.services["keyword_service"].save_result(self._keyword_result),
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
        self._run(
            lambda: self.services["tracking_service"].add_keyword(
                keyword,
                app_id,
                country=country.strip() or "us",
                lang=lang.strip() or "en",
                platform=platform,
            ),
            lambda _: self._after_mutation("已加入关键词监控。"),
            label="正在加入关键词监控...",
        )

    # --- keyword coverage ("what keywords can find my app") ------------------

    @Property("QVariant", notify=coverageChanged)
    def coverage(self) -> dict[str, Any]:
        return self._coverage

    @Slot(str, str, str, bool)
    def discoverCoverage(
        self, app_id: str, country: str, lang: str, deep: bool = False
    ) -> None:
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
        cached_pool = self._coverage_pools.get(pool_key)
        # Build a proxy pool from settings + data/proxies.txt. Concurrency is honoured
        # ONLY when proxies exist — parallel same-IP scraping just multiplies ban risk.
        proxies = load_proxies(self.services.get("settings_service"), DATA_DIR)
        proxy_pool = ProxyPool(proxies) if proxies else None
        max_workers = self._coverage_concurrency() if proxy_pool else 1
        if proxy_pool:
            self.statusMessage.emit(
                f"覆盖扫描启用 {len(proxy_pool)} 个代理 · {max_workers} 并发"
            )
        self._set_coverage(
            summary="正在深度挖掘覆盖关键词，请稍候..." if deep else "正在分析覆盖关键词，请稍候...",
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
                candidates, canonical = cached_pool or (None, None)
                result = self.services["keyword_coverage_service"].analyze_coverage(
                    platform,
                    app_id,
                    country=country,
                    lang=lang,
                    limit=50,
                    deep=deep,
                    candidates=candidates,
                    canonical_app_id=canonical,
                    proxy_pool=proxy_pool,
                    max_workers=max_workers,
                    progress=lambda msg, frac: self.coverageProgress.emit(msg, float(frac)),
                )
                return ("ok", result)
            except Exception as exc:  # surface a clean message, never leave it "running"
                return ("error", str(exc))

        # busy=False: a coverage scan runs ~1-2 min, so use inline progress (the
        # CoveragePage shows a bar) instead of blocking the whole UI with the overlay.
        self._run(work, self._on_coverage_done, label="正在分析覆盖关键词...", busy=False)

    def _coverage_concurrency(self) -> int:
        """Max parallel workers for a proxy-backed coverage scan (clamped 1..16)."""
        raw = self.services["settings_service"].get("coverage_concurrency", "6")
        return max(1, min(16, safe_int(raw, 6)))

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
        pool_key = (
            value.platform,
            normalize_app_id(value.app_id),
            value.country,
            value.lang,
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
        self._run(
            lambda: self._fetch_reviews_for(self._reviews_context, None),
            self._set_reviews_result,
            label="正在抓取评论...",
        )

    @Slot()
    def loadMoreReviews(self) -> None:
        ctx = self._reviews_context
        token = self._reviews_token
        if not ctx.get("app_id") or token is None:
            self.errorMessage.emit("没有更多评论可加载。")
            return
        self._run(
            lambda: self._fetch_reviews_for(ctx, token),
            self._append_reviews_result,
            label="正在加载更多评论...",
        )

    def _fetch_reviews_for(self, ctx: dict[str, str], token):
        """Fetch one reviews page from the platform the context was created under,
        so a mid-flight platform switch can't mix sources."""
        if ctx.get("platform") == "app_store":
            return self.services["app_store_service"].reviews(
                ctx["app_id"],
                country=ctx["country"],
                lang=ctx["lang"],
                sort=ctx.get("sort", "newest"),
                continuation_token=token,
            )
        return self.services["review_service"].fetch(
            ctx["app_id"], ctx["country"], ctx["lang"], ctx.get("sort", "newest"), token
        )

    @Slot(str, str, str)
    def saveReviews(self, app_id: str, country: str, lang: str) -> None:
        app_id = (app_id or self._reviews_context.get("app_id", "")).strip()
        country = (country or self._reviews_context.get("country", "")).strip() or "us"
        lang = (lang or self._reviews_context.get("lang", "")).strip() or "en"
        if not app_id or not self._reviews_items:
            self.errorMessage.emit("请先获取评论。")
            return
        self._run(
            lambda: self.services["review_service"].save(
                app_id,
                country,
                lang,
                self._reviews_items,
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

    def _after_detail_saved(self, detail) -> None:
        self._set_detail_result(detail)
        self._after_mutation("快照已写入 SQLite。")

    def _collect_dashboard(self) -> dict[str, Any]:
        tracking_service = self.services["tracking_service"]
        alert_service = self.services["alert_service"]
        tracked_apps = tracking_service.list_apps()
        tracked_keywords = tracking_service.list_keywords()
        chart_apps = tracking_service.list_chart_apps()
        with self.database.session() as session:
            snapshots_count = self.snapshot_repository.count(session)
            recent_snapshots = list(
                reversed(self.snapshot_repository.list_recent(session, limit=8))
            )
            latest_kw = self.keyword_rank_repository.list_recent(session, limit=1)
            keyword_history = []
            keyword_name = ""
            if latest_kw:
                top = latest_kw[0]
                keyword_name = top.keyword
                keyword_history = self.keyword_rank_repository.history(
                    session, top.keyword, top.app_id, top.country, top.lang
                )
        unread = alert_service.unread_count()
        alerts = alert_service.recent_alerts(limit=6)
        latest_sync = self._latest_sync_time(tracked_apps, tracked_keywords, chart_apps)
        health = tracking_service.monitor_overview()
        return {
            "stats": [
                {
                    "label": "监控 App",
                    "value": len(tracked_apps),
                    "meta": f"启用 {sum(1 for x in tracked_apps if x.enabled)}",
                },
                {"label": "关键词监控", "value": len(tracked_keywords), "meta": "本地排名历史"},
                {"label": "榜单监控", "value": len(chart_apps), "meta": "Google Play 榜单"},
                {"label": "历史快照", "value": snapshots_count, "meta": "SQLite 本地数据"},
                {"label": "未读提醒", "value": unread, "meta": "评分 / 版本 / 排名变化"},
            ],
            "latestSync": self._short_time(latest_sync) if latest_sync else "-",
            "alerts": [self._alert_row(alert) for alert in alerts],
            "health": [self._health_row(item) for item in health],
            "ratingLabels": [self._short_time(item.captured_at) for item in recent_snapshots],
            "ratingValues": [item.rating or 0 for item in recent_snapshots],
            "keywordName": keyword_name,
            "keywordLabels": [self._short_time(item.captured_at) for item in keyword_history],
            "keywordValues": [item.rank or item.checked_limit or 0 for item in keyword_history],
        }

    def _collect_tracking(self) -> dict[str, Any]:
        tracking_service = self.services["tracking_service"]
        settings = self.services["settings_service"].get_all()
        apps = tracking_service.list_apps()
        keywords = tracking_service.list_keywords()
        chart_apps = tracking_service.list_chart_apps()
        return {
            "defaults": {
                "country": settings["default_country"],
                "lang": settings["default_lang"],
                "limit": settings["default_limit"],
            },
            "apps": [
                {
                    "title": item.title or item.app_id,
                    "appId": item.app_id,
                    "country": item.country,
                    "lang": item.lang,
                    "frequency": self._frequency_label(item.frequency),
                    "lastSynced": self._fmt_dt(item.last_synced_at),
                    "nextSync": self._next_sync_label(item.last_synced_at, item.frequency),
                    "failures": self._fail_label(item),
                    "tag": item.tag or "-",
                    "enabled": "启用" if item.enabled else "禁用",
                }
                for item in apps
            ],
            "keywords": [
                {
                    "keyword": item.keyword,
                    "appId": item.app_id,
                    "rank": self._keyword_rank_label(item),
                    "country": item.country,
                    "frequency": self._frequency_label(item.frequency),
                    "lastSynced": self._fmt_dt(item.last_synced_at),
                    "nextSync": self._next_sync_label(item.last_synced_at, item.frequency),
                    "failures": self._fail_label(item),
                    "enabled": "启用" if item.enabled else "禁用",
                }
                for item in keywords
            ],
            "charts": [
                {
                    "appId": item.app_id,
                    "collection": item.collection,
                    "category": item.category or "-",
                    "country": item.country,
                    "rank": self._chart_rank_label(item),
                    "lastSynced": self._fmt_dt(item.last_synced_at),
                    "failures": self._fail_label(item),
                    "enabled": "启用" if item.enabled else "禁用",
                }
                for item in chart_apps
            ],
        }

    def _collect_alerts(self) -> dict[str, Any]:
        alert_service = self.services["alert_service"]
        alerts = alert_service.list_alerts(limit=200)
        return {
            "rows": [self._alert_row(alert) for alert in alerts],
            "unread": alert_service.unread_count(),
        }

    def _collect_history(self) -> dict[str, Any]:
        tracking_service = self.services["tracking_service"]
        apps = tracking_service.list_apps()
        selected = apps[0] if apps else None
        if self._history_selection is not None:
            selected = next(
                (
                    item
                    for item in apps
                    if (
                        item.app_id,
                        item.country,
                        item.lang,
                    )
                    == self._history_selection
                ),
                selected,
            )
        snapshots = []
        keyword_rows = []
        if selected is not None:
            self._history_selection = (selected.app_id, selected.country, selected.lang)
            with self.database.session() as session:
                snapshots = self.snapshot_repository.get_history(
                    session, selected.app_id, selected.country, selected.lang
                )[-80:]
                recent_kw = self.keyword_rank_repository.list_recent(session, limit=80)
                keyword_rows = [
                    row
                    for row in recent_kw
                    if row.app_id == selected.app_id
                    and row.country == selected.country
                    and row.lang == selected.lang
                ]
        return {
            "apps": [
                {
                    "label": f"{item.title or item.app_id} · {item.country}/{item.lang}",
                    "appId": item.app_id,
                    "country": item.country,
                    "lang": item.lang,
                }
                for item in apps
            ],
            "selected": selected.app_id if selected is not None else "",
            "snapshots": [
                {
                    "time": self._short_time(item.captured_at),
                    "title": item.title or item.app_id,
                    "rating": item.rating or "-",
                    "ratings": item.ratings_count or "-",
                    "reviews": item.reviews_count or "-",
                    "installs": item.installs or "-",
                    "version": item.version or "-",
                }
                for item in snapshots
            ],
            "keywords": [
                {
                    "time": self._short_time(item.captured_at),
                    "keyword": item.keyword,
                    "rank": item.rank if item.rank is not None else "未命中",
                    "limit": item.checked_limit,
                }
                for item in keyword_rows
            ],
        }

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
                "iconUrl": item.icon_url or "",
                "title": item.title,
                "appId": item.app_id,
                "developer": item.developer or "-",
                "rating": item.rating if item.rating is not None else "-",
                "ratings": self._fmt_count(item.ratings_count),
                "installs": item.installs or "-",
                "price": item.price or "免费",
                "hasIap": "内购" if item.has_iap else "",
                "category": item.category or "-",
            }
            for item in items
        ]
        self._search = {"rows": rows, "summary": f"已获取 {len(rows)} 条搜索结果"}
        self.searchChanged.emit()

    def _set_detail_result(self, item) -> None:
        self._detail_item = item
        self._detail_gen += 1
        gen = self._detail_gen
        is_ios = item.platform == "app_store"
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
            "priceLabel": self._price_label(item),
            "available": item.available,
            # --- metric chips (label/value computed bridge-side; QML just repeats) ---
            "metrics": self._detail_metrics(item),
            # --- rating histogram ---
            "histogram": self._histogram_rows(item.histogram),
            # --- developer / links ---
            "devLinks": self._detail_dev_links(item, is_ios),
            "devPlain": self._detail_dev_plain(item, is_ios),
            # --- more info ---
            "moreInfo": self._detail_more_info(item, is_ios),
            "contentRatingDescription": item.content_rating_description or "",
            "dataSafety": self._data_safety_text(item.data_safety),
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
            "similarLoading": not is_ios,
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
            lambda: self._collect_detail_extras(item),
            lambda extras: self._apply_detail_extras(gen, extras),
            label="正在加载本地历史...",
            busy=False,
        )
        ctx = self._detail_context or {"country": "us", "lang": "en"}
        self._run(
            lambda: self.services["google_play_service"].similar(
                item.app_id, country=ctx["country"], lang=ctx["lang"], limit=10
            ),
            lambda similar: self._apply_detail_similar(gen, similar),
            label="正在获取相似应用...",
            busy=False,
        )

    def _detail_dev_links(self, item, is_ios: bool) -> list[dict[str, str]]:
        links = [
            {
                "label": "官网",
                "text": item.developer_website or "",
                "url": item.developer_website or "",
            },
        ]
        if not is_ios:
            links.insert(
                0,
                {
                    "label": "邮箱",
                    "text": item.developer_email or "",
                    "url": f"mailto:{item.developer_email}" if item.developer_email else "",
                },
            )
            links.append(
                {
                    "label": "隐私政策",
                    "text": item.privacy_policy or "",
                    "url": item.privacy_policy or "",
                }
            )
        return links

    def _detail_dev_plain(self, item, is_ios: bool) -> list[dict[str, str]]:
        if is_ios:
            return [
                {"label": "卖家", "value": item.developer_address or "-"},
                {"label": "发布国", "value": item.publisher_country or "-"},
            ]
        return [
            {"label": "地址", "value": item.developer_address or "-"},
            {"label": "电话", "value": item.developer_phone or "-"},
            {"label": "发布国", "value": item.publisher_country or "-"},
        ]

    def _detail_more_info(self, item, is_ios: bool) -> list[dict[str, Any]]:
        if is_ios:
            return [
                {"label": "App ID", "value": item.app_id},
                {"label": "Bundle ID", "value": item.app_bundle or "-"},
                {"label": "类目 ID", "value": item.genre_id or "-"},
                {"label": "开发者 ID", "value": item.developer_id or "-"},
                {"label": "货币", "value": item.currency or "-"},
                {
                    "label": "全部类目",
                    "value": "、".join(item.categories) if item.categories else "-",
                },
            ]
        return [
            {"label": "应用包", "value": item.app_bundle or "-"},
            {"label": "类目 ID", "value": item.genre_id or "-"},
            {"label": "开发者 ID", "value": item.developer_id or "-"},
            {"label": "货币", "value": item.currency or "-"},
            {"label": "最低日均安装", "value": self._fmt_count(item.min_daily_installs)},
            {"label": "最低月均安装", "value": self._fmt_count(item.min_monthly_installs)},
            {"label": "预告片", "value": "观看", "url": item.video or ""},
            {"label": "头图", "value": "查看", "url": item.header_image or ""},
        ]

    def _detail_metrics(self, item) -> list[dict[str, Any]]:
        if item.platform == "app_store":
            return self._detail_metrics_app_store(item)
        daily = item.real_daily_installs or item.daily_installs
        monthly = item.real_monthly_installs or item.monthly_installs
        ads = item.contains_ads if item.contains_ads is not None else item.ad_supported
        if item.min_android_api and item.max_android_api:
            api_text = f"{item.min_android_api} ~ {item.max_android_api}"
        elif item.min_android_api:
            api_text = f"{item.min_android_api}+"
        else:
            api_text = "-"
        if item.original_price:
            original = (
                f"{item.currency} {item.original_price:.2f}"
                if item.currency
                else f"{item.original_price:.2f}"
            )
        else:
            original = "-"
        return [
            {
                "label": "评分",
                "value": f"{item.rating:.2f}" if item.rating else "-",
                "accent": "blue",
            },
            {"label": "评分数", "value": self._fmt_count(item.ratings_count)},
            {"label": "评论数", "value": self._fmt_count(item.reviews_count)},
            {"label": "安装量", "value": item.installs or "-", "accent": "blue"},
            {"label": "最低安装", "value": self._fmt_count(item.min_installs)},
            {"label": "真实安装", "value": self._fmt_count(item.real_installs), "accent": "blue"},
            {"label": "日均安装", "value": self._fmt_count(daily)},
            {"label": "月均安装", "value": self._fmt_count(monthly)},
            {
                "label": "上线天数",
                "value": f"{item.app_age_days:,} 天" if item.app_age_days else "-",
            },
            {"label": "发布日期", "value": item.released or "-"},
            {"label": "最近更新", "value": item.updated or "-"},
            {"label": "版本", "value": item.version or "-"},
            {"label": "Android 版本", "value": item.android_version or "-"},
            {"label": "Android API", "value": api_text},
            {"label": "内容分级", "value": item.content_rating or "-"},
            {"label": "价格", "value": item.price or ("免费" if item.free else "-")},
            {"label": "原价", "value": original},
            {"label": "促销", "value": self._yes_no(item.sale)},
            {"label": "内购", "value": self._yes_no(item.has_iap)},
            {"label": "内购价", "value": item.iap_price_range or "-"},
            {"label": "含广告", "value": self._yes_no(ads)},
            {"label": "可下载", "value": self._yes_no(item.available)},
        ]

    def _detail_metrics_app_store(self, item) -> list[dict[str, Any]]:
        """iOS-native chip set — iTunes lookup has no install counts / Android fields,
        but does carry size, min OS, device & language coverage and per-version rating."""
        raw = item.raw or {}
        current_rating = raw.get("averageUserRatingForCurrentVersion")
        devices = raw.get("supportedDevices") or []
        languages = raw.get("languageCodesISO2A") or []
        return [
            {
                "label": "评分",
                "value": f"{item.rating:.2f}" if item.rating else "-",
                "accent": "blue",
            },
            {"label": "评分数", "value": self._fmt_count(item.ratings_count)},
            {
                "label": "当前版本评分",
                "value": f"{current_rating:.2f}" if current_rating else "-",
            },
            {
                "label": "当前版本评分数",
                "value": self._fmt_count(raw.get("userRatingCountForCurrentVersion")),
            },
            {
                "label": "价格",
                "value": item.price or ("免费" if item.free else "-"),
                "accent": "blue",
            },
            {"label": "内购", "value": self._yes_no(item.has_iap)},
            {"label": "大小", "value": self._fmt_size(raw.get("fileSizeBytes"))},
            {
                "label": "最低系统",
                "value": f"iOS {raw['minimumOsVersion']}+" if raw.get("minimumOsVersion") else "-",
            },
            {"label": "支持设备", "value": f"{len(devices)} 种" if devices else "-"},
            {"label": "支持语言", "value": f"{len(languages)} 种" if languages else "-"},
            {"label": "版本", "value": item.version or "-"},
            {"label": "发布日期", "value": item.released or "-"},
            {"label": "最近更新", "value": item.updated or "-"},
            {
                "label": "上线天数",
                "value": f"{item.app_age_days:,} 天" if item.app_age_days else "-",
            },
            {"label": "内容分级", "value": item.content_rating or "-"},
            {"label": "可下载", "value": self._yes_no(item.available)},
        ]

    @staticmethod
    def _fmt_size(value) -> str:
        try:
            size = int(value)
        except (TypeError, ValueError):
            return "-"
        if size >= 1024**3:
            return f"{size / 1024**3:.2f} GB"
        return f"{size / 1024**2:.1f} MB"

    @staticmethod
    def _histogram_rows(histogram) -> list[dict[str, Any]]:
        counts = list(histogram or [])
        if not counts or sum(counts) == 0:
            return []
        total = sum(counts)
        maximum = max(counts) or 1
        rows = []
        for star in range(5, 0, -1):
            count = counts[star - 1] if len(counts) >= star else 0
            rows.append(
                {
                    "star": star,
                    "count": count,
                    "ratio": count / maximum,
                    "text": f"{count:,} ({count / total * 100:.0f}%)",
                }
            )
        return rows

    @staticmethod
    def _price_label(item) -> str:
        # None means "unknown" (e.g. iTunes has no IAP/ads flags) — say nothing then.
        parts = [item.price or ("免费" if item.free in (True, None) else "-")]
        if item.has_iap is not None:
            parts.append("含内购" if item.has_iap else "无内购")
        ads = item.contains_ads if item.contains_ads is not None else item.ad_supported
        if ads is not None:
            parts.append("含广告" if ads else "无广告")
        return " · ".join(parts)

    @staticmethod
    def _fmt_count(value) -> str:
        return f"{value:,}" if isinstance(value, (int, float)) and value else "-"

    @staticmethod
    def _yes_no(value) -> str:
        if value is None:
            return "-"
        return "是" if value else "否"

    @staticmethod
    def _data_safety_text(data_safety) -> str:
        """Render the dataSafety list (shape varies by source) into a short summary."""
        if not data_safety:
            return "-"
        parts: list[str] = []
        for entry in data_safety:
            if isinstance(entry, dict):
                name = (
                    entry.get("data")
                    or entry.get("type")
                    or entry.get("name")
                    or entry.get("category")
                )
                if name:
                    parts.append(str(name))
            elif entry:
                parts.append(str(entry))
        if not parts:
            return f"{len(data_safety)} 项"
        return "、".join(parts[:8]) + (" …" if len(parts) > 8 else "")

    def _collect_detail_extras(self, item) -> dict[str, Any]:
        ctx = self._detail_context or {"country": "us", "lang": "en"}
        history = self.services["tracking_service"].get_history(
            item.app_id, country=ctx["country"], lang=ctx["lang"]
        )
        alerts = self.services["alert_service"].list_alerts(app_id=item.app_id, limit=8)
        reviews = []
        review_service = self.services.get("review_service")
        if review_service is not None:
            reviews = review_service.list_cached(item.app_id, limit=10)
        labels = [snap.captured_at[5:10] for snap in history]
        rating_values = [snap.rating or 0 for snap in history]
        reviews_values = [snap.reviews_count or 0 for snap in history]
        installs_values = [snap.real_installs or snap.min_installs or 0 for snap in history]
        # Append today's freshly-fetched values so the charts show something
        # even before any snapshot is saved (mirrors the widgets detail page).
        today = now_iso()[5:10]
        if not labels or labels[-1] != today:
            labels.append(today)
            rating_values.append(item.rating or 0)
            reviews_values.append(item.reviews_count or 0)
            installs_values.append(item.real_installs or item.min_installs or 0)
        return {
            "historyLabels": labels,
            "ratingValues": rating_values,
            "reviewsValues": reviews_values,
            "installsValues": installs_values,
            "recentAlerts": [self._alert_row(alert) for alert in alerts],
            "recentReviews": [
                {
                    "time": (r.review_created_at or "")[:10],
                    "rating": r.rating if r.rating is not None else "-",
                    "content": (r.content or "").strip().replace("\n", " ")[:120],
                }
                for r in reviews
            ],
        }

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
                "iconUrl": entry.icon_url or "",
                "title": entry.title or entry.app_id,
                "appId": entry.app_id,
                "developer": entry.developer or "-",
                "rating": f"{entry.rating:.1f}" if entry.rating is not None else "-",
                "installs": entry.installs or "-",
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
                "rank": item.rank,
                "iconUrl": item.icon_url or "",
                "title": item.title,
                "appId": item.app_id,
                "developer": item.developer or "-",
                "rating": item.rating if item.rating is not None else "-",
                "installs": item.installs or "-",
                "price": item.price or ("免费" if item.free else "-"),
                "category": item.category or "-",
            }
            for item in items
        ]
        self._charts = {"rows": rows, "summary": f"已获取 {len(rows)} 条榜单结果"}
        self.chartsChanged.emit()

    def _set_keyword_result(self, result) -> None:
        self._keyword_result = result
        rows = [
            {
                "rank": index,
                "iconUrl": item.icon_url or "",
                "title": item.title,
                "appId": item.app_id,
                "developer": item.developer or "-",
                "rating": item.rating if item.rating is not None else "-",
                "installs": item.installs or "-",
                "hit": item.app_id == result.app_id,
            }
            for index, item in enumerate(result.results, start=1)
        ]
        summary = f"当前排名 #{result.rank}" if result.found else "未找到目标应用"
        self._keywords = {
            "rows": rows,
            "summary": f"{summary} · checked_limit {result.checked_limit}",
        }
        self.keywordsChanged.emit()

    def _set_reviews_result(self, result) -> None:
        items, token = result
        self._reviews_items = list(items)
        self._reviews_token = token
        self._emit_reviews(f"已获取 {len(items)} 条评论")

    def _append_reviews_result(self, result) -> None:
        items, token = result
        self._reviews_items.extend(items)
        self._reviews_token = token if items else None
        self._emit_reviews(f"共 {len(self._reviews_items)} 条评论")

    def _emit_reviews(self, summary: str) -> None:
        rows = [
            {
                "user": item.user_name or "-",
                "rating": item.rating if item.rating is not None else 0,
                "version": item.app_version or "-",
                "time": (item.review_created_at or "-")[:16].replace("T", " "),
                "content": item.content or "",
                "helpful": item.helpful_count or 0,
            }
            for item in self._reviews_items
        ]
        self._reviews = {
            "rows": rows,
            "summary": summary,
            "hasMore": self._reviews_token is not None and len(self._reviews_items) > 0,
        }
        self.reviewsChanged.emit()

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

    @staticmethod
    def _short_time(value: str | None) -> str:
        if not value:
            return "-"
        return value[5:16].replace("T", " ") if len(value) >= 16 else value

    @staticmethod
    def _fmt_dt(value: str | None) -> str:
        if not value:
            return "未同步"
        try:
            return datetime.fromisoformat(value).strftime("%m-%d %H:%M")
        except (TypeError, ValueError):
            return value[:10] if len(value) >= 10 else value

    @staticmethod
    def _latest_sync_time(*groups) -> str | None:
        values = [
            item.last_synced_at
            for group in groups
            for item in group
            if getattr(item, "last_synced_at", None)
        ]
        return max(values) if values else None

    @staticmethod
    def _frequency_label(value: str | None) -> str:
        return {"daily": "每日", "weekly": "每周", "manual": "手动"}.get(value or "daily", value)

    @staticmethod
    def _fail_label(item) -> str:
        count = item.consecutive_failures or 0
        return "-" if count == 0 else f"{count} 次"

    @staticmethod
    def _next_sync_label(last_synced_at: str | None, frequency: str | None) -> str:
        freq = (frequency or "daily").lower()
        if freq == "manual":
            return "手动"
        if not last_synced_at:
            return "待首次同步"
        if is_sync_due(last_synced_at, freq):
            return "已到期"
        interval = FREQUENCY_HOURS.get(freq, FREQUENCY_HOURS["daily"])
        if interval is None:
            return "手动"
        try:
            last = datetime.fromisoformat(last_synced_at)
        except (ValueError, TypeError):
            return "待首次同步"
        return (last + timedelta(hours=interval)).strftime("%m-%d %H:%M")

    def _keyword_rank_label(self, item) -> str:
        # Rank snapshots are platform-scoped — read via the service matching the ROW's
        # platform (the tracked list mixes both stores), not the UI's current toggle.
        key = (
            "keyword_service_app_store"
            if item.platform == "app_store"
            else "keyword_service"
        )
        keyword_service = self.services.get(key)
        if keyword_service is None:
            return "未同步"
        snapshot = keyword_service.latest_rank(item.keyword, item.app_id, item.country, item.lang)
        if snapshot is None:
            return "未同步"
        return f"#{snapshot.rank}" if snapshot.found and snapshot.rank is not None else "未命中"

    def _chart_rank_label(self, item) -> str:
        chart_rank_service = self.services.get("chart_rank_service")
        if chart_rank_service is None:
            return "未同步"
        snapshot = chart_rank_service.latest_rank(
            item.app_id, item.collection, item.category, item.country, item.lang
        )
        if snapshot is None:
            return "未同步"
        return f"#{snapshot.rank}" if snapshot.found and snapshot.rank is not None else "未命中"

    @staticmethod
    def _alert_row(alert) -> dict[str, Any]:
        return {
            "id": alert.id,
            "time": QmlBridge._short_time(alert.created_at),
            "severity": alert_severity_label(alert.severity),
            "severityColor": ALERT_SEVERITY_COLORS.get(alert.severity, "#64748B"),
            "type": alert_type_label(alert.type),
            "appId": alert.app_id or "-",
            "message": alert.message,
            "isRead": "已读" if alert.is_read else "未读",
            "unread": not alert.is_read,
        }

    @staticmethod
    def _health_row(item) -> dict[str, Any]:
        color = {"normal": "#16A34A", "failing": "#D97706", "escalated": "#DC2626"}.get(
            item.fail_status, "#16A34A"
        )
        return {
            "title": item.title or item.app_id,
            "appId": item.app_id,
            "rating": f"{item.latest_rating:.2f}" if item.latest_rating is not None else "-",
            "installs": item.latest_installs or "-",
            "unread": item.unread_count,
            "failures": item.consecutive_failures,
            "statusColor": color,
            "lastSynced": QmlBridge._fmt_dt(item.last_synced_at),
        }
