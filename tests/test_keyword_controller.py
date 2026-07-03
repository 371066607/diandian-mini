from types import SimpleNamespace

import pytest

from app.ui.controllers.keyword_controller import KeywordController


class FakeApi:
    def __init__(self, cached=None):
        self.cached = cached

    def cached_keyword_rank(self, keyword, app_id, country="us", lang="en", limit=30, platform="google_play"):
        return self.cached


class FakeBridge:
    def __init__(self, services=None):
        self.services = services or {}
        self.refresh_calls = []

    def _request_api_refresh(self, api, kind, **kwargs):
        self.refresh_calls.append((kind, kwargs))
        api.cached = SimpleNamespace(app_id="com.demo", found=True, rank=3)


class FakeKeywordService:
    def __init__(self):
        self.rank_calls = []
        self.save_calls = []

    def rank(self, keyword, app_id, country, lang, limit):
        self.rank_calls.append((keyword, app_id, country, lang, limit))
        return SimpleNamespace(app_id=app_id, found=True, rank=1)

    def save_result(self, result):
        self.save_calls.append(result)
        return True


def test_fetch_rank_api_returns_cache_hit_without_refresh():
    api = FakeApi(cached=SimpleNamespace(app_id="com.demo", found=True, rank=2))
    bridge = FakeBridge()
    controller = KeywordController(bridge)

    payload = controller.fetch_rank_api(api, "notes", "com.demo", "us", "en", "google_play")

    assert payload["result"].rank == 2
    assert bridge.refresh_calls == []


def test_fetch_rank_api_triggers_refresh_on_cache_miss():
    api = FakeApi(cached=None)
    bridge = FakeBridge()
    controller = KeywordController(bridge)

    payload = controller.fetch_rank_api(api, "notes", "com.demo", "us", "en", "google_play")

    assert bridge.refresh_calls and bridge.refresh_calls[0][0] == "keyword_rank"
    assert payload["result"].rank == 3


def test_fetch_rank_api_raises_when_still_missing_after_refresh():
    api = FakeApi(cached=None)

    class NoOpRefreshBridge(FakeBridge):
        def _request_api_refresh(self, api, kind, **kwargs):
            self.refresh_calls.append((kind, kwargs))

    bridge = NoOpRefreshBridge()
    controller = KeywordController(bridge)

    with pytest.raises(RuntimeError, match="没有返回可用的关键词排名数据"):
        controller.fetch_rank_api(api, "notes", "com.demo", "us", "en", "google_play")


def test_fetch_rank_legacy_uses_google_play_service_by_default():
    keyword_service = FakeKeywordService()
    bridge = FakeBridge(services={"keyword_service": keyword_service})
    controller = KeywordController(bridge)

    result = controller.fetch_rank_legacy("notes", "com.demo", "us", "en", "google_play")

    assert result.rank == 1
    assert keyword_service.rank_calls == [("notes", "com.demo", "us", "en", 30)]


def test_fetch_rank_legacy_uses_app_store_service_for_app_store_platform():
    app_store_keyword_service = FakeKeywordService()
    bridge = FakeBridge(services={"keyword_service_app_store": app_store_keyword_service})
    controller = KeywordController(bridge)

    controller.fetch_rank_legacy("notes", "123456", "us", "en", "app_store")

    assert app_store_keyword_service.rank_calls == [("notes", "123456", "us", "en", 30)]


def test_save_legacy_delegates_to_keyword_service():
    keyword_service = FakeKeywordService()
    bridge = FakeBridge(services={"keyword_service": keyword_service})
    controller = KeywordController(bridge)

    result = SimpleNamespace(app_id="com.demo")
    controller.save_legacy(result)

    assert keyword_service.save_calls == [result]
