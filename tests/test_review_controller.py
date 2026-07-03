from types import SimpleNamespace

from app.ui.controllers.review_controller import ReviewController


class FakeApi:
    def __init__(self, cached=None):
        self.cached = cached or []
        self.refresh_calls = []
        self.save_calls = []

    def list_cached_reviews(self, app_id, limit=50, platform="google_play"):
        return self.cached

    def save_reviews(self, app_id, country, lang, items, platform="google_play"):
        self.save_calls.append((app_id, country, lang, list(items), platform))
        return len(items)


class FakeBridge:
    def __init__(self, api=None, services=None):
        self._api = api
        self.services = services or {}
        self.refresh_calls = []

    def _store_intel_api(self, platform=None):
        return self._api

    def _request_api_refresh(self, api, kind, **kwargs):
        self.refresh_calls.append((kind, kwargs))


class FakeReviewService:
    def __init__(self):
        self.fetch_calls = []
        self.save_calls = []

    def fetch(self, app_id, country, lang, sort, token):
        self.fetch_calls.append((app_id, country, lang, sort, token))
        return [SimpleNamespace(review_id="r1")], "next-token"

    def save(self, app_id, country, lang, items):
        self.save_calls.append((app_id, country, lang, list(items)))
        return len(items)


class FakeAppStoreService:
    def __init__(self):
        self.calls = []

    def reviews(self, app_id, country, lang, sort, continuation_token):
        self.calls.append((app_id, country, lang, sort, continuation_token))
        return [SimpleNamespace(review_id="ios1")], None


def test_fetch_page_api_mode_returns_cache_hit_without_refresh():
    api = FakeApi(cached=[SimpleNamespace(review_id="r1")])
    bridge = FakeBridge(api=api)
    controller = ReviewController(bridge)

    items, token = controller.fetch_page({"app_id": "com.demo", "platform": "google_play"}, None)

    assert [item.review_id for item in items] == ["r1"]
    assert token is None
    assert bridge.refresh_calls == []


def test_fetch_page_api_mode_triggers_refresh_on_cache_miss():
    api = FakeApi(cached=[])
    bridge = FakeBridge(api=api)
    controller = ReviewController(bridge)

    controller.fetch_page(
        {"app_id": "com.demo", "country": "us", "lang": "en", "platform": "google_play"}, None
    )

    assert bridge.refresh_calls
    assert bridge.refresh_calls[0][0] == "reviews"
    assert bridge.refresh_calls[0][1]["app_id"] == "com.demo"


def test_fetch_page_api_mode_pagination_returns_empty_without_refetch():
    api = FakeApi(cached=[SimpleNamespace(review_id="r1")])
    bridge = FakeBridge(api=api)
    controller = ReviewController(bridge)

    items, token = controller.fetch_page(
        {"app_id": "com.demo", "platform": "google_play"}, "some-token"
    )

    assert items == []
    assert token is None


def test_fetch_page_legacy_google_play_delegates_to_review_service():
    review_service = FakeReviewService()
    bridge = FakeBridge(api=None, services={"review_service": review_service})
    controller = ReviewController(bridge)

    items, token = controller.fetch_page(
        {"app_id": "com.demo", "country": "us", "lang": "en", "sort": "newest"}, None
    )

    assert token == "next-token"
    assert review_service.fetch_calls == [("com.demo", "us", "en", "newest", None)]


def test_fetch_page_legacy_app_store_delegates_to_app_store_service():
    app_store_service = FakeAppStoreService()
    bridge = FakeBridge(api=None, services={"app_store_service": app_store_service})
    controller = ReviewController(bridge)

    controller.fetch_page(
        {
            "app_id": "123456",
            "country": "us",
            "lang": "en",
            "sort": "newest",
            "platform": "app_store",
        },
        None,
    )

    assert app_store_service.calls == [("123456", "us", "en", "newest", None)]


def test_save_api_mode_delegates_to_api():
    api = FakeApi()
    bridge = FakeBridge(api=api)
    controller = ReviewController(bridge)

    saved = controller.save("com.demo", "us", "en", [SimpleNamespace(review_id="r1")], "google_play")

    assert saved == 1
    assert api.save_calls[0][0] == "com.demo"
    assert api.save_calls[0][4] == "google_play"


def test_save_legacy_mode_delegates_to_review_service():
    review_service = FakeReviewService()
    bridge = FakeBridge(api=None, services={"review_service": review_service})
    controller = ReviewController(bridge)

    saved = controller.save("com.demo", "us", "en", [SimpleNamespace(review_id="r1")], "google_play")

    assert saved == 1
    assert review_service.save_calls[0][0] == "com.demo"
