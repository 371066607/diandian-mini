from types import SimpleNamespace

import pytest

from app.ui.controllers.coverage_controller import CoverageController, has_coverage_cache_data


def test_has_coverage_cache_data_false_for_none():
    assert has_coverage_cache_data(None) is False


def test_has_coverage_cache_data_true_when_any_signal_present():
    assert has_coverage_cache_data(SimpleNamespace(captured_at="2026-06-18T00:00:00Z")) is True
    assert has_coverage_cache_data(SimpleNamespace(candidate_count=5)) is True
    assert has_coverage_cache_data(SimpleNamespace(candidates=["notes"])) is True
    assert has_coverage_cache_data(SimpleNamespace(covered=[{"keyword": "notes"}])) is True


def test_has_coverage_cache_data_false_when_all_empty():
    empty = SimpleNamespace(captured_at="", candidate_count=0, candidates=[], covered=[])
    assert has_coverage_cache_data(empty) is False


class FakeApi:
    def __init__(self, cached=None, job_status="completed"):
        self.cached = cached
        self.job_status = job_status
        self.calls = []

    def cached_coverage(self, app_id, country="us", lang="en", deep=False, platform="google_play"):
        self.calls.append("cached_coverage")
        return self.cached

    def request_refresh(self, kind, **kwargs):
        self.calls.append(("request_refresh", kind))
        return SimpleNamespace(job_id="job-1")

    def wait_refresh_job(self, job_id, timeout=60.0, interval=1.0):
        self.calls.append("wait_refresh_job")
        return SimpleNamespace(status=self.job_status, error="boom" if self.job_status == "failed" else "")

    def list_keyword_rank_history(
        self, keyword, app_id, country="us", lang="en", limit=0, platform="google_play"
    ):
        self.calls.append(("list_keyword_rank_history", keyword, app_id, country, lang, limit, platform))
        return [
            SimpleNamespace(rank=4, captured_at="2026-07-12T09:00:00Z"),
            SimpleNamespace(rank=None, captured_at="2026-07-12T12:00:00Z"),
            SimpleNamespace(rank=2, captured_at="2026-07-13T09:00:00Z"),
        ]


class FakeBridge:
    def __init__(self, services=None):
        self.services = services or {}
        self.progress_events = []
        self.coverageProgress = SimpleNamespace(emit=lambda msg, frac: self.progress_events.append((msg, frac)))


class FakeCoverageService:
    def __init__(self):
        self.calls = []

    def analyze_coverage(self, platform, app_id, **kwargs):
        self.calls.append((platform, app_id, kwargs))
        return SimpleNamespace(candidate_count=3, covered=[{"keyword": "notes", "rank": 1}])


class FakeSettingsService:
    def __init__(self, value="6"):
        self.value = value

    def get(self, key, default=""):
        return self.value


def test_concurrency_clamps_between_1_and_16():
    bridge = FakeBridge(services={"settings_service": FakeSettingsService("100")})
    controller = CoverageController(bridge)
    assert controller.concurrency() == 16

    bridge2 = FakeBridge(services={"settings_service": FakeSettingsService("0")})
    assert CoverageController(bridge2).concurrency() == 1

    bridge3 = FakeBridge(services={"settings_service": FakeSettingsService("8")})
    assert CoverageController(bridge3).concurrency() == 8


def test_load_trend_uses_real_ranked_points_and_scan_identity():
    api = FakeApi()
    controller = CoverageController(FakeBridge())

    result = controller.load_trend(
        api,
        keyword="notes",
        app_id="com.demo",
        country="us",
        lang="en",
        platform="google_play",
    )

    assert result["values"] == [4, 2]
    assert result["labels"] == ["07-12 09:00", "07-13 09:00"]
    assert result["current"] == "当前 #2"
    assert api.calls[-1] == (
        "list_keyword_rank_history",
        "notes",
        "com.demo",
        "us",
        "en",
        90,
        "google_play",
    )


def test_analyze_api_mode_returns_cache_hit_without_refresh():
    cached = SimpleNamespace(candidate_count=5, covered=[{"keyword": "notes", "rank": 2}], candidates=[], captured_at="2026-06-18T00:00:00Z")
    api = FakeApi(cached=cached)
    bridge = FakeBridge()
    controller = CoverageController(bridge)

    result = controller.analyze(api, "com.demo", "us", "en", False, "google_play", None)

    assert result is cached
    assert "request_refresh" not in [c[0] if isinstance(c, tuple) else c for c in api.calls]


def test_analyze_api_mode_triggers_refresh_job_on_cache_miss():
    api = FakeApi(cached=None)

    call_count = {"n": 0}
    original_cached_coverage = api.cached_coverage

    def cached_coverage_side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] >= 2:
            api.cached = SimpleNamespace(candidate_count=1, covered=[], candidates=[], captured_at="now")
        return original_cached_coverage(*args, **kwargs)

    api.cached_coverage = cached_coverage_side_effect
    bridge = FakeBridge()
    controller = CoverageController(bridge)

    result = controller.analyze(api, "com.demo", "us", "en", False, "google_play", None)

    assert result is not None
    assert ("request_refresh", "coverage") in api.calls


def test_analyze_api_mode_raises_when_still_empty_after_refresh(monkeypatch):
    # refresh_api_cache polls for up to 30s (real time.monotonic/time.sleep) waiting
    # for the cache to populate — fast-forward the clock so this test doesn't
    # actually wait 30 seconds for a cache that (by design) never populates.
    monkeypatch.setattr("app.ui.controllers.coverage_controller.time.sleep", lambda _: None)
    clock = {"now": 0.0}
    monkeypatch.setattr(
        "app.ui.controllers.coverage_controller.time.monotonic", lambda: clock.__setitem__("now", clock["now"] + 40.0) or clock["now"]
    )
    api = FakeApi(cached=None)
    bridge = FakeBridge()
    controller = CoverageController(bridge)

    with pytest.raises(RuntimeError, match="没有返回可用的覆盖词数据"):
        controller.analyze(api, "com.demo", "us", "en", False, "google_play", None)


def test_analyze_legacy_mode_delegates_to_keyword_coverage_service():
    service = FakeCoverageService()
    bridge = FakeBridge(services={"keyword_coverage_service": service})
    controller = CoverageController(bridge)

    result = controller.analyze(None, "com.demo", "us", "en", True, "google_play", ("cand", "canon"), proxy_pool=None, max_workers=1)

    assert result.candidate_count == 3
    call = service.calls[0]
    assert call[0] == "google_play"
    assert call[1] == "com.demo"
    assert call[2]["deep"] is True
    assert call[2]["candidates"] == "cand"
    assert call[2]["canonical_app_id"] == "canon"


def test_refresh_api_cache_raises_on_failed_job():
    api = FakeApi(cached=None, job_status="failed")
    bridge = FakeBridge()
    controller = CoverageController(bridge)

    with pytest.raises(RuntimeError, match="boom"):
        controller.refresh_api_cache(api, app_id="com.demo", country="us", lang="en", deep=False)
