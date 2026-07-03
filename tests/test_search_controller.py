from types import SimpleNamespace

from app.ui.controllers.search_controller import (
    SearchController,
    has_search_display_data,
    search_items_signature,
)


def _item(**overrides):
    defaults = dict(app_id="com.demo", title="Demo", developer="Acme", rating=4.5, ratings_count=10, installs="1K+")
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_has_search_display_data_requires_all_core_fields():
    assert has_search_display_data(_item()) is True
    assert has_search_display_data(_item(developer="")) is False
    assert has_search_display_data(None) is False
    assert has_search_display_data(SimpleNamespace(app_id="")) is False


def test_search_items_signature_stable_and_order_sensitive():
    a = [_item(app_id="1"), _item(app_id="2")]
    b = [_item(app_id="1"), _item(app_id="2")]
    c = [_item(app_id="2"), _item(app_id="1")]

    assert search_items_signature(a) == search_items_signature(b)
    assert search_items_signature(a) != search_items_signature(c)
    assert search_items_signature([]) == search_items_signature(None)


class FakeApi:
    def __init__(self, cached=None):
        self.cached = cached or []
        self.refresh_calls = []

    def search_cached(self, keyword, country="us", lang="en", limit=50, platform="google_play"):
        return self.cached


class FakeBridge:
    def __init__(self, api=None, store=None):
        self._api = api
        self._store = store
        self.refresh_calls = []

    def _store_intel_api(self, platform=None):
        return self._api

    def _active_store(self):
        return self._store

    def _request_api_refresh(self, api, kind, **kwargs):
        self.refresh_calls.append((kind, kwargs))
        api.cached = [_item(app_id="com.refreshed")]


class FakeStore:
    def __init__(self, items):
        self.items = items

    def search(self, keyword, country="us", lang="en", limit=50):
        return self.items


def test_search_api_mode_returns_cache_hit_without_refresh():
    api = FakeApi(cached=[_item()])
    bridge = FakeBridge(api=api)
    controller = SearchController(bridge)

    result = controller.search("notes", "us", "en", 50, "google_play")

    assert result["items"] == api.cached
    assert result["refresh_in_background"] is False
    assert bridge.refresh_calls == []


def test_search_api_mode_triggers_refresh_on_cache_miss():
    api = FakeApi(cached=[])
    bridge = FakeBridge(api=api)
    controller = SearchController(bridge)

    result = controller.search("notes", "us", "en", 50, "google_play")

    assert bridge.refresh_calls and bridge.refresh_calls[0][0] == "search"
    assert result["items"]


def test_search_api_mode_flags_background_refresh_for_incomplete_cache():
    api = FakeApi(cached=[_item(developer="")])  # incomplete but non-empty
    bridge = FakeBridge(api=api)
    controller = SearchController(bridge)

    result = controller.search("notes", "us", "en", 50, "google_play")

    assert result["refresh_in_background"] is True
    assert bridge.refresh_calls == []  # cache wasn't empty, so no eager refresh


def test_search_legacy_mode_delegates_to_active_store():
    store = FakeStore([_item(app_id="com.local")])
    bridge = FakeBridge(api=None, store=store)
    controller = SearchController(bridge)

    result = controller.search("notes", "us", "en", 50, "google_play")

    assert result == {"items": store.items, "queued": False}


def test_refresh_cache_triggers_refresh_and_returns_fresh_items():
    api = FakeApi(cached=[_item()])
    bridge = FakeBridge(api=api)
    controller = SearchController(bridge)

    items = controller.refresh_cache(api, "notes", "us", "en", 50, "google_play")

    assert bridge.refresh_calls and bridge.refresh_calls[0][0] == "search"
    assert items[0].app_id == "com.refreshed"
