import pytest

from app.ui.controllers.chart_controller import ChartController


class FakeApi:
    def __init__(self, cached=None, cache_error=False):
        self.cached = cached or []
        self.cache_error = cache_error
        self.refresh_calls = []

    def fetch_chart_cached(self, chart_type, category, country, lang, limit, platform="google_play"):
        if self.cache_error:
            raise RuntimeError("boom")
        return self.cached


class FakeBridge:
    def __init__(self, api=None, services=None):
        self._api = api
        self.services = services or {}
        self.refresh_calls = []

    def _store_intel_api(self, platform=None):
        return self._api

    def _request_api_refresh(self, api, kind, **kwargs):
        self.refresh_calls.append((kind, kwargs))
        api.cached = [{"app_id": "com.demo", "rank": 1}]
        api.cache_error = False


class FakeChartService:
    def __init__(self):
        self.fetch_calls = []
        self.save_calls = []

    def fetch(self, chart_type, category, country, lang, limit, platform="google_play"):
        self.fetch_calls.append((chart_type, category, country, lang, limit, platform))
        return [{"app_id": "com.local", "rank": 2}]

    def save(self, chart_type, category, country, lang, items):
        self.save_calls.append((chart_type, category, country, lang, list(items)))
        return len(items)


def _ctx(**overrides):
    base = {
        "chart_type": "top_free",
        "category": None,
        "country": "us",
        "lang": "en",
        "platform": "google_play",
    }
    base.update(overrides)
    return base


def test_fetch_api_mode_returns_cache_hit_without_refresh():
    api = FakeApi(cached=[{"app_id": "com.demo", "rank": 1}])
    bridge = FakeBridge(api=api)
    controller = ChartController(bridge)

    result = controller.fetch(_ctx(), 50)

    assert result == {"items": api.cached, "queued": False}
    assert bridge.refresh_calls == []


def test_fetch_api_mode_triggers_refresh_on_cache_miss():
    api = FakeApi(cached=[])
    bridge = FakeBridge(api=api)
    controller = ChartController(bridge)

    result = controller.fetch(_ctx(), 50)

    assert bridge.refresh_calls and bridge.refresh_calls[0][0] == "chart"
    assert result["items"]


def test_fetch_api_mode_raises_when_still_empty_after_refresh():
    api = FakeApi(cached=[])

    class NoOpRefreshBridge(FakeBridge):
        def _request_api_refresh(self, api, kind, **kwargs):
            self.refresh_calls.append((kind, kwargs))
            # cache stays empty even after the refresh attempt

    bridge = NoOpRefreshBridge(api=api)
    controller = ChartController(bridge)

    with pytest.raises(RuntimeError, match="没有返回可用的榜单数据"):
        controller.fetch(_ctx(), 50)


def test_fetch_api_mode_tolerates_cache_read_error():
    api = FakeApi(cache_error=True)
    bridge = FakeBridge(api=api)
    controller = ChartController(bridge)

    result = controller.fetch(_ctx(), 50)

    assert bridge.refresh_calls  # cache read failure is treated like a miss
    assert result["items"]


def test_fetch_legacy_mode_delegates_to_chart_service():
    chart_service = FakeChartService()
    bridge = FakeBridge(api=None, services={"chart_service": chart_service})
    controller = ChartController(bridge)

    result = controller.fetch(_ctx(), 50)

    assert result == {"items": [{"app_id": "com.local", "rank": 2}], "queued": False}
    assert chart_service.fetch_calls == [("top_free", None, "us", "en", 50, "google_play")]


def test_save_legacy_delegates_to_chart_service():
    chart_service = FakeChartService()
    bridge = FakeBridge(api=None, services={"chart_service": chart_service})
    controller = ChartController(bridge)

    saved = controller.save_legacy(_ctx(), [{"app_id": "com.demo"}])

    assert saved == 1
    assert chart_service.save_calls[0][0] == "top_free"
