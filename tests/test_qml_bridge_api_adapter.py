from __future__ import annotations

import logging
import os
import time
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication

from app.constants import DEFAULT_SETTINGS
from app.schemas.app_schema import AppDetail, AppSummary
from app.schemas.chart_schema import ChartItem
from app.schemas.keyword_schema import KeywordRankResult
from app.schemas.review_schema import ReviewItem
from app.services.store_intel_api_client import StoreIntelApiCacheMiss
from app.ui.qml_bridge import QmlBridge
from app.utils.time_utils import now_iso


class FakeSettings:
    def __init__(self):
        self.values = {**DEFAULT_SETTINGS, "input_history": "{}"}

    def get_all(self):
        return dict(self.values)

    def get(self, key, default=""):
        return self.values.get(key, default)

    def set_many(self, values):
        self.values.update(values)


class FakeApi:
    enabled = True

    def __init__(self):
        self.calls = []
        self.settings = {**DEFAULT_SETTINGS, "input_history": "{}", "theme": "slate"}

    def search(self, keyword, country="us", lang="en", limit=50, platform="google_play"):
        self.calls.append(("search", keyword, country, lang, limit))
        return [AppSummary(app_id="com.remote", title="Remote App", has_iap=True)]

    def search_cached(self, keyword, country="us", lang="en", limit=50, platform="google_play"):
        self.calls.append(("search_cached", keyword, country, lang, limit))
        return [AppSummary(app_id="com.remote", title="Remote App", has_iap=True)]

    def app_detail(self, app_id, country="us", lang="en", platform="google_play"):
        self.calls.append(("app_detail", app_id, country, lang))
        return AppDetail(
            app_id=app_id,
            title="Remote Detail",
            developer="Remote Dev",
            rating=4.6,
            free=True,
            categories=["Tools"],
        )

    def cached_app_detail(self, app_id, country="us", lang="en", platform="google_play"):
        self.calls.append(("cached_app_detail", app_id, country, lang))
        return AppDetail(
            app_id=app_id,
            title="Remote Detail",
            developer="Remote Dev",
            rating=4.6,
            free=True,
            categories=["Tools"],
            permissions={"Location": ["approximate location"]},
        )

    def similar_apps(self, app_id, country="us", lang="en", limit=10, platform="google_play"):
        self.calls.append(("similar_apps", app_id, country, lang, limit))
        return [AppSummary(app_id="com.related", title="Related App", rating=4.2)]

    def permissions(self, app_id, country="us", lang="en", platform="google_play"):
        self.calls.append(("permissions", app_id, country, lang))
        return {"Location": ["approximate location"]}

    def reviews(
        self,
        app_id,
        country="us",
        lang="en",
        sort="newest",
        continuation_token=None,
        limit=20,
        platform="google_play",
    ):
        self.calls.append(("reviews", app_id, country, lang, sort, continuation_token))
        return [ReviewItem(app_id=app_id, review_id="r1", rating=5, content="great")], None

    def fetch_chart(self, chart_type, category, country, lang, limit, platform="google_play"):
        self.calls.append(("fetch_chart", chart_type, category, country, lang, limit))
        return [
            ChartItem(
                app_id="com.remote",
                title="Remote App",
                rank=1,
                chart_type=chart_type,
                category=category,
                country=country,
                lang=lang,
            )
        ]

    def fetch_chart_cached(
        self, chart_type, category, country, lang, limit, platform="google_play"
    ):
        self.calls.append(("fetch_chart_cached", chart_type, category, country, lang, limit))
        return [
            ChartItem(
                app_id="com.remote",
                title="Remote App",
                rank=1,
                chart_type=chart_type,
                category=category,
                country=country,
                lang=lang,
            )
        ]

    def rank_keyword(self, keyword, app_id, country="us", lang="en", limit=100, platform="google_play"):
        self.calls.append(("rank_keyword", keyword, app_id, country, lang, limit))
        return KeywordRankResult(
            keyword=keyword,
            app_id=app_id,
            country=country,
            lang=lang,
            found=True,
            rank=1,
            checked_limit=limit,
            captured_at="2026-06-18T00:00:00Z",
            results=[AppSummary(app_id=app_id, title="Remote App")],
        )

    def cached_keyword_rank(
        self, keyword, app_id, country="us", lang="en", limit=100, platform="google_play"
    ):
        self.calls.append(("cached_keyword_rank", keyword, app_id, country, lang, limit))
        return KeywordRankResult(
            keyword=keyword,
            app_id=app_id,
            country=country,
            lang=lang,
            found=True,
            rank=1,
            checked_limit=limit,
            captured_at="2026-06-18T00:00:00Z",
            results=[AppSummary(app_id=app_id, title="Remote App")],
        )

    def analyze_coverage(
        self,
        app_id,
        country="us",
        lang="en",
        limit=50,
        deep=False,
        candidates=None,
        canonical_app_id=None,
        platform="google_play",
    ):
        self.calls.append(
            (
                "analyze_coverage",
                app_id,
                country,
                lang,
                limit,
                deep,
                tuple(candidates or []),
                canonical_app_id or "",
            )
        )
        return SimpleNamespace(
            platform="google_play",
            app_id=app_id,
            canonical_app_id=canonical_app_id or app_id,
            country=country,
            lang=lang,
            candidates=["notes"],
            candidate_count=1,
            covered=[{"keyword": "notes", "rank": 1}],
            checked_limit=limit,
        )

    def cached_coverage(self, app_id, country="us", lang="en", deep=False, platform="google_play"):
        self.calls.append(("cached_coverage", app_id, country, lang, deep))
        return SimpleNamespace(
            platform="google_play",
            app_id=app_id,
            canonical_app_id=app_id,
            country=country,
            lang=lang,
            candidates=["notes"],
            candidate_count=1,
            covered=[{"keyword": "notes", "rank": 1}],
            checked_limit=50,
        )

    def analyze_coverage_stream(
        self,
        app_id,
        country="us",
        lang="en",
        limit=50,
        deep=False,
        candidates=None,
        canonical_app_id=None,
        progress=None,
        platform="google_play",
    ):
        self.calls.append(
            (
                "analyze_coverage_stream",
                app_id,
                country,
                lang,
                limit,
                deep,
                tuple(candidates or []),
                canonical_app_id or "",
            )
        )
        if progress is not None:
            progress("覆盖检测 1/1：notes", 1.0)
        return SimpleNamespace(
            platform="google_play",
            app_id=app_id,
            canonical_app_id=canonical_app_id or app_id,
            country=country,
            lang=lang,
            candidates=["notes"],
            candidate_count=1,
            covered=[{"keyword": "notes", "rank": 1}],
            checked_limit=limit,
        )

    def get_settings(self):
        self.calls.append(("get_settings",))
        return dict(self.settings)

    def set_settings(self, values):
        self.calls.append(("set_settings", dict(values)))
        self.settings.update(values)
        return dict(self.settings)

    def list_tracked_apps(self, enabled=None, platform=""):
        self.calls.append(("list_tracked_apps",))
        return [
            SimpleNamespace(
                app_id="com.remote",
                title="Remote App",
                country="us",
                lang="en",
                frequency="daily",
                tag="core",
                enabled=True,
                last_synced_at="",
                consecutive_failures=0,
            )
        ]

    def list_tracked_keywords(self, enabled=None, platform=""):
        self.calls.append(("list_tracked_keywords",))
        return [
            SimpleNamespace(
                platform="google_play",
                keyword="notes",
                app_id="com.remote",
                country="us",
                lang="en",
                frequency="daily",
                enabled=True,
                last_synced_at="",
                consecutive_failures=0,
            )
        ]

    def list_tracked_chart_apps(self, enabled=None, platform=""):
        self.calls.append(("list_tracked_chart_apps",))
        return [
            SimpleNamespace(
                app_id="com.remote",
                collection="top_free",
                category="APPLICATION",
                country="us",
                lang="en",
                frequency="daily",
                enabled=True,
                last_synced_at="",
                consecutive_failures=0,
            )
        ]

    def list_app_snapshots(self, app_id, country="us", lang="en", limit=80, platform="google_play"):
        self.calls.append(("list_app_snapshots", app_id, country, lang, limit))
        rows = [
            SimpleNamespace(
                platform="google_play",
                app_id=app_id,
                country=country,
                lang=lang,
                captured_at="2026-06-17T00:00:00Z",
                title="Remote App",
                rating=4.5,
                ratings_count=100,
                reviews_count=20,
                installs="1,000+",
                min_installs=1000,
                real_installs=1200,
                version="1.0.0",
            ),
            SimpleNamespace(
                platform="google_play",
                app_id=app_id,
                country=country,
                lang=lang,
                captured_at="2026-06-18T00:00:00Z",
                title="Remote App",
                rating=4.6,
                ratings_count=120,
                reviews_count=25,
                installs="1,000+",
                min_installs=1000,
                real_installs=1300,
                version="1.1.0",
            ),
        ]
        return rows[:limit] if limit else rows

    def list_recent_app_snapshots(self, limit=8):
        self.calls.append(("list_recent_app_snapshots", limit))
        return list(reversed(self.list_app_snapshots("com.remote", "us", "en", limit=limit)))

    def count_app_snapshots(self):
        self.calls.append(("count_app_snapshots",))
        return 2

    def list_cached_reviews(self, app_id, limit=10, platform="google_play"):
        self.calls.append(("list_cached_reviews", app_id, limit))
        return [ReviewItem(app_id=app_id, review_id="cached", rating=4, content="cached review")]

    def list_keyword_rank_history(
        self, keyword, app_id, country="us", lang="en", limit=0, platform="google_play"
    ):
        self.calls.append(("list_keyword_rank_history", keyword, app_id, country, lang, limit))
        return [
            SimpleNamespace(
                platform="google_play",
                keyword=keyword,
                app_id=app_id,
                country=country,
                lang=lang,
                found=True,
                rank=3,
                checked_limit=10,
                captured_at="2026-06-17T00:00:00Z",
            ),
            SimpleNamespace(
                platform="google_play",
                keyword=keyword,
                app_id=app_id,
                country=country,
                lang=lang,
                found=True,
                rank=1,
                checked_limit=10,
                captured_at="2026-06-18T00:00:00Z",
            ),
        ][: limit or None]

    def list_recent_keyword_ranks(self, *, app_id="", country="", lang="", limit=8, platform=""):
        self.calls.append(("list_recent_keyword_ranks", app_id, country, lang, limit))
        rows = list(
            reversed(
                self.list_keyword_rank_history(
                    "notes", app_id or "com.remote", country or "us", lang or "en"
                )
            )
        )
        return rows[:limit]

    def latest_keyword_rank_label(self, keyword, app_id, country="us", lang="en", platform="google_play"):
        self.calls.append(("latest_keyword_rank_label", keyword, app_id, country, lang, platform))
        return "#1"

    def latest_chart_rank_label(
        self, app_id, collection, category, country="us", lang="en", platform="google_play"
    ):
        self.calls.append(
            ("latest_chart_rank_label", app_id, collection, category, country, lang, platform)
        )
        return "#2"

    def list_chart_rank_history(
        self,
        app_id,
        collection,
        category="APPLICATION",
        country="us",
        lang="en",
        limit=0,
        platform="google_play",
    ):
        self.calls.append(
            ("list_chart_rank_history", app_id, collection, category, country, lang, limit)
        )
        rows = [
            SimpleNamespace(
                app_id=app_id,
                collection=collection,
                category=category,
                country=country,
                lang=lang,
                found=True,
                rank=4,
                checked_limit=10,
                captured_at="2026-06-17T00:00:00Z",
            ),
            SimpleNamespace(
                app_id=app_id,
                collection=collection,
                category=category,
                country=country,
                lang=lang,
                found=True,
                rank=2,
                checked_limit=10,
                captured_at="2026-06-18T00:00:00Z",
            ),
        ]
        return rows[:limit] if limit else rows

    def list_alerts(self, *, limit=200, **kwargs):
        self.calls.append(("list_alerts", limit, kwargs))
        return [
            SimpleNamespace(
                id=7,
                type="rating_drop",
                severity="high",
                app_id="com.remote",
                message="drop",
                is_read=False,
                created_at="2026-06-18T00:00:00Z",
            )
        ]

    def unread_count(self):
        self.calls.append(("unread_count",))
        return 1

    def add_tracked_app(
        self, app_id, country="us", lang="en", frequency="daily", tag="", platform="google_play"
    ):
        self.calls.append(("add_tracked_app", app_id, country, lang, frequency, tag))
        return SimpleNamespace(app_id=app_id)

    def add_tracked_keyword(self, keyword, app_id, country="us", lang="en", platform="google_play"):
        self.calls.append(("add_tracked_keyword", keyword, app_id, country, lang, platform))
        return SimpleNamespace(keyword=keyword, app_id=app_id)

    def add_tracked_chart_app(
        self,
        app_id,
        collection,
        category="APPLICATION",
        country="us",
        lang="en",
        frequency="daily",
        platform="google_play",
    ):
        self.calls.append(("add_tracked_chart_app", app_id, collection, category, country, lang))
        return SimpleNamespace(app_id=app_id)

    def sync_app_now(self, app_id, country="us", lang="en", platform="google_play"):
        self.calls.append(("sync_app_now", app_id, country, lang))
        return AppDetail(app_id=app_id, title="Synced Detail", free=True)

    def sync_all(self, due_only=False):
        self.calls.append(("sync_all", due_only))
        return {"apps": 1, "keywords": 2, "charts": 3}

    def request_refresh(self, kind, **kwargs):
        self.calls.append(("request_refresh", kind, kwargs))
        return SimpleNamespace(job_id=f"job-{len(self.calls)}", status="queued", kind=kind)

    def save_reviews(self, app_id, country, lang, items, platform="google_play"):
        self.calls.append(("save_reviews", app_id, country, lang, len(items), platform))
        return len(items)

    def wait_refresh_job(self, job_id, *, timeout=60.0, interval=1.0):
        self.calls.append(("wait_refresh_job", job_id, timeout, interval))
        return SimpleNamespace(job_id=job_id, status="completed")

    def mark_alerts_read(self, ids=None):
        self.calls.append(("mark_alerts_read", ids or []))
        return 1

    def cleanup_history(self):
        self.calls.append(("cleanup_history",))
        return {"snapshots": 1, "keywords": 2, "charts": 3, "alerts": 4, "reviews": 5}

    def remove_tracked_app(self, app_id, country="us", lang="en", platform="google_play"):
        self.calls.append(("remove_tracked_app", app_id, country, lang))
        return 1

    def set_tracked_app_enabled(self, app_id, enabled, country="us", lang="en", platform="google_play"):
        self.calls.append(("set_tracked_app_enabled", app_id, enabled, country, lang))
        return SimpleNamespace(updated=1, enabled=enabled)

    def set_tracked_app_frequency(
        self, app_id, frequency, country="us", lang="en", platform="google_play"
    ):
        self.calls.append(("set_tracked_app_frequency", app_id, frequency, country, lang))
        return SimpleNamespace(updated=1, frequency=frequency)

    def set_tracked_app_tag(self, app_id, tag, country="us", lang="en", platform="google_play"):
        self.calls.append(("set_tracked_app_tag", app_id, tag, country, lang))
        return SimpleNamespace(updated=1, tag=tag)

    def remove_tracked_keyword(
        self, keyword, app_id, country="us", lang="en", platform="google_play"
    ):
        self.calls.append(("remove_tracked_keyword", keyword, app_id, country, lang, platform))
        return 1

    def set_tracked_keyword_enabled(
        self, keyword, app_id, enabled, country="us", lang="en", platform="google_play"
    ):
        self.calls.append(
            ("set_tracked_keyword_enabled", keyword, app_id, enabled, country, lang, platform)
        )
        return SimpleNamespace(updated=1, enabled=enabled)

    def set_tracked_keyword_frequency(
        self, keyword, app_id, frequency, country="us", lang="en", platform="google_play"
    ):
        self.calls.append(
            ("set_tracked_keyword_frequency", keyword, app_id, frequency, country, lang, platform)
        )
        return SimpleNamespace(updated=1, frequency=frequency)

    def sync_tracked_keyword_now(
        self, keyword, app_id, country="us", lang="en", platform="google_play", limit=100
    ):
        self.calls.append(
            ("sync_tracked_keyword_now", keyword, app_id, country, lang, platform, limit)
        )
        return KeywordRankResult(
            keyword=keyword,
            app_id=app_id,
            country=country,
            lang=lang,
            found=True,
            rank=1,
            checked_limit=limit,
            captured_at="2026-06-18T00:00:00Z",
        )

    def remove_tracked_chart_app(
        self, app_id, collection, category="APPLICATION", country="us", lang="en", platform="google_play"
    ):
        self.calls.append(("remove_tracked_chart_app", app_id, collection, category, country, lang))
        return 1

    def set_tracked_chart_app_enabled(
        self,
        app_id,
        collection,
        enabled,
        category="APPLICATION",
        country="us",
        lang="en",
        platform="google_play",
    ):
        self.calls.append(
            ("set_tracked_chart_app_enabled", app_id, collection, enabled, category, country, lang)
        )
        return SimpleNamespace(updated=1, enabled=enabled)

    def sync_tracked_chart_app_now(
        self,
        app_id,
        collection,
        category="APPLICATION",
        country="us",
        lang="en",
        limit=100,
        platform="google_play",
    ):
        self.calls.append(
            ("sync_tracked_chart_app_now", app_id, collection, category, country, lang, limit)
        )
        return SimpleNamespace(
            app_id=app_id,
            collection=collection,
            category=category,
            country=country,
            lang=lang,
            found=True,
            rank=2,
            checked_limit=limit,
            captured_at="2026-06-18T00:00:00Z",
        )


class FakeGooglePlay:
    def similar(self, app_id, country="us", lang="en", limit=10):
        return []


class FakeTracking:
    def get_history(self, app_id, country="us", lang="en"):
        return []


class FakeAlerts:
    def list_alerts(self, app_id=None, limit=8):
        return []


class FakeReviews:
    def list_cached(self, app_id, limit=10):
        return []


class FakeUpdateService:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def current_label(self):
        return "开发版"

    def check(self):
        self.calls += 1
        return self.result


def _wait_idle(app, bridge, timeout=10.0):
    deadline = time.time() + timeout
    while bridge._workers and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    for _ in range(5):
        app.processEvents()
    assert not bridge._workers, "a bridge worker did not finish in time"


def test_qml_bridge_quiet_update_check_prompts_once_per_version():
    app = QApplication.instance() or QApplication([])
    update_service = FakeUpdateService(
        SimpleNamespace(
            mode="patch",
            error=None,
            up_to_date=False,
            can_patch=True,
            local_label="2026.06.24.1000",
            latest_label="2026.06.24.1100",
            latest_version=2,
            changelog="修复关键词排名显示",
        )
    )
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": FakeApi(),
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
            "update_service": update_service,
        },
        logger=logging.getLogger("qml-api-test"),
    )
    prompts = []
    bridge.updatePrompt.connect(lambda title, message: prompts.append((title, message)))

    bridge.checkUpdatesQuietly()
    _wait_idle(app, bridge)
    bridge.dismissUpdate()
    bridge.checkUpdatesQuietly()
    _wait_idle(app, bridge)

    assert update_service.calls == 2
    assert len(prompts) == 1
    assert "发现新版本" in prompts[0][0]
    assert "修复关键词排名显示" in prompts[0][1]


def test_qml_bridge_prefers_store_intel_api_for_google_play_core_pages():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )

    bridge.searchApps("notes", "us", "en", "10")
    _wait_idle(app, bridge)
    assert bridge.search["rows"][0]["appId"] == "com.remote"

    bridge.fetchAppDetail("com.remote", "us", "en")
    _wait_idle(app, bridge)
    assert bridge.detail["loaded"] is True
    assert bridge.detail["title"] == "Remote Detail"
    assert bridge.detail["similar"] == []

    bridge.fetchDetailPermissions()
    _wait_idle(app, bridge)
    assert bridge.detail["permissionsLoaded"] is True
    assert bridge.detail["permissions"][0]["group"] == "Location"

    bridge.fetchReviews("com.remote", "us", "en", "newest")
    _wait_idle(app, bridge)
    assert bridge.reviews["rows"][0]["content"] == "cached review"

    bridge.fetchChart("top_free", "", "us", "en", "10")
    _wait_idle(app, bridge)
    assert bridge.charts["rows"][0]["rank"] == 1

    bridge.fetchKeywordRank("notes", "com.remote", "us", "en", "10")
    _wait_idle(app, bridge)
    assert "前 30 条内排名 #1" in bridge.keywords["summary"]
    assert ("cached_keyword_rank", "notes", "com.remote", "us", "en", 30) in api.calls
    assert bridge.keywords["rows"] == [
        {
            "rank": 1,
            "iconUrl": "",
            "title": "Remote App",
            "appId": "com.remote",
            "developer": "-",
            "rating": "-",
            "installs": "-",
            "hit": True,
        }
    ]
    assert bridge._keyword_result_remote is True

    progress_events = []
    bridge.coverageProgress.connect(
        lambda message, fraction: progress_events.append((message, fraction))
    )
    bridge.discoverCoverage("com.remote", "us", "en", False)
    _wait_idle(app, bridge)
    assert bridge.coverage["rows"][0]["keyword"] == "notes"
    assert bridge.coverage["rows"][0]["rank"] == 1
    assert ("覆盖检测 1/1：notes", 1.0) not in progress_events

    bridge.loadCoverageTrend("notes")
    _wait_idle(app, bridge)
    assert bridge.coverageTrend["keyword"] == "notes"
    assert bridge.coverageTrend["values"] == [3, 1]
    assert bridge.coverageTrend["current"] == "当前 #1"
    assert (
        "list_keyword_rank_history",
        "notes",
        "com.remote",
        "us",
        "en",
        90,
    ) in api.calls

    call_names = [call[0] for call in api.calls]
    for expected in (
        "search_cached",
        "cached_app_detail",
        "list_app_snapshots",
        "list_cached_reviews",
        "fetch_chart_cached",
        "cached_keyword_rank",
        "cached_coverage",
    ):
        assert expected in call_names
    for blocked in (
        "search",
        "app_detail",
        "similar_apps",
        "permissions",
        "reviews",
        "fetch_chart",
        "rank_keyword",
        "analyze_coverage_stream",
    ):
        assert blocked not in call_names


def test_qml_bridge_waits_search_refresh_job_on_cache_miss():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()
    calls = {"search_cached": 0}

    def search_cached(keyword, country="us", lang="en", limit=50, platform="google_play"):
        calls["search_cached"] += 1
        api.calls.append(("search_cached", keyword, country, lang, limit))
        if calls["search_cached"] == 1:
            return []
        return [AppSummary(app_id="com.refreshed", title="Refreshed App", has_iap=False)]

    api.search_cached = search_cached
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )

    bridge.searchApps("notes", "us", "en", "10")
    _wait_idle(app, bridge)

    assert bridge.search["rows"][0]["appId"] == "com.refreshed"
    assert calls["search_cached"] == 2
    assert any(call[0] == "request_refresh" and call[1] == "search" for call in api.calls)
    assert any(call[0] == "wait_refresh_job" for call in api.calls)


def test_qml_bridge_refreshes_incomplete_search_cache_for_display_fields():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()
    calls = {"search_cached": 0}

    def search_cached(keyword, country="us", lang="en", limit=50, platform="google_play"):
        calls["search_cached"] += 1
        api.calls.append(("search_cached", keyword, country, lang, limit))
        if calls["search_cached"] == 1:
            return [
                AppSummary(
                    app_id="com.hotshotai",
                    title="Hotshot AI: Photo Generator",
                    category="PHOTOGRAPHY",
                    summary="Create AI meme photos.",
                    price="0",
                    icon_url="https://example.test/icon.png",
                )
            ]
        return [
            AppSummary(
                app_id="com.hotshotai",
                title="Hotshot AI: Photo Generator",
                developer="Hotshot Studio",
                category="PHOTOGRAPHY",
                summary="Create AI meme photos.",
                rating=4.7,
                ratings_count=1200,
                installs="100K+",
                price="0",
                icon_url="https://example.test/icon.png",
            )
        ]

    api.search_cached = search_cached
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )

    bridge.searchApps("hotshotai", "us", "en", "10")
    _wait_idle(app, bridge)

    row = bridge.search["rows"][0]
    assert row["title"] == "Hotshot AI: Photo Generator"
    assert row["developer"] == "Hotshot Studio"
    assert row["rating"] == 4.7
    assert row["ratings"] == "1,200"
    assert row["installs"] == "100K+"
    assert row["category"] == "PHOTOGRAPHY"
    assert row["summary"] == "Create AI meme photos."
    assert calls["search_cached"] == 2
    assert any(call[0] == "request_refresh" and call[1] == "search" for call in api.calls)
    assert any(call[0] == "wait_refresh_job" for call in api.calls)


def test_qml_bridge_shows_incomplete_search_cache_before_background_refresh():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()
    calls = {"search_cached": 0}

    def search_cached(keyword, country="us", lang="en", limit=50, platform="google_play"):
        calls["search_cached"] += 1
        api.calls.append(("search_cached", keyword, country, lang, limit))
        if calls["search_cached"] == 1:
            return [
                AppSummary(
                    app_id="com.hauljoy.aiadvice",
                    title="Hauljoy AI: Shopping Assistant",
                    category="SHOPPING",
                    summary="AI shopping helper.",
                )
            ]
        return [
            AppSummary(
                app_id="com.hauljoy.aiadvice",
                title="Hauljoy AI: Shopping Assistant",
                developer="Hauljoy",
                category="SHOPPING",
                summary="AI shopping helper.",
                rating=4.8,
                ratings_count=2400,
                installs="10K+",
            )
        ]

    def wait_refresh_job(job_id, *, timeout=60.0, interval=1.0):
        api.calls.append(("wait_refresh_job", job_id, timeout, interval))
        time.sleep(0.2)
        return SimpleNamespace(job_id=job_id, status="completed")

    api.search_cached = search_cached
    api.wait_refresh_job = wait_refresh_job
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )

    bridge.searchApps("hauljoy", "us", "en", "10")
    deadline = time.time() + 2.0
    while not bridge.search["rows"] and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)

    assert bridge.search["rows"][0]["appId"] == "com.hauljoy.aiadvice"
    assert bridge.search["rows"][0]["developer"] == "-"
    assert bridge.search["rows"][0]["rating"] == "-"

    _wait_idle(app, bridge)

    assert bridge.search["rows"][0]["developer"] == "Hauljoy"
    assert bridge.search["rows"][0]["rating"] == 4.8
    assert bridge.search["rows"][0]["ratings"] == "2,400"
    assert bridge.search["rows"][0]["installs"] == "10K+"
    assert calls["search_cached"] == 2
    assert any(call[0] == "request_refresh" and call[1] == "search" for call in api.calls)


def test_qml_bridge_refreshes_app_detail_cache_on_miss():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()
    cache_reads = {"count": 0}

    def cached_detail(app_id, country="us", lang="en", platform="google_play"):
        cache_reads["count"] += 1
        api.calls.append(("cached_app_detail", app_id, country, lang))
        if cache_reads["count"] == 1:
            raise StoreIntelApiCacheMiss("暂无应用详情缓存。")
        return AppDetail(
            app_id=app_id,
            title="Synced Cache Detail",
            developer="Remote Dev",
            rating=4.9,
            free=True,
        )

    api.cached_app_detail = cached_detail
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )

    bridge.fetchAppDetail("com.remote", "us", "en")
    _wait_idle(app, bridge)

    assert bridge.detail["loaded"] is True
    assert bridge.detail["title"] == "Synced Cache Detail"
    assert cache_reads["count"] == 2
    assert (
        "request_refresh",
        "app",
        {"app_id": "com.remote", "country": "us", "lang": "en", "platform": "google_play"},
    ) in api.calls
    assert any(call[0] == "wait_refresh_job" for call in api.calls)
    assert "app_detail" not in [call[0] for call in api.calls]


def test_qml_bridge_refreshes_incomplete_app_detail_cache():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()
    cache_reads = {"count": 0}

    def cached_detail(app_id, country="us", lang="en", platform="google_play"):
        cache_reads["count"] += 1
        api.calls.append(("cached_app_detail", app_id, country, lang))
        if cache_reads["count"] == 1:
            return AppDetail(
                app_id=app_id,
                title="Shallow Cache Detail",
                summary="Only summary fields came back.",
                android_version="ANDROID",
                icon_url="https://example.test/icon.png",
                free=True,
            )
        return AppDetail(
            app_id=app_id,
            title="Refreshed Cache Detail",
            summary="Fresh complete detail.",
            developer="Remote Dev",
            rating=4.8,
            ratings_count=2400,
            reviews_count=120,
            installs="10K+",
            min_installs=10000,
            real_installs=12345,
            android_version="ANDROID",
            icon_url="https://example.test/icon.png",
            has_iap=False,
            free=True,
        )

    api.cached_app_detail = cached_detail
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )

    bridge.fetchAppDetail("com.remote", "us", "en")
    _wait_idle(app, bridge)

    assert bridge.detail["loaded"] is True
    assert bridge.detail["title"] == "Refreshed Cache Detail"
    assert bridge.detail["developer"] == "Remote Dev"
    metrics = {row["label"]: row["value"] for row in bridge.detail["metrics"]}
    assert metrics["评分"] == "4.80"
    assert metrics["评分数"] == "2,400"
    assert metrics["安装量"] == "10K+"
    assert cache_reads["count"] == 2
    assert (
        "request_refresh",
        "app",
        {"app_id": "com.remote", "country": "us", "lang": "en", "platform": "google_play"},
    ) in api.calls
    assert any(call[0] == "wait_refresh_job" for call in api.calls)


def test_qml_bridge_waits_chart_refresh_job_on_cache_miss():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()
    cache_reads = {"count": 0}

    def fetch_chart_cached(chart_type, category, country, lang, limit, platform="google_play"):
        cache_reads["count"] += 1
        api.calls.append(("fetch_chart_cached", chart_type, category, country, lang, limit))
        if cache_reads["count"] == 1:
            return []
        return [
            ChartItem(
                app_id="com.refreshed.chart",
                title="Refreshed Chart App",
                rank=7,
                chart_type=chart_type,
                category=category,
                country=country,
                lang=lang,
            )
        ]

    api.fetch_chart_cached = fetch_chart_cached
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )

    bridge.fetchChart("top_free", "", "us", "en", "10")
    _wait_idle(app, bridge)

    assert bridge.charts["rows"][0]["appId"] == "com.refreshed.chart"
    assert bridge.charts["rows"][0]["rank"] == 7
    assert cache_reads["count"] == 2
    assert any(call[0] == "request_refresh" and call[1] == "chart" for call in api.calls)
    assert any(call[0] == "wait_refresh_job" for call in api.calls)


def test_qml_bridge_ignores_stale_app_detail_result():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()

    def cached_detail(app_id, country="us", lang="en", platform="google_play"):
        api.calls.append(("cached_app_detail", app_id, country, lang))
        if app_id == "com.slow":
            time.sleep(0.2)
            return AppDetail(app_id=app_id, title="Slow Detail", rating=4.0)
        return AppDetail(app_id=app_id, title="Fast Detail", rating=4.8)

    api.cached_app_detail = cached_detail
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )

    bridge.fetchAppDetail("com.slow", "ca", "fr")
    bridge.fetchAppDetail("com.fast", "us", "en")
    _wait_idle(app, bridge)

    assert bridge.detail["appId"] == "com.fast"
    assert bridge.detail["title"] == "Fast Detail"


def test_qml_bridge_allows_app_store_platform_switch_in_api_mode():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )
    errors = []
    bridge.errorMessage.connect(errors.append)
    statuses = []
    bridge.statusMessage.connect(statuses.append)

    bridge.setPlatform("app_store")
    app.processEvents()

    assert bridge.platform == "app_store"
    assert not errors
    assert statuses
    assert "App Store" in statuses[-1]


def test_qml_bridge_add_app_rejects_numeric_id_on_google_play_platform():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )
    errors = []
    bridge.errorMessage.connect(errors.append)

    assert bridge.platform == "google_play"
    # A purely-numeric id looks like an App Store id, not a Google Play
    # package name — must be rejected so it can never collide with an
    # App Store row sharing the same (app_id, country, lang).
    bridge.addApp("587366035", "us", "en", "daily")
    _wait_idle(app, bridge)

    assert errors
    assert not any(call[0] == "add_tracked_app" for call in api.calls)


def test_qml_bridge_add_chart_app_rejects_numeric_id_on_google_play_platform():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )
    errors = []
    bridge.errorMessage.connect(errors.append)

    assert bridge.platform == "google_play"
    bridge.addChartApp("587366035", "top_free", "APPLICATION", "us", "en")
    _wait_idle(app, bridge)

    assert errors
    assert not any(call[0] == "add_tracked_chart_app" for call in api.calls)


def test_qml_bridge_dashboard_ignores_optional_keyword_history_api_error():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()

    def fail_keyword_history(keyword, app_id, country="us", lang="en", limit=0, platform="google_play"):
        api.calls.append(("list_keyword_rank_history", keyword, app_id, country, lang, limit))
        raise RuntimeError("internal error (STORE_INTEL_INTERNAL_ERROR)")

    api.list_keyword_rank_history = fail_keyword_history
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )
    errors = []
    bridge.errorMessage.connect(errors.append)

    bridge.refreshDashboard()
    _wait_idle(app, bridge)

    assert not errors
    assert bridge.dashboard["stats"][0]["value"] == 1
    # tracked keyword still names the card; only the series is empty
    assert bridge.dashboard["keywordName"] == "notes"
    assert bridge.dashboard["keywordValues"] == []


def test_qml_bridge_dashboard_tolerates_snapshot_without_rating():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()

    def list_app_snapshots(app_id, country="us", lang="en", limit=80, platform="google_play"):
        api.calls.append(("list_app_snapshots", app_id, country, lang, limit))
        return [
            SimpleNamespace(
                platform="google_play",
                app_id=app_id,
                country=country,
                lang=lang,
                captured_at="2026-06-18T00:00:00Z",
                title="Remote App",
            )
        ]

    api.list_app_snapshots = list_app_snapshots
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )
    errors = []
    bridge.errorMessage.connect(errors.append)

    bridge.refreshDashboard()
    _wait_idle(app, bridge)

    assert not errors
    assert bridge.dashboard["ratingLabels"] == ["06-18 00:00"]
    assert bridge.dashboard["ratingValues"] == [0]


def test_qml_bridge_async_monitor_tree_and_series():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )
    errors = []
    bridge.errorMessage.connect(errors.append)
    trees = []
    series = []
    bridge.monitorTreeReady.connect(trees.append)
    bridge.monitorSeriesReady.connect(series.append)

    bridge.requestMonitorTree()
    bridge.requestMonitorSeries("app", "com.remote", "us", "en", "", 30)
    _wait_idle(app, bridge)

    assert not errors
    assert trees and trees[-1]["apps"][0]["appId"] == "com.remote"
    assert trees[-1]["apps"][0]["keywords"][0]["rank"] == "#1"
    assert series and series[-1]["charts"][0]["current"] == "4.60"


def test_qml_bridge_guarded_applier_drops_stale_results():
    QApplication.instance() or QApplication([])
    api = FakeApi()
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )

    applied = []
    guard = bridge._guarded("_reviews_request_id", bridge._reviews_request_id, applied.append)
    guard("fresh")
    assert applied == ["fresh"]

    stale_guard = bridge._guarded("_reviews_request_id", bridge._reviews_request_id, applied.append)
    bridge._reviews_request_id += 1  # a newer fetch supersedes the in-flight one
    stale_guard("stale")
    assert applied == ["fresh"]

    # switching platform must invalidate every in-flight fetch
    before = (
        bridge._search_request_id,
        bridge._chart_request_id,
        bridge._keyword_request_id,
        bridge._reviews_request_id,
    )
    bridge.setPlatform("app_store")
    after = (
        bridge._search_request_id,
        bridge._chart_request_id,
        bridge._keyword_request_id,
        bridge._reviews_request_id,
    )
    assert all(now > prev for now, prev in zip(after, before))


def test_qml_bridge_tracking_rank_labels_use_tracked_item_platform():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()

    def app_store_keywords(enabled=None, platform=""):
        api.calls.append(("list_tracked_keywords",))
        return [
            SimpleNamespace(
                platform="app_store",
                keyword="notes",
                app_id="310633997",
                country="us",
                lang="en",
                frequency="daily",
                enabled=True,
                last_synced_at="",
                consecutive_failures=0,
            )
        ]

    def app_store_charts(enabled=None, platform=""):
        api.calls.append(("list_tracked_chart_apps",))
        return [
            SimpleNamespace(
                platform="app_store",
                app_id="310633997",
                collection="top_free",
                category="6014",
                country="us",
                lang="en",
                frequency="daily",
                enabled=True,
                last_synced_at="",
                consecutive_failures=0,
            )
        ]

    api.list_tracked_keywords = app_store_keywords
    api.list_tracked_chart_apps = app_store_charts
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )
    errors = []
    bridge.errorMessage.connect(errors.append)

    bridge.refreshTracking()
    _wait_idle(app, bridge)

    assert not errors
    kw_calls = [call for call in api.calls if call[0] == "latest_keyword_rank_label"]
    chart_calls = [call for call in api.calls if call[0] == "latest_chart_rank_label"]
    assert kw_calls and all(call[-1] == "app_store" for call in kw_calls)
    assert chart_calls and all(call[-1] == "app_store" for call in chart_calls)


def test_qml_bridge_dashboard_trends_empty_without_tracked_items():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()

    def no_tracked_apps(enabled=None, platform=""):
        api.calls.append(("list_tracked_apps",))
        return []

    def no_tracked_keywords(enabled=None, platform=""):
        api.calls.append(("list_tracked_keywords",))
        return []

    api.list_tracked_apps = no_tracked_apps
    api.list_tracked_keywords = no_tracked_keywords
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )
    errors = []
    bridge.errorMessage.connect(errors.append)

    bridge.refreshDashboard()
    _wait_idle(app, bridge)

    assert not errors
    # nothing tracked -> no trend at all, and no global /recent fallback
    assert bridge.dashboard["ratingAppName"] == ""
    assert bridge.dashboard["ratingValues"] == []
    assert bridge.dashboard["keywordName"] == ""
    assert bridge.dashboard["keywordValues"] == []
    assert not any(call[0] == "list_app_snapshots" for call in api.calls)
    assert not any(call[0] == "list_keyword_rank_history" for call in api.calls)
    assert not any(call[0] == "list_recent_app_snapshots" for call in api.calls)
    assert not any(call[0] == "list_recent_keyword_ranks" for call in api.calls)


def test_qml_bridge_tracking_tolerates_app_without_tag():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()

    def list_tracked_apps():
        api.calls.append(("list_tracked_apps",))
        return [
            SimpleNamespace(
                app_id="com.remote",
                title="Remote App",
                country="us",
                lang="en",
                frequency="daily",
                enabled=True,
                last_synced_at="2026-06-18T00:00:00Z",
            )
        ]

    api.list_tracked_apps = list_tracked_apps
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )
    errors = []
    bridge.errorMessage.connect(errors.append)

    bridge.refreshTracking()
    _wait_idle(app, bridge)

    assert not errors
    assert bridge.tracking["apps"][0]["tag"] == "-"
    assert bridge.tracking["apps"][0]["nextSync"] == "已到期"


def test_qml_bridge_detail_ignores_optional_extra_api_errors():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()

    def fail_snapshots(app_id, country="us", lang="en", limit=80):
        api.calls.append(("list_app_snapshots", app_id, country, lang, limit))
        raise TimeoutError("timed out")

    def fail_alerts(*, app_id=None, limit=8):
        api.calls.append(("list_alerts", limit, {"app_id": app_id}))
        raise TimeoutError("timed out")

    def fail_reviews(app_id, limit=10):
        api.calls.append(("list_cached_reviews", app_id, limit))
        raise TimeoutError("timed out")

    api.list_app_snapshots = fail_snapshots
    api.list_alerts = fail_alerts
    api.list_cached_reviews = fail_reviews
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )
    errors = []
    bridge.errorMessage.connect(errors.append)

    bridge.fetchAppDetail("com.remote", "us", "en")
    _wait_idle(app, bridge)

    assert not errors
    assert bridge.detail["loaded"] is True
    assert bridge.detail["title"] == "Remote Detail"
    assert bridge.detail["recentAlerts"] == []
    assert bridge.detail["recentReviews"] == []
    # history fetch failed -> empty trend, not a synthetic single-point series
    assert bridge.detail["ratingValues"] == []


def test_qml_bridge_history_ignores_optional_recent_keyword_api_error():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()

    def fail_recent_keywords(*, app_id="", country="", lang="", limit=8):
        api.calls.append(("list_recent_keyword_ranks", app_id, country, lang, limit))
        raise RuntimeError("internal error (STORE_INTEL_INTERNAL_ERROR)")

    api.list_recent_keyword_ranks = fail_recent_keywords
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )
    errors = []
    bridge.errorMessage.connect(errors.append)

    bridge.refreshHistory()
    _wait_idle(app, bridge)

    assert not errors
    assert bridge.history["apps"][0]["appId"] == "com.remote"
    assert bridge.history["snapshots"][0]["version"] == "1.0.0"
    assert bridge.history["keywords"] == []


def test_qml_bridge_waits_keyword_rank_refresh_job_on_cache_miss():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()
    calls = {"cached_keyword_rank": 0}

    def cached_keyword_rank(keyword, app_id, country="us", lang="en", limit=100, platform="google_play"):
        calls["cached_keyword_rank"] += 1
        api.calls.append(("cached_keyword_rank", keyword, app_id, country, lang, limit))
        if calls["cached_keyword_rank"] == 1:
            return None
        return KeywordRankResult(
            keyword=keyword,
            app_id=app_id,
            country=country,
            lang=lang,
            found=True,
            rank=2,
            checked_limit=limit,
            captured_at="2026-06-18T00:00:00Z",
            results=[AppSummary(app_id=app_id, title="Refreshed App")],
        )

    api.cached_keyword_rank = cached_keyword_rank
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )

    bridge.fetchKeywordRank("notes", "com.remote", "us", "en", "10")
    _wait_idle(app, bridge)

    assert calls["cached_keyword_rank"] == 2
    assert "前 30 条内排名 #2" in bridge.keywords["summary"]
    assert any(
        call[0] == "request_refresh" and call[1] == "keyword_rank" for call in api.calls
    )
    assert any(call[0] == "wait_refresh_job" for call in api.calls)
    refresh_calls = [
        call[2] for call in api.calls if call[0] == "request_refresh" and call[1] == "keyword_rank"
    ]
    assert refresh_calls == [
        {
            "keyword": "notes",
            "app_id": "com.remote",
            "country": "us",
            "lang": "en",
            "limit": 30,
            "platform": "google_play",
        }
    ]
    assert not any(call[0] == "rank_keyword" for call in api.calls)


def test_qml_bridge_reports_keyword_rank_refresh_job_failure():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()

    def cached_keyword_rank(keyword, app_id, country="us", lang="en", limit=100, platform="google_play"):
        api.calls.append(("cached_keyword_rank", keyword, app_id, country, lang, limit))
        return None

    def wait_refresh_job(job_id, *, timeout=60.0, interval=1.0):
        api.calls.append(("wait_refresh_job", job_id, timeout, interval))
        return SimpleNamespace(
            job_id=job_id,
            status="failed",
            error="internal error (STORE_INTEL_INTERNAL_ERROR)",
        )

    api.cached_keyword_rank = cached_keyword_rank
    api.wait_refresh_job = wait_refresh_job
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )
    errors = []
    bridge.errorMessage.connect(errors.append)

    bridge.fetchKeywordRank("notes", "com.remote", "us", "en", "10")
    _wait_idle(app, bridge)

    assert errors == ["internal error (STORE_INTEL_INTERNAL_ERROR)"]
    assert bridge.keywords["rows"] == []
    assert not any(call[0] == "rank_keyword" for call in api.calls)
    assert any(
        call[0] == "request_refresh" and call[1] == "keyword_rank" for call in api.calls
    )
    assert any(call[0] == "wait_refresh_job" for call in api.calls)


def test_qml_bridge_waits_coverage_refresh_job_on_cache_miss():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()
    cache_reads = {"count": 0}

    def cached_coverage(app_id, country="us", lang="en", deep=False, platform="google_play"):
        cache_reads["count"] += 1
        api.calls.append(("cached_coverage", app_id, country, lang, deep))
        if cache_reads["count"] == 1:
            return SimpleNamespace(
                platform="google_play",
                app_id=app_id,
                canonical_app_id=app_id,
                country=country,
                lang=lang,
                candidates=[],
                candidate_count=0,
                covered=[],
                checked_limit=50,
            )
        return SimpleNamespace(
            platform="google_play",
            app_id=app_id,
            canonical_app_id=app_id,
            country=country,
            lang=lang,
            candidates=["notes"],
            candidate_count=1,
            covered=[{"keyword": "notes", "rank": 1}],
            checked_limit=50,
        )

    api.cached_coverage = cached_coverage
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )
    errors = []
    progress_events = []
    bridge.errorMessage.connect(errors.append)
    bridge.coverageProgress.connect(
        lambda message, fraction: progress_events.append((message, fraction))
    )

    bridge.discoverCoverage("com.remote", "us", "en", False)
    _wait_idle(app, bridge)

    assert not errors
    assert bridge.coverage["rows"][0]["keyword"] == "notes"
    assert bridge.coverage["rows"][0]["rank"] == 1
    assert ("暂无缓存，已开始后台分析...", 0.05) in progress_events
    assert ("后台分析完成，正在读取缓存...", 0.9) in progress_events
    assert cache_reads["count"] == 2
    assert not any(call[0] == "analyze_coverage_stream" for call in api.calls)
    assert any(
        call[0] == "request_refresh"
        and call[1] == "coverage"
        and call[2]["deep"] is False
        for call in api.calls
    )
    assert any(call[0] == "wait_refresh_job" for call in api.calls)


def test_qml_bridge_uses_refresh_job_for_deep_remote_coverage():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()
    cache_reads = {"count": 0}

    def cached_coverage(app_id, country="us", lang="en", deep=False, platform="google_play"):
        cache_reads["count"] += 1
        api.calls.append(("cached_coverage", app_id, country, lang, deep))
        if cache_reads["count"] == 1:
            return SimpleNamespace(
                platform="google_play",
                app_id=app_id,
                canonical_app_id=app_id,
                country=country,
                lang=lang,
                candidates=[],
                candidate_count=0,
                covered=[],
                checked_limit=50,
            )
        return SimpleNamespace(
            platform="google_play",
            app_id=app_id,
            canonical_app_id=app_id,
            country=country,
            lang=lang,
            candidates=["notes"],
            candidate_count=1,
            covered=[{"keyword": "notes", "rank": 1}],
            checked_limit=50,
        )

    api.cached_coverage = cached_coverage
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )
    progress_events = []
    bridge.coverageProgress.connect(
        lambda message, fraction: progress_events.append((message, fraction))
    )

    bridge.discoverCoverage("com.remote", "us", "en", True)
    _wait_idle(app, bridge)

    assert bridge.coverage["rows"][0]["keyword"] == "notes"
    assert bridge.coverage["rows"][0]["rank"] == 1
    assert ("暂无缓存，已开始后台分析...", 0.05) in progress_events
    assert cache_reads["count"] == 2
    assert not any(call[0] == "analyze_coverage_stream" for call in api.calls)
    assert any(
        call[0] == "request_refresh"
        and call[1] == "coverage"
        and call[2]["deep"] is True
        for call in api.calls
    )
    assert any(
        call[0] == "wait_refresh_job" and call[2] == 300.0 and call[3] == 2.0
        for call in api.calls
    )


def test_qml_bridge_waits_reviews_refresh_job_on_cache_miss():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()
    cache_reads = {"count": 0}

    def list_cached_reviews(app_id, limit=10, platform="google_play"):
        cache_reads["count"] += 1
        api.calls.append(("list_cached_reviews", app_id, limit))
        if cache_reads["count"] == 1:
            return []
        return [
            ReviewItem(
                app_id=app_id,
                review_id="refreshed",
                rating=5,
                content="refreshed review",
            )
        ]

    api.list_cached_reviews = list_cached_reviews
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )

    bridge.fetchReviews("com.remote", "us", "en", "newest")
    _wait_idle(app, bridge)

    assert bridge.reviews["rows"][0]["content"] == "refreshed review"
    assert cache_reads["count"] == 2
    assert any(call[0] == "request_refresh" and call[1] == "reviews" for call in api.calls)
    assert any(call[0] == "wait_refresh_job" for call in api.calls)


def test_qml_bridge_detail_extras_refresh_reviews_on_empty_cache():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()
    cache_reads = {"count": 0}

    def list_cached_reviews(app_id, limit=10, platform="google_play"):
        cache_reads["count"] += 1
        api.calls.append(("list_cached_reviews", app_id, limit))
        if cache_reads["count"] == 1:
            return []
        return [
            ReviewItem(
                app_id=app_id,
                country="us",
                lang="en",
                review_id="detail-refreshed",
                user_name="Ana",
                rating=5,
                app_version="1.2.3",
                helpful_count=7,
                review_created_at="2026-06-21T10:11:12Z",
                captured_at="2026-06-23T13:36:41Z",
                content="detail refreshed review",
                raw={"userImage": "https://example.test/avatar.png", "score": 5},
            )
        ]

    api.list_cached_reviews = list_cached_reviews
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )

    bridge.fetchAppDetail("com.remote", "us", "en")
    _wait_idle(app, bridge)

    assert bridge.detail["recentReviews"][0]["content"] == "detail refreshed review"
    assert bridge.detail["recentReviews"][0]["country"] == "us"
    assert bridge.detail["recentReviews"][0]["lang"] == "en"
    assert bridge.detail["recentReviews"][0]["reviewId"] == "detail-refreshed"
    assert bridge.detail["recentReviews"][0]["user"] == "Ana"
    assert bridge.detail["recentReviews"][0]["version"] == "1.2.3"
    assert bridge.detail["recentReviews"][0]["helpful"] == 7
    assert bridge.detail["recentReviews"][0]["reviewCreatedAt"] == "2026-06-21 10:11:12"
    assert bridge.detail["recentReviews"][0]["capturedAt"] == "2026-06-23 13:36:41"
    assert "userImage" in bridge.detail["recentReviews"][0]["rawText"]
    assert cache_reads["count"] == 2
    assert any(call[0] == "request_refresh" and call[1] == "reviews" for call in api.calls)
    assert any(call[0] == "wait_refresh_job" for call in api.calls)


def test_qml_bridge_prefers_store_intel_api_for_tracking_settings_and_alerts():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )

    bridge.refreshDashboard()
    bridge.refreshTracking()
    bridge.refreshAlerts()
    bridge.refreshSettings()
    bridge.refreshHistory()
    _wait_idle(app, bridge)
    assert bridge.dashboard["stats"][3]["value"] == 2
    # trend series come from the user's own tracked app/keyword, not the
    # backend's global /recent endpoints
    assert bridge.dashboard["ratingAppName"] == "Remote App"
    assert bridge.dashboard["ratingValues"] == [4.5, 4.6]
    assert bridge.dashboard["keywordName"] == "notes"
    assert bridge.dashboard["keywordValues"] == [3, 1]
    assert any(call == ("list_app_snapshots", "com.remote", "us", "en", 8) for call in api.calls)
    assert not any(call[0] == "list_recent_app_snapshots" for call in api.calls)
    # the history page still queries recent keyword ranks, but always scoped to
    # a selected app — no unscoped (global) call may remain
    assert not any(
        call[0] == "list_recent_keyword_ranks" and not call[1] for call in api.calls
    )
    assert bridge.tracking["apps"][0]["appId"] == "com.remote"
    assert bridge.tracking["keywords"][0]["rank"] == "#1"
    assert bridge.tracking["charts"][0]["rank"] == "#2"
    assert bridge.alerts["unread"] == 1
    assert bridge.settings["default_country"] == "us"
    assert bridge.history["snapshots"][0]["version"] == "1.0.0"
    assert bridge.history["keywords"][0]["keyword"] == "notes"
    assert bridge.history["keywords"][0]["rank"] == 1
    tree = bridge.monitorTree()
    assert tree["apps"][0]["appId"] == "com.remote"
    assert tree["apps"][0]["keywords"][0]["rank"] == "#1"
    assert tree["apps"][0]["charts"][0]["rank"] == "#2"
    app_series = bridge.monitorSeries("app", "com.remote", "us", "en", "", 30)
    assert app_series["charts"][0]["current"] == "4.60"
    assert app_series["charts"][1]["values"] == [1200, 1300]
    keyword_series = bridge.monitorSeries("keyword", "com.remote", "us", "en", "notes", 30)
    assert keyword_series["charts"][0]["values"] == [3, 1]
    chart_series = bridge.monitorSeries(
        "chart", "com.remote", "us", "en", "top_free|APPLICATION", 30
    )
    assert chart_series["charts"][0]["values"] == [4, 2]

    bridge.addApp("com.remote", "us", "en", "daily")
    _wait_idle(app, bridge)
    bridge.bulkImportApps("com.remote\ncom.bulk\nbad id\ncom.bulk", "us", "en", "weekly")
    _wait_idle(app, bridge)
    bridge.addChartApp("com.remote", "top_free", "APPLICATION", "us", "en")
    _wait_idle(app, bridge)
    bridge.addKeywordTracking("notes", "com.remote", "us", "en")
    _wait_idle(app, bridge)
    bridge.syncAll()
    _wait_idle(app, bridge)
    bridge.markAlertRead(7)
    _wait_idle(app, bridge)
    bridge.markAllAlertsRead()
    _wait_idle(app, bridge)
    bridge.cleanupHistory()
    _wait_idle(app, bridge)
    bridge.setMonitorFrequency("app", "com.remote", "us", "en", "", "weekly")
    _wait_idle(app, bridge)
    bridge.setMonitorTag("app", "com.remote", "us", "en", "", "core")
    _wait_idle(app, bridge)
    bridge.setMonitorFrequency("keyword", "com.remote", "us", "en", "notes", "manual")
    _wait_idle(app, bridge)
    bridge.syncMonitor("app", "com.remote", "us", "en", "")
    _wait_idle(app, bridge)
    bridge.toggleMonitor("app", "com.remote", "us", "en", "")
    _wait_idle(app, bridge)
    bridge.removeMonitor("app", "com.remote", "us", "en", "")
    _wait_idle(app, bridge)
    bridge.syncMonitor("keyword", "com.remote", "us", "en", "notes")
    _wait_idle(app, bridge)
    bridge.toggleMonitor("keyword", "com.remote", "us", "en", "notes")
    _wait_idle(app, bridge)
    bridge.removeMonitor("keyword", "com.remote", "us", "en", "notes")
    _wait_idle(app, bridge)
    bridge.syncMonitor("chart", "com.remote", "us", "en", "top_free|APPLICATION")
    _wait_idle(app, bridge)
    bridge.toggleMonitor("chart", "com.remote", "us", "en", "top_free|APPLICATION")
    _wait_idle(app, bridge)
    bridge.removeMonitor("chart", "com.remote", "us", "en", "top_free|APPLICATION")
    _wait_idle(app, bridge)

    bridge.fetchAppDetail("com.remote", "us", "en")
    _wait_idle(app, bridge)
    assert bridge.detail["historyLabels"][-1] == now_iso()[5:10]
    assert bridge.detail["recentReviews"][0]["content"] == "cached review"
    bridge.saveDetailSnapshot("us", "en")
    _wait_idle(app, bridge)
    assert bridge.detail["title"] == "Remote Detail"

    call_names = [call[0] for call in api.calls]
    assert ("add_tracked_app", "com.bulk", "us", "en", "weekly", "") in api.calls
    for expected in (
        "get_settings",
        "list_tracked_apps",
        "list_tracked_keywords",
        "list_tracked_chart_apps",
        "list_alerts",
        "unread_count",
        "list_recent_keyword_ranks",
        "list_keyword_rank_history",
        "add_tracked_app",
        "add_tracked_chart_app",
        "add_tracked_keyword",
        "request_refresh",
        "mark_alerts_read",
        "cleanup_history",
        "set_tracked_app_frequency",
        "set_tracked_app_tag",
        "set_tracked_keyword_frequency",
        "remove_tracked_app",
        "set_tracked_app_enabled",
        "remove_tracked_keyword",
        "set_tracked_keyword_enabled",
        "remove_tracked_chart_app",
        "set_tracked_chart_app_enabled",
    ):
        assert expected in call_names
    for blocked in (
        "sync_all",
        "sync_tracked_keyword_now",
        "sync_tracked_chart_app_now",
        "sync_app_now",
    ):
        assert blocked not in call_names
    refresh_kinds = [call[1] for call in api.calls if call[0] == "request_refresh"]
    assert refresh_kinds.count("all") == 1
    assert refresh_kinds.count("app") >= 2
    assert refresh_kinds.count("keyword") == 1
    assert refresh_kinds.count("chart") == 1


def test_qml_bridge_reviews_refresh_payload_matches_backend_schema():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()
    cache_reads = {"count": 0}

    def list_cached_reviews(app_id, limit=10, platform="google_play"):
        cache_reads["count"] += 1
        api.calls.append(("list_cached_reviews", app_id, limit))
        if cache_reads["count"] == 1:
            return []
        return [ReviewItem(app_id=app_id, review_id="cached", rating=4, content="cached review")]

    api.list_cached_reviews = list_cached_reviews
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )

    bridge.fetchReviews("com.remote", "us", "en", "newest")
    _wait_idle(app, bridge)

    review_refreshes = [
        call for call in api.calls if call[0] == "request_refresh" and call[1] == "reviews"
    ]
    assert review_refreshes == [
        (
            "request_refresh",
            "reviews",
            {
                "app_id": "com.remote",
                "country": "us",
                "lang": "en",
                "limit": 50,
                "platform": "google_play",
            },
        )
    ]
    assert bridge.reviews["rows"][0]["content"] == "cached review"


def test_qml_bridge_save_reviews_api_mode_persists_via_backend():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )

    bridge.fetchReviews("com.remote", "us", "en", "newest")
    _wait_idle(app, bridge)
    bridge.saveReviews("com.remote", "us", "en")
    _wait_idle(app, bridge)

    save_calls = [call for call in api.calls if call[0] == "save_reviews"]
    assert len(save_calls) == 1
    assert save_calls[0][1] == "com.remote"
    assert save_calls[0][5] == "google_play"


def test_qml_bridge_save_reviews_requires_fetched_reviews_first():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )
    errors = []
    bridge.errorMessage.connect(errors.append)

    bridge.saveReviews("com.remote", "us", "en")
    _wait_idle(app, bridge)

    assert errors and "请先获取评论" in errors[0]
    assert not any(call[0] == "save_reviews" for call in api.calls)


def test_qml_bridge_save_settings_api_mode_persists_via_backend():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )

    bridge.saveSettings({"default_country": "gb", "daily_sync_time": "10:30"})
    _wait_idle(app, bridge)

    set_settings_calls = [call for call in api.calls if call[0] == "set_settings"]
    assert len(set_settings_calls) == 1
    saved = set_settings_calls[0][1]
    assert saved["default_country"] == "gb"
    assert saved["daily_sync_time"] == "10:30"
    # _after_mutation triggers refreshSettings(), which re-reads through the backend.
    assert bridge.settings["default_country"] == "gb"


def test_qml_bridge_save_settings_rejects_malformed_sync_time():
    app = QApplication.instance() or QApplication([])
    api = FakeApi()
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )
    errors = []
    bridge.errorMessage.connect(errors.append)

    bridge.saveSettings({"daily_sync_time": "not-a-time"})
    _wait_idle(app, bridge)

    assert errors and "每日同步时间格式不正确" in errors[0]
    assert not any(call[0] == "set_settings" for call in api.calls)


def test_qml_bridge_save_settings_legacy_mode_persists_locally_and_retunes_scraper():
    app = QApplication.instance() or QApplication([])

    class ConfigurableGooglePlay(FakeGooglePlay):
        def __init__(self):
            self.configured_delay = None

        def configure(self, request_delay_seconds=None):
            self.configured_delay = request_delay_seconds

    class FakeScheduler:
        def __init__(self):
            self.reloaded = False

        def reload_jobs(self):
            self.reloaded = True

    settings_service = FakeSettings()
    google_play = ConfigurableGooglePlay()
    scheduler = FakeScheduler()
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": settings_service,
            "google_play_service": google_play,
            "scheduler": scheduler,
        },
        logger=logging.getLogger("qml-legacy-test"),
    )

    bridge.saveSettings({"request_delay_seconds": "3.5", "default_country": "de"})
    _wait_idle(app, bridge)

    assert settings_service.values["request_delay_seconds"] == "3.5"
    assert settings_service.values["default_country"] == "de"
    assert google_play.configured_delay == 3.5
    assert scheduler.reloaded is True


def test_qml_bridge_api_log_lifecycle():
    api = FakeApi()
    bridge = QmlBridge(
        database=None,
        services={
            "settings_service": FakeSettings(),
            "store_intel_api_client": api,
            "google_play_service": FakeGooglePlay(),
            "tracking_service": FakeTracking(),
            "alert_service": FakeAlerts(),
            "review_service": FakeReviews(),
        },
        logger=logging.getLogger("qml-api-test"),
    )
    changes = []
    bridge.apiLogsChanged.connect(lambda: changes.append(len(bridge.apiLogs)))

    bridge._append_api_log_entry(
        {"method": "GET", "path": "/api/store-intel/apps/search", "status": 200, "ok": True}
    )
    assert len(bridge.apiLogs) == 1
    assert bridge.apiLogs[0]["method"] == "GET"
    assert changes == [1]

    bridge._append_api_log_entry("not a dict — must be ignored")
    assert len(bridge.apiLogs) == 1
    assert changes == [1]  # no extra apiLogsChanged emitted for the ignored entry

    bridge.clearApiLogs()
    assert bridge.apiLogs == []
    assert changes == [1, 0]
