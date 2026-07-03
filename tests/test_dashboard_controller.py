from types import SimpleNamespace

from app.ui.controllers.dashboard_controller import DashboardController


# --- fakes -------------------------------------------------------------------


class FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeDatabase:
    def session(self):
        return FakeSession()


class FakeSnapshotRepository:
    def __init__(self, recent=None, history=None, count=0):
        self.recent = recent or []
        self.history_rows = history or []
        self._count = count

    def count(self, session):
        return self._count

    def list_recent(self, session, limit=8):
        return self.recent[:limit]

    def get_history(self, session, app_id, country, lang):
        return self.history_rows


class FakeKeywordRankRepository:
    def __init__(self, recent=None, history=None):
        self.recent = recent or []
        self.history_rows = history or []

    def list_recent(self, session, limit=1):
        return self.recent[:limit]

    def history(self, session, keyword, app_id, country, lang):
        return self.history_rows


class FakeChartRankRepository:
    def __init__(self, history=None):
        self.history_rows = history or []

    def history(self, session, app_id, collection, category, country, lang):
        return self.history_rows


class FakeTrackingController:
    def __init__(self, platform="google_play"):
        self.platform = platform
        self.calls = []

    def platform_of(self, api, kind, app_id, country, lang, key):
        self.calls.append((kind, app_id, key))
        return self.platform


class FakeBridge:
    def __init__(
        self,
        api=None,
        services=None,
        snapshot_repository=None,
        keyword_rank_repository=None,
        chart_rank_repository=None,
    ):
        self._api = api
        self.services = services or {}
        self.database = FakeDatabase()
        self.snapshot_repository = snapshot_repository or FakeSnapshotRepository()
        self.keyword_rank_repository = keyword_rank_repository or FakeKeywordRankRepository()
        self.chart_rank_repository = chart_rank_repository or FakeChartRankRepository()
        self._tracking_controller = FakeTrackingController()
        self._history_selection = None

    def _store_intel_api(self):
        return self._api


class FakeApi:
    def __init__(
        self,
        tracked_apps=None,
        tracked_keywords=None,
        tracked_chart_apps=None,
        alerts=None,
        unread=0,
        snapshots_count=0,
        recent_snapshots=None,
        recent_keyword_ranks=None,
        keyword_history=None,
        settings=None,
        app_snapshots=None,
        recent_keyword_ranks_for_history=None,
    ):
        self.tracked_apps = tracked_apps or []
        self.tracked_keywords = tracked_keywords or []
        self.tracked_chart_apps = tracked_chart_apps or []
        self.alerts = alerts or []
        self.unread = unread
        self.snapshots_count = snapshots_count
        self.recent_snapshots = recent_snapshots or []
        self.recent_keyword_ranks = recent_keyword_ranks or []
        self.keyword_history = keyword_history or []
        self.settings = settings or {
            "default_country": "us",
            "default_lang": "en",
            "default_limit": 50,
        }
        self.app_snapshots = app_snapshots or []
        self.recent_keyword_ranks_for_history = recent_keyword_ranks_for_history or []
        self.keyword_rank_history = []
        self.chart_rank_history = []

    def list_tracked_apps(self):
        return self.tracked_apps

    def list_tracked_keywords(self):
        return self.tracked_keywords

    def list_tracked_chart_apps(self):
        return self.tracked_chart_apps

    def latest_keyword_rank_label(self, keyword, app_id, country, lang, platform="google_play"):
        return "#7"

    def latest_chart_rank_label(
        self, app_id, collection, category, country, lang, platform="google_play"
    ):
        return "#9"

    def list_alerts(self, limit=6):
        return self.alerts

    def unread_count(self):
        return self.unread

    def count_app_snapshots(self):
        return self.snapshots_count

    def list_recent_app_snapshots(self, limit=8):
        return self.recent_snapshots

    def list_recent_keyword_ranks(
        self, limit=None, app_id=None, country=None, lang=None, platform=None
    ):
        if app_id is not None:
            return self.recent_keyword_ranks_for_history
        return self.recent_keyword_ranks

    def list_keyword_rank_history(self, keyword, app_id, country, lang, platform="google_play"):
        return self.keyword_history

    def get_settings(self):
        return self.settings

    def list_app_snapshots(self, app_id, country, lang, limit=80, platform="google_play"):
        return self.app_snapshots

    def list_chart_rank_history(
        self, app_id, collection, category, country, lang, platform="google_play"
    ):
        return self.chart_rank_history


def _controller(**kwargs):
    return DashboardController(FakeBridge(**kwargs))


def _tracked_app(**overrides):
    defaults = dict(
        app_id="com.demo",
        title="Demo",
        country="us",
        lang="en",
        enabled=True,
        frequency="daily",
        last_synced_at="",
        tag="",
        consecutive_failures=0,
        platform="google_play",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# --- monitor_tree --------------------------------------------------------


def test_monitor_tree_legacy_groups_keywords_and_charts_by_app():
    ts = SimpleNamespace(
        list_apps=lambda: [
            SimpleNamespace(title="", app_id="com.a", country="us", lang="en", last_synced_at="")
        ],
        list_keywords=lambda: [
            SimpleNamespace(
                keyword="k1", app_id="com.a", country="us", lang="en", platform="google_play"
            )
        ],
        list_chart_apps=lambda: [
            SimpleNamespace(
                collection="top_free",
                category="",
                app_id="com.a",
                country="us",
                lang="en",
                platform="google_play",
            )
        ],
    )
    keyword_service = SimpleNamespace(latest_rank=lambda *a: SimpleNamespace(found=True, rank=3))
    chart_rank_service = SimpleNamespace(latest_rank=lambda *a: None)
    controller = _controller(
        services={
            "tracking_service": ts,
            "keyword_service": keyword_service,
            "chart_rank_service": chart_rank_service,
        }
    )

    tree = controller.monitor_tree()

    assert tree["apps"][0]["appId"] == "com.a"
    assert tree["apps"][0]["keywords"][0]["rank"] == "#3"
    assert tree["apps"][0]["charts"][0]["rank"] == "未同步"


def test_monitor_tree_api_mode_delegates_and_swallows_errors():
    class BrokenApi:
        def list_tracked_apps(self):
            raise RuntimeError("boom")

    controller = _controller(api=BrokenApi())
    assert controller.monitor_tree() == {"apps": []}


def test_monitor_tree_api_mode_builds_nested_rows():
    api = FakeApi(
        tracked_apps=[_tracked_app()],
        tracked_keywords=[
            SimpleNamespace(
                keyword="k1", app_id="com.demo", country="us", lang="en", platform="google_play"
            )
        ],
        tracked_chart_apps=[
            SimpleNamespace(
                app_id="com.demo",
                collection="top_free",
                category="",
                country="us",
                lang="en",
                platform="google_play",
            )
        ],
    )
    controller = _controller(api=api)

    tree = controller.monitor_tree()

    assert tree["apps"][0]["keywords"][0]["rank"] == "#7"
    assert tree["apps"][0]["charts"][0]["rank"] == "#9"


# --- monitor_series --------------------------------------------------------


def test_monitor_series_legacy_keyword():
    controller = _controller(
        keyword_rank_repository=FakeKeywordRankRepository(
            history=[SimpleNamespace(captured_at="2024-01-02", rank=5)]
        )
    )
    result = controller.monitor_series("keyword", "com.demo", "us", "en", "notes", days=0)
    assert result["charts"][0]["current"] == "#5"
    assert result["charts"][0]["invert"] is True


def test_monitor_series_legacy_chart():
    controller = _controller(
        chart_rank_repository=FakeChartRankRepository(
            history=[SimpleNamespace(captured_at="2024-01-02", rank=2)]
        )
    )
    result = controller.monitor_series("chart", "com.demo", "us", "en", "top_free|GAME", days=0)
    assert result["title"] == "top_free · GAME"
    assert result["charts"][0]["current"] == "#2"


def test_monitor_series_legacy_app_defaults_missing_metrics_to_dash():
    controller = _controller(
        snapshot_repository=FakeSnapshotRepository(
            history=[SimpleNamespace(captured_at="2024-01-02", title="Demo")]
        )
    )
    result = controller.monitor_series("app", "com.demo", "us", "en", "")
    ratings = result["charts"][0]
    assert ratings["current"] == "-"


def test_monitor_series_api_mode_resolves_platform_via_tracking_controller():
    api = FakeApi()
    api.keyword_history = [
        SimpleNamespace(captured_at="2024-01-02T00:00:00", rank=4, checked_limit=50)
    ]
    controller = _controller(api=api)

    result = controller.monitor_series("keyword", "com.demo", "us", "en", "notes", days=0)

    assert result["charts"][0]["current"] == "#4"
    assert controller.bridge._tracking_controller.calls == [("keyword", "com.demo", "notes")]


def test_monitor_series_swallows_exceptions():
    class BrokenSnapshotRepo:
        def get_history(self, *a, **k):
            raise RuntimeError("boom")

    controller = _controller(snapshot_repository=BrokenSnapshotRepo())
    result = controller.monitor_series("app", "com.demo", "us", "en", "")
    assert result == {"title": "", "subtitle": "", "charts": []}


# --- collect_dashboard --------------------------------------------------


def test_collect_dashboard_legacy_mode_assembles_stats_and_health():
    tracked_app = _tracked_app(enabled=True)
    ts = SimpleNamespace(
        list_apps=lambda: [tracked_app],
        list_keywords=lambda: [],
        list_chart_apps=lambda: [],
        monitor_overview=lambda: [
            SimpleNamespace(
                title="Demo",
                app_id="com.demo",
                latest_rating=4.5,
                latest_installs="1k+",
                unread_count=2,
                consecutive_failures=0,
                fail_status="normal",
                last_synced_at="",
            )
        ],
    )
    alert_service = SimpleNamespace(unread_count=lambda: 3, recent_alerts=lambda limit=6: [])
    controller = _controller(services={"tracking_service": ts, "alert_service": alert_service})

    dashboard = controller.collect_dashboard()

    assert dashboard["stats"][0]["value"] == 1
    assert dashboard["stats"][4]["value"] == 3
    assert dashboard["health"][0]["statusColor"] == "#16A34A"


def test_collect_dashboard_api_mode_health_only_includes_enabled_apps():
    api = FakeApi(
        tracked_apps=[_tracked_app(enabled=True), _tracked_app(app_id="com.off", enabled=False)],
        unread=1,
    )
    controller = _controller(api=api)

    dashboard = controller.collect_dashboard()

    assert len(dashboard["health"]) == 1
    assert dashboard["health"][0]["appId"] == "com.demo"


# --- collect_tracking --------------------------------------------------


def test_collect_tracking_legacy_mode_uses_rank_label_helpers():
    tracked_app = _tracked_app()
    keyword = SimpleNamespace(
        keyword="k1",
        app_id="com.demo",
        country="us",
        lang="en",
        frequency="daily",
        last_synced_at="",
        platform="google_play",
        enabled=True,
    )
    settings_service = SimpleNamespace(
        get_all=lambda: {"default_country": "us", "default_lang": "en", "default_limit": 50}
    )
    ts = SimpleNamespace(
        list_apps=lambda: [tracked_app], list_keywords=lambda: [keyword], list_chart_apps=lambda: []
    )
    keyword_service = SimpleNamespace(
        latest_rank=lambda *a: SimpleNamespace(found=False, rank=None)
    )
    controller = _controller(
        services={
            "tracking_service": ts,
            "settings_service": settings_service,
            "keyword_service": keyword_service,
        }
    )

    tracking = controller.collect_tracking()

    assert tracking["defaults"]["country"] == "us"
    assert tracking["keywords"][0]["rank"] == "未命中"


def test_collect_tracking_api_mode_uses_api_rank_labels():
    api = FakeApi(tracked_apps=[_tracked_app()])
    controller = _controller(api=api)

    tracking = controller.collect_tracking()

    assert tracking["apps"][0]["appId"] == "com.demo"


# --- collect_history --------------------------------------------------


def test_collect_history_legacy_mode_defaults_to_first_app_and_remembers_selection():
    apps = [_tracked_app(app_id="com.a"), _tracked_app(app_id="com.b")]
    ts = SimpleNamespace(list_apps=lambda: apps)
    controller = _controller(
        services={"tracking_service": ts},
        snapshot_repository=FakeSnapshotRepository(
            history=[SimpleNamespace(captured_at="t", title="A", rating=4.0)]
        ),
        keyword_rank_repository=FakeKeywordRankRepository(),
    )

    history = controller.collect_history()

    assert history["selected"] == "com.a"
    assert controller.bridge._history_selection == ("com.a", "us", "en")


def test_collect_history_legacy_mode_respects_prior_selection():
    apps = [_tracked_app(app_id="com.a"), _tracked_app(app_id="com.b")]
    ts = SimpleNamespace(list_apps=lambda: apps)
    controller = _controller(services={"tracking_service": ts})
    controller.bridge._history_selection = ("com.b", "us", "en")

    history = controller.collect_history()

    assert history["selected"] == "com.b"


def test_collect_history_api_mode_builds_snapshot_and_keyword_rows():
    api = FakeApi(
        tracked_apps=[_tracked_app()],
        app_snapshots=[
            SimpleNamespace(
                captured_at="t",
                title="Demo",
                rating=4.1,
                ratings_count=10,
                reviews_count=5,
                installs="1k+",
                version="1.0",
            )
        ],
        recent_keyword_ranks_for_history=[
            SimpleNamespace(captured_at="t", keyword="k1", rank=2, checked_limit=50)
        ],
    )
    controller = _controller(api=api)

    history = controller.collect_history()

    assert history["snapshots"][0]["version"] == "1.0"
    assert history["keywords"][0]["rank"] == 2
    assert controller.bridge._history_selection == ("com.demo", "us", "en")


# --- rank labels --------------------------------------------------


def test_keyword_rank_label_missing_service_returns_not_synced():
    controller = _controller(services={})
    item = SimpleNamespace(platform="google_play", keyword="k", app_id="a", country="us", lang="en")
    assert controller.keyword_rank_label(item) == "未同步"


def test_keyword_rank_label_uses_app_store_service_for_app_store_rows():
    calls = []
    service = SimpleNamespace(
        latest_rank=lambda *a: calls.append(a) or SimpleNamespace(found=True, rank=1)
    )
    controller = _controller(services={"keyword_service_app_store": service})
    item = SimpleNamespace(platform="app_store", keyword="k", app_id="a", country="us", lang="en")

    assert controller.keyword_rank_label(item) == "#1"
    assert calls


def test_chart_rank_label_not_found_returns_missed():
    service = SimpleNamespace(latest_rank=lambda *a: SimpleNamespace(found=True, rank=None))
    controller = _controller(services={"chart_rank_service": service})
    item = SimpleNamespace(app_id="a", collection="top_free", category="", country="us", lang="en")
    assert controller.chart_rank_label(item) == "未命中"


# --- health rows --------------------------------------------------


def test_health_row_maps_fail_status_to_color():
    item = SimpleNamespace(
        title="",
        app_id="com.demo",
        latest_rating=None,
        latest_installs=None,
        unread_count=0,
        consecutive_failures=2,
        fail_status="escalated",
        last_synced_at="",
    )
    row = DashboardController.health_row(item)
    assert row["statusColor"] == "#DC2626"
    assert row["title"] == "com.demo"


def test_health_row_from_tracked_defaults_metrics_to_dash():
    item = _tracked_app(consecutive_failures=1)
    row = DashboardController.health_row_from_tracked(item)
    assert row["rating"] == "-"
    assert row["statusColor"] == "#D97706"
