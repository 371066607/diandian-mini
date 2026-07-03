from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from app.schemas.review_schema import ReviewItem
from app.services.store_intel_api_client import StoreIntelApiClient, StoreIntelApiError


class StoreIntelHandler(BaseHTTPRequestHandler):
    def log_message(self, _format, *_args):  # pragma: no cover - keeps test output clean
        return

    def do_GET(self):
        self.server.requests.append(("GET", self.path, None))
        self.server.user_agents.append(self.headers.get("user-agent"))
        self.server.auth_headers.append(self.headers.get("authorization"))
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/api/store-intel/apps/search":
            return self._json({"items": [{"app_id": "com.demo", "title": query["query"][0]}]})
        if parsed.path == "/api/store-intel/apps/search/cache":
            if query.get("null_items") == ["1"]:
                return self._json({"items": None, "total": 0})
            return self._json(
                {"items": [{"app_id": "com.cached", "title": query["query"][0]}]}
            )
        if parsed.path == "/api/store-intel/apps/com.demo":
            return self._json({"app_id": "com.demo", "title": "Demo", "rating": 4.7})
        if parsed.path == "/api/store-intel/apps/com.demo/cache":
            return self._json(
                {
                    "detail": {
                        "app_id": "com.demo",
                        "title": "Cached Demo",
                        "rating": 4.8,
                        "permissions": {"Location": ["cached location"]},
                    }
                }
            )
        if parsed.path == "/api/store-intel/apps/com.miss/cache":
            return self._json(
                {
                    "detail": {
                        "platform": "google_play",
                        "app_id": "com.miss",
                    },
                    "cached": False,
                }
            )
        if parsed.path == "/api/store-intel/apps/com.demo/similar":
            return self._json(
                {"items": [{"app_id": "com.related", "title": "Related", "rating": 4.2}]}
            )
        if parsed.path == "/api/store-intel/apps/com.demo/permissions":
            return self._json({"groups": {"Location": ["approximate location"]}})
        if parsed.path == "/api/store-intel/apps/com.demo/reviews":
            return self._json(
                {
                    "items": [{"app_id": "com.demo", "review_id": "r1", "rating": 5}],
                    "next_token": "page-2",
                }
            )
        if parsed.path == "/api/store-intel/apps/com.demo/reviews/cache":
            return self._json(
                {"items": [{"app_id": "com.demo", "review_id": "cached", "rating": 4}]}
            )
        if parsed.path == "/api/store-intel/charts":
            return self._json(
                {
                    "items": [
                        {
                            "app_id": "com.demo",
                            "title": "Demo",
                            "rank": 1,
                            "chart_type": query["chart_type"][0],
                            "country": "us",
                            "lang": "en",
                        }
                    ]
                }
            )
        if parsed.path == "/api/store-intel/charts/cache":
            return self._json(
                {
                    "items": [
                        {
                            "app_id": "com.cached",
                            "title": "Cached",
                            "rank": 2,
                            "chart_type": query["chart_type"][0],
                            "country": "us",
                            "lang": "en",
                        }
                    ]
                }
            )
        if parsed.path == "/api/store-intel/keyword-coverage/cache":
            return self._json(
                {
                    "platform": "google_play",
                    "app_id": query["app_id"][0],
                    "canonical_app_id": query["app_id"][0],
                    "country": "us",
                    "lang": "en",
                    "candidates": ["notes"],
                    "candidate_count": 1,
                    "covered": [{"keyword": "notes", "rank": 1}],
                    "checked_limit": 50,
                }
            )
        if parsed.path == "/api/store-intel/settings":
            return self._json(
                {"default_country": "us", "default_lang": "en", "default_limit": "50"}
            )
        if parsed.path == "/api/store-intel/app-snapshots/history":
            return self._json(
                {
                    "items": [
                        {
                            "app_id": query["app_id"][0],
                            "country": "us",
                            "lang": "en",
                            "captured_at": "2026-06-18T00:00:00Z",
                            "title": "Demo",
                            "rating": 4.7,
                            "ratings_count": 100,
                            "reviews_count": 10,
                            "installs": "1,000+",
                            "real_installs": 1200,
                            "version": "1.2.3",
                        }
                    ]
                }
            )
        if parsed.path == "/api/store-intel/app-snapshots/recent":
            return self._json(
                {
                    "items": [
                        {
                            "app_id": "com.demo",
                            "captured_at": "2026-06-18T00:00:00Z",
                            "title": "Demo",
                            "rating": 4.7,
                        }
                    ]
                }
            )
        if parsed.path == "/api/store-intel/app-snapshots/count":
            return self._json({"total": 1})
        if parsed.path == "/api/store-intel/tracking/apps":
            if getattr(self.server, "require_tracking_auth", False):
                if self.headers.get("authorization") not in (
                    "Bearer guest-access",
                    "Bearer refreshed-access",
                ):
                    return self._json(
                        {"error_code": "unauthorized"},
                        code=401,
                        message="unauthorized",
                    )
            return self._json(
                {
                    "items": [
                        {
                            "app_id": "com.demo",
                            "title": "Demo",
                            "country": "us",
                            "lang": "en",
                            "frequency": "daily",
                            "enabled": True,
                            "consecutive_failures": 0,
                            "last_synced_at": "",
                        }
                    ]
                }
            )
        if parsed.path == "/api/store-intel/tracking/keywords":
            return self._json(
                {
                    "items": [
                        {
                            "platform": "google_play",
                            "keyword": "notes",
                            "app_id": "com.demo",
                            "country": "us",
                            "lang": "en",
                            "frequency": "daily",
                            "enabled": True,
                            "consecutive_failures": 0,
                            "last_synced_at": "",
                        }
                    ]
                }
            )
        if parsed.path == "/api/store-intel/tracking/chart-apps":
            return self._json(
                {
                    "items": [
                        {
                            "app_id": "com.demo",
                            "collection": "top_free",
                            "category": "APPLICATION",
                            "country": "us",
                            "lang": "en",
                            "frequency": "daily",
                            "enabled": True,
                            "consecutive_failures": 0,
                            "last_synced_at": "",
                        }
                    ]
                }
            )
        if parsed.path == "/api/store-intel/alerts":
            return self._json(
                {
                    "items": [
                        {
                            "id": 7,
                            "type": "rating_drop",
                            "severity": "high",
                            "app_id": "com.demo",
                            "title": "Demo",
                            "message": "drop",
                            "is_read": False,
                            "created_at": "2026-06-18T00:00:00Z",
                        }
                    ]
                }
            )
        if parsed.path == "/api/store-intel/keyword-rank/history":
            if query.get("keyword") == ["empty-check"]:
                return self._json(
                    {
                        "items": [
                            {
                                "keyword": "empty-check",
                                "app_id": "com.demo",
                                "country": "us",
                                "lang": "en",
                                "found": False,
                                "checked_limit": 0,
                                "coverage_complete": False,
                                "captured_at": "2026-06-18T00:00:00Z",
                            }
                        ]
                    }
                )
            return self._json(
                {
                    "items": [
                        {
                            "keyword": "notes",
                            "app_id": "com.demo",
                            "country": "us",
                            "lang": "en",
                            "found": True,
                            "rank": 3,
                            "checked_limit": 10,
                            "captured_at": "2026-06-18T00:00:00Z",
                        }
                    ]
                }
            )
        if parsed.path == "/api/store-intel/keyword-rank/recent":
            return self._json(
                {
                    "items": [
                        {
                            "keyword": "notes",
                            "app_id": query.get("app_id", ["com.demo"])[0] or "com.demo",
                            "country": "us",
                            "lang": "en",
                            "found": True,
                            "rank": 2,
                            "checked_limit": 10,
                            "captured_at": "2026-06-19T00:00:00Z",
                        }
                    ]
                }
            )
        if parsed.path == "/api/store-intel/chart-rank/history":
            return self._json(
                {
                    "items": [
                        {
                            "app_id": "com.demo",
                            "collection": "top_free",
                            "category": "APPLICATION",
                            "country": "us",
                            "lang": "en",
                            "found": False,
                            "checked_limit": 10,
                            "captured_at": "2026-06-18T00:00:00Z",
                        }
                    ]
                }
            )
        if parsed.path == "/api/store-intel/refresh-jobs/job-1":
            return self._json(
                {
                    "job_id": "job-1",
                    "kind": "app",
                    "status": "queued",
                    "message": "queued",
                    "requested_at": "2026-06-18T00:00:00Z",
                    "updated_at": "2026-06-18T00:00:00Z",
                }
            )
        return self._json({"error_code": "missing"}, code=404, message="missing")

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("content-length") or 0)).decode("utf-8")
        body = json.loads(raw or "{}")
        self.server.requests.append(("POST", self.path, body))
        self.server.user_agents.append(self.headers.get("user-agent"))
        self.server.auth_headers.append(self.headers.get("authorization"))
        parsed = urlparse(self.path)
        if parsed.path == "/api/auth/guest":
            self.server.guest_login_bodies.append(body)
            return self._json(
                {
                    "access_token": "guest-access",
                    "refresh_token": "guest-refresh",
                }
            )
        if parsed.path == "/api/auth/refresh":
            self.server.refresh_bodies.append(body)
            if getattr(self.server, "refresh_should_fail", False):
                return self._json(
                    {"error_code": "invalid_refresh_token"},
                    code=401,
                    message="refresh token expired",
                )
            return self._json(
                {
                    "access_token": "refreshed-access",
                    "refresh_token": "refreshed-refresh",
                }
            )
        if parsed.path == "/api/store-intel/apps/com.demo/reviews":
            return self._json({"saved": len(body["items"])})
        if parsed.path == "/api/store-intel/charts/snapshot":
            return self._json({"saved": len(body["items"]), "captured_at": "2026-06-18T00:00:00Z"})
        if parsed.path == "/api/store-intel/keyword-rank":
            return self._json(
                {
                    "platform": "google_play",
                    "keyword": body["keyword"],
                    "app_id": body["app_id"],
                    "country": body["country"],
                    "lang": body["lang"],
                    "found": True,
                    "rank": 1,
                    "checked_limit": body["limit"],
                    "captured_at": "2026-06-18T00:00:00Z",
                    "results": [{"app_id": body["app_id"], "title": "Demo"}],
                }
            )
        if parsed.path == "/api/store-intel/keyword-coverage":
            return self._json(
                {
                    "platform": "google_play",
                    "app_id": body["app_id"],
                    "canonical_app_id": body["app_id"],
                    "country": body["country"],
                    "lang": body["lang"],
                    "candidates": ["notes"],
                    "candidate_count": 1,
                    "covered": [{"keyword": "notes", "rank": 1}],
                    "checked_limit": body["limit"],
                }
            )
        if parsed.path == "/api/store-intel/keyword-coverage/stream":
            payload = "\n".join(
                [
                    json.dumps(
                        {
                            "type": "progress",
                            "message": "覆盖检测 1/1：notes",
                            "fraction": 1.0,
                        }
                    ),
                    json.dumps(
                        {
                            "type": "result",
                            "data": {
                                "platform": "google_play",
                                "app_id": body["app_id"],
                                "canonical_app_id": body["app_id"],
                                "country": body["country"],
                                "lang": body["lang"],
                                "candidates": ["notes"],
                                "candidate_count": 1,
                                "covered": [{"keyword": "notes", "rank": 1}],
                                "checked_limit": body["limit"],
                            },
                        }
                    ),
                    "",
                ]
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "application/x-ndjson; charset=utf-8")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if parsed.path == "/api/store-intel/settings":
            body.setdefault("default_lang", "en")
            return self._json(body)
        if parsed.path == "/api/store-intel/tracking/apps":
            return self._json({**body, "enabled": True, "consecutive_failures": 0})
        if parsed.path == "/api/store-intel/tracking/keywords":
            return self._json({**body, "enabled": True, "consecutive_failures": 0})
        if parsed.path == "/api/store-intel/tracking/chart-apps":
            return self._json({**body, "enabled": True, "consecutive_failures": 0})
        if parsed.path == "/api/store-intel/tracking/apps/remove":
            return self._json({"updated": 1})
        if parsed.path == "/api/store-intel/tracking/apps/enabled":
            return self._json({"updated": 1, "enabled": body["enabled"]})
        if parsed.path == "/api/store-intel/tracking/apps/frequency":
            return self._json({"updated": 1, "frequency": body["frequency"]})
        if parsed.path == "/api/store-intel/tracking/apps/tag":
            return self._json({"updated": 1, "tag": body["tag"]})
        if parsed.path == "/api/store-intel/tracking/keywords/remove":
            return self._json({"updated": 1})
        if parsed.path == "/api/store-intel/tracking/keywords/enabled":
            return self._json({"updated": 1, "enabled": body["enabled"]})
        if parsed.path == "/api/store-intel/tracking/keywords/frequency":
            return self._json({"updated": 1, "frequency": body["frequency"]})
        if parsed.path == "/api/store-intel/tracking/keywords/sync":
            return self._json(
                {
                    "rank": {
                        "platform": body["platform"],
                        "keyword": body["keyword"],
                        "app_id": body["app_id"],
                        "country": body["country"],
                        "lang": body["lang"],
                        "found": True,
                        "rank": 2,
                        "checked_limit": body["limit"],
                        "captured_at": "2026-06-18T00:00:00Z",
                    }
                }
            )
        if parsed.path == "/api/store-intel/tracking/chart-apps/remove":
            return self._json({"updated": 1})
        if parsed.path == "/api/store-intel/tracking/chart-apps/enabled":
            return self._json({"updated": 1, "enabled": body["enabled"]})
        if parsed.path == "/api/store-intel/tracking/chart-apps/sync":
            return self._json(
                {
                    "rank": {
                        "app_id": body["app_id"],
                        "collection": body["collection"],
                        "category": body["category"],
                        "country": body["country"],
                        "lang": body["lang"],
                        "found": True,
                        "rank": 5,
                        "checked_limit": body["limit"],
                        "captured_at": "2026-06-18T00:00:00Z",
                    }
                }
            )
        if parsed.path == "/api/store-intel/tracking/apps/sync":
            return self._json({"detail": {"app_id": body["app_id"], "title": "Synced"}})
        if parsed.path == "/api/store-intel/tracking/sync-all":
            return self._json({"apps_synced": 1, "keywords_synced": 2, "charts_synced": 3})
        if parsed.path == "/api/store-intel/refresh-jobs":
            return self._json({"job_id": "job-1", "status": "queued", "kind": body["kind"]})
        if parsed.path == "/api/store-intel/alerts/read":
            return self._json({"updated": 4})
        if parsed.path == "/api/store-intel/history/cleanup":
            return self._json(
                {"snapshots": 1, "keywords": 2, "charts": 3, "alerts": 4, "reviews": 5}
            )
        return self._json({"error_code": "missing"}, code=404, message="missing")

    def _json(self, data, *, code: int = 200, message: str = "success"):
        payload = json.dumps({"code": code, "message": message, "data": data}).encode("utf-8")
        self.send_response(200 if code == 200 else code)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture
def api_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), StoreIntelHandler)
    server.requests = []
    server.user_agents = []
    server.auth_headers = []
    server.guest_login_bodies = []
    server.refresh_bodies = []
    server.refresh_should_fail = False
    server.require_tracking_auth = False
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_store_intel_api_client_maps_core_page_contracts(api_server):
    client = StoreIntelApiClient(f"http://127.0.0.1:{api_server.server_port}")

    search = client.search("notes", country="us", lang="en", limit=5)
    assert search[0].app_id == "com.demo"
    assert search[0].title == "notes"
    cached_search = client.search_cached("notes", country="us", lang="en", limit=5)
    assert cached_search[0].app_id == "com.cached"

    detail = client.app_detail("com.demo", country="us", lang="en")
    assert detail.app_id == "com.demo"
    assert detail.rating == 4.7
    cached_detail = client.cached_app_detail("com.demo", country="us", lang="en")
    assert cached_detail.title == "Cached Demo"
    assert cached_detail.permissions["Location"][0] == "cached location"
    assert client.similar_apps("com.demo", country="us", lang="en")[0].app_id == "com.related"
    assert client.permissions("com.demo", country="us", lang="en")["Location"][0] == (
        "approximate location"
    )

    api_server.requests.clear()
    assert client.list_recent_keyword_ranks(limit=1)[0].rank == 2
    assert "app_id=" not in api_server.requests[0][1]
    assert "country=" not in api_server.requests[0][1]
    assert "lang=" not in api_server.requests[0][1]

    empty_rank = client.cached_keyword_rank("empty-check", "com.demo", limit=30)
    assert empty_rank is not None
    assert empty_rank.checked_limit == 0
    assert empty_rank.requested_limit == 0
    assert empty_rank.returned_count == 0
    assert empty_rank.coverage_complete is False
    assert empty_rank.results == []

    reviews, token = client.reviews("com.demo", country="us", lang="en", sort="newest")
    assert reviews[0].review_id == "r1"
    assert token == "page-2"
    assert client.list_cached_reviews("com.demo")[0].review_id == "cached"

    saved = client.save_reviews("com.demo", "us", "en", [ReviewItem(app_id="com.demo")])
    assert saved == 1

    charts = client.fetch_chart("top_free", None, "us", "en", 10)
    assert charts[0].rank == 1
    assert charts[0].chart_type == "top_free"
    cached_charts = client.fetch_chart_cached("top_free", None, "us", "en", 10)
    assert cached_charts[0].app_id == "com.cached"
    assert cached_charts[0].rank == 2

    chart_saved = client.save_chart_snapshot("top_free", None, "us", "en", charts)
    assert chart_saved == 1
    snapshots = client.list_app_snapshots("com.demo", "us", "en", 80)
    assert snapshots[0].version == "1.2.3"
    assert client.list_recent_app_snapshots(8)[0].rating == 4.7
    assert client.count_app_snapshots() == 1

    rank = client.rank_keyword("notes", "com.demo", country="us", lang="en", limit=10)
    assert rank.found is True
    assert rank.rank == 1
    assert rank.results[0].app_id == "com.demo"
    coverage = client.analyze_coverage("com.demo", country="us", lang="en", limit=10)
    assert coverage.candidate_count == 1
    assert coverage.covered[0]["keyword"] == "notes"
    assert coverage.covered[0]["rank"] == 1
    cached_coverage = client.cached_coverage("com.demo", country="us", lang="en")
    assert cached_coverage.covered[0]["keyword"] == "notes"
    assert cached_coverage.covered[0]["rank"] == 1
    progress = []
    streamed = client.analyze_coverage_stream(
        "com.demo",
        country="us",
        lang="en",
        limit=10,
        progress=lambda message, fraction: progress.append((message, fraction)),
    )
    assert streamed.candidate_count == 1
    assert streamed.covered[0]["keyword"] == "notes"
    assert progress == [("覆盖检测 1/1：notes", 1.0)]

    settings = client.get_settings()
    assert settings["default_country"] == "us"
    saved_settings = client.set_settings({"theme": "teal"})
    assert saved_settings["theme"] == "teal"

    assert client.list_tracked_apps()[0].app_id == "com.demo"
    assert client.list_tracked_keywords()[0].keyword == "notes"
    assert client.list_tracked_chart_apps()[0].collection == "top_free"
    assert client.add_tracked_app("com.demo").enabled is True
    assert client.add_tracked_keyword("notes", "com.demo").enabled is True
    assert client.add_tracked_chart_app("com.demo", "top_free").enabled is True
    assert client.remove_tracked_app("com.demo") == 1
    assert client.set_tracked_app_enabled("com.demo", False).enabled is False
    assert client.set_tracked_app_frequency("com.demo", "weekly").frequency == "weekly"
    assert client.set_tracked_app_tag("com.demo", "core").tag == "core"
    assert client.remove_tracked_keyword("notes", "com.demo") == 1
    assert client.set_tracked_keyword_enabled("notes", "com.demo", False).enabled is False
    assert client.set_tracked_keyword_frequency("notes", "com.demo", "manual").frequency == "manual"
    synced_keyword = client.sync_tracked_keyword_now("notes", "com.demo", limit=10)
    assert synced_keyword.rank == 2
    assert client.remove_tracked_chart_app("com.demo", "top_free") == 1
    assert client.set_tracked_chart_app_enabled("com.demo", "top_free", False).enabled is False
    synced_chart = client.sync_tracked_chart_app_now("com.demo", "top_free", limit=10)
    assert synced_chart.rank == 5
    assert client.sync_app_now("com.demo").title == "Synced"
    assert client.sync_all(True) == {"apps": 1, "keywords": 2, "charts": 3}
    refresh_job = client.request_refresh("app", app_id="com.demo", country="us", lang="en")
    assert refresh_job.status == "queued"
    assert refresh_job.kind == "app"
    assert client.get_refresh_job(refresh_job.job_id).status == "queued"
    assert client.cleanup_history() == {
        "snapshots": 1,
        "keywords": 2,
        "charts": 3,
        "alerts": 4,
        "reviews": 5,
    }

    post_paths = [path for method, path, _body in api_server.requests if method == "POST"]
    assert "/api/store-intel/apps/com.demo/reviews" in post_paths
    assert "/api/store-intel/charts/snapshot" in post_paths
    assert "/api/store-intel/keyword-rank" in post_paths
    assert "/api/store-intel/keyword-coverage" in post_paths
    assert "/api/store-intel/refresh-jobs" in post_paths
    assert "/api/store-intel/tracking/apps/remove" in post_paths
    assert "/api/store-intel/tracking/apps/enabled" in post_paths
    assert "/api/store-intel/tracking/apps/frequency" in post_paths
    assert "/api/store-intel/tracking/apps/tag" in post_paths
    assert "/api/store-intel/tracking/keywords/remove" in post_paths
    assert "/api/store-intel/tracking/keywords/enabled" in post_paths
    assert "/api/store-intel/tracking/keywords/frequency" in post_paths
    assert "/api/store-intel/tracking/keywords/sync" in post_paths
    assert "/api/store-intel/tracking/chart-apps/remove" in post_paths
    assert "/api/store-intel/tracking/chart-apps/enabled" in post_paths
    assert "/api/store-intel/tracking/chart-apps/sync" in post_paths
    assert "/api/store-intel/history/cleanup" in post_paths

    alerts = client.list_alerts(limit=5)
    assert alerts[0].id == 7
    assert client.unread_count() == 1
    assert client.mark_alerts_read([7]) == 4
    assert client.latest_keyword_rank_label("notes", "com.demo") == "#3"
    assert client.list_keyword_rank_history("notes", "com.demo")[0].rank == 3
    assert client.list_recent_keyword_ranks(app_id="com.demo")[0].rank == 2
    assert client.list_chart_rank_history("com.demo", "top_free")[0].collection == "top_free"
    assert client.latest_chart_rank_label("com.demo", "top_free") == "未命中"


def test_store_intel_api_client_waits_for_refresh_job():
    client = StoreIntelApiClient("http://store.test")
    statuses = [
        SimpleNamespace(job_id="job-1", status="queued"),
        SimpleNamespace(job_id="job-1", status="completed"),
    ]
    calls = []

    def get_refresh_job(job_id):
        calls.append(job_id)
        return statuses.pop(0)

    client.get_refresh_job = get_refresh_job

    job = client.wait_refresh_job("job-1", timeout=1.0, interval=0.1)

    assert job.status == "completed"
    assert calls == ["job-1", "job-1"]


def test_store_intel_api_client_treats_dead_refresh_job_as_terminal():
    client = StoreIntelApiClient("http://store.test")
    statuses = [
        SimpleNamespace(job_id="job-1", status="running"),
        SimpleNamespace(job_id="job-1", status="dead"),
    ]

    def get_refresh_job(job_id):
        return statuses.pop(0)

    client.get_refresh_job = get_refresh_job

    job = client.wait_refresh_job("job-1", timeout=1.0, interval=0.1)

    assert job.status == "dead"


def test_store_intel_api_client_requires_base_url():
    client = StoreIntelApiClient("")
    with pytest.raises(StoreIntelApiError, match="未配置"):
        client.search("notes")


def test_store_intel_api_client_sends_desktop_user_agent(api_server):
    client = StoreIntelApiClient(f"http://127.0.0.1:{api_server.server_port}")

    client.get_settings()
    client.request_refresh("search", query="notes", country="us", lang="en", limit=5)

    assert api_server.user_agents
    assert set(api_server.user_agents) == {"CatchRadar/desktop"}


def test_store_intel_api_client_guest_retries_once_on_401(api_server):
    api_server.require_tracking_auth = True
    client = StoreIntelApiClient(
        f"http://127.0.0.1:{api_server.server_port}",
        device_id="desktop-test-device",
    )

    apps = client.list_tracked_apps()

    assert apps[0].app_id == "com.demo"
    assert api_server.guest_login_bodies == [
        {
            "app_id": "catchradar",
            "device_id": "desktop-test-device",
            "platform": "desktop",
        }
    ]
    paths = [path for _method, path, _body in api_server.requests]
    assert paths.count("/api/store-intel/tracking/apps") == 2
    assert "/api/auth/guest" in paths
    tracking_headers = [
        api_server.auth_headers[index]
        for index, path in enumerate(paths)
        if path == "/api/store-intel/tracking/apps"
    ]
    assert tracking_headers == [None, "Bearer guest-access"]


def test_store_intel_api_client_refreshes_token_before_guest_login_on_401(api_server):
    api_server.require_tracking_auth = True
    client = StoreIntelApiClient(
        f"http://127.0.0.1:{api_server.server_port}",
        device_id="desktop-test-device",
    )
    client._access_token = "stale-access"
    client._refresh_token = "existing-refresh"

    apps = client.list_tracked_apps()

    assert apps[0].app_id == "com.demo"
    assert api_server.refresh_bodies == [
        {"app_id": "catchradar", "refresh_token": "existing-refresh"}
    ]
    assert api_server.guest_login_bodies == []
    assert client._access_token == "refreshed-access"
    assert client._refresh_token == "refreshed-refresh"


def test_store_intel_api_client_falls_back_to_guest_login_when_refresh_fails(api_server):
    api_server.require_tracking_auth = True
    api_server.refresh_should_fail = True
    client = StoreIntelApiClient(
        f"http://127.0.0.1:{api_server.server_port}",
        device_id="desktop-test-device",
    )
    client._refresh_token = "stale-refresh"

    apps = client.list_tracked_apps()

    assert apps[0].app_id == "com.demo"
    assert api_server.refresh_bodies == [
        {"app_id": "catchradar", "refresh_token": "stale-refresh"}
    ]
    assert api_server.guest_login_bodies == [
        {
            "app_id": "catchradar",
            "device_id": "desktop-test-device",
            "platform": "desktop",
        }
    ]


def test_store_intel_api_client_coalesces_concurrent_reauthentication(api_server):
    api_server.require_tracking_auth = True
    client = StoreIntelApiClient(
        f"http://127.0.0.1:{api_server.server_port}",
        device_id="desktop-test-device",
    )

    results: list[list] = []
    errors: list[Exception] = []
    lock = threading.Lock()

    def call():
        try:
            apps = client.list_tracked_apps()
        except StoreIntelApiError as exc:  # pragma: no cover - failure path
            with lock:
                errors.append(exc)
            return
        with lock:
            results.append(apps)

    workers = [threading.Thread(target=call) for _ in range(5)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=5)

    assert not errors
    assert len(results) == 5
    assert api_server.guest_login_bodies == [
        {
            "app_id": "catchradar",
            "device_id": "desktop-test-device",
            "platform": "desktop",
        }
    ]


def test_store_intel_api_client_sends_chart_refresh_collection(api_server):
    client = StoreIntelApiClient(f"http://127.0.0.1:{api_server.server_port}")

    client.request_refresh(
        "chart",
        chart_type="top_free",
        category="ENTERTAINMENT",
        country="us",
        lang="en",
        limit=100,
    )

    _method, path, body = api_server.requests[-1]
    assert path == "/api/store-intel/refresh-jobs"
    assert body["collection"] == "top_free"
    assert "chart_type" not in body


def test_store_intel_api_client_emits_request_logs(api_server):
    logs = []
    client = StoreIntelApiClient(
        f"http://127.0.0.1:{api_server.server_port}",
        log_sink=logs.append,
    )

    client.get_settings()
    client.set_settings({"default_country": "us", "proxy": "http://secret"})
    with pytest.raises(StoreIntelApiError, match="missing"):
        client.app_detail("com.unknown")

    assert [item["method"] for item in logs] == ["GET", "POST", "GET"]
    assert logs[0]["path"] == "/api/store-intel/settings"
    assert logs[0]["status"] == 200
    assert logs[0]["code"] == 200
    assert logs[0]["ok"] is True
    assert logs[1]["body"] == '{"default_country":"us","proxy":"***"}'
    assert logs[2]["status"] == 404
    assert logs[2]["ok"] is False
    assert "missing" in logs[2]["error"]


def test_store_intel_api_client_keeps_full_log_payloads():
    logs = []
    client = StoreIntelApiClient("http://store.test", log_sink=logs.append)
    response = {
        "items": [{"keyword": f"keyword-{index}", "rank": index} for index in range(40)],
        "proxy": "http://secret",
    }

    client._emit_log(
        method="GET",
        path="/api/store-intel/keyword-coverage/cache",
        query={"app_id": "com.demo"},
        body=None,
        response=response,
        raw_response="",
        status=200,
        code=200,
        ok=True,
        error="",
        started=0,
    )

    log = logs[0]
    assert log["response"].endswith("...")
    assert "keyword-39" not in log["response"]
    assert "keyword-39" in log["response_full"]
    assert "http://secret" not in log["response_full"]
    assert '"proxy":"***"' in log["response_full"]


def test_store_intel_api_client_treats_null_items_as_empty_list(api_server):
    client = StoreIntelApiClient(f"http://127.0.0.1:{api_server.server_port}")

    items = client.search_cached("notes", country="us", lang="en", limit=5)
    assert items[0].app_id == "com.cached"

    data = client._request(
        "GET",
        "/api/store-intel/apps/search/cache",
        query={"query": "notes", "country": "us", "lang": "en", "limit": 5, "null_items": "1"},
    )
    assert client._items(data) == []


def test_store_intel_api_client_treats_cached_false_detail_as_miss(api_server):
    client = StoreIntelApiClient(f"http://127.0.0.1:{api_server.server_port}")

    with pytest.raises(StoreIntelApiError, match="暂无应用详情缓存"):
        client.cached_app_detail("com.miss", country="us", lang="en")
