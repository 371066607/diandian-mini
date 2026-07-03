from types import SimpleNamespace

from app.ui.controllers import detail_controller as dc


def _gp_item(**overrides):
    defaults = dict(
        app_id="com.demo",
        title="Demo",
        summary="",
        store_url="",
        icon_url="",
        description="",
        platform="google_play",
        developer="",
        developer_id="",
        developer_email="",
        developer_website="",
        privacy_policy="",
        developer_address="123 Main St",
        developer_phone="555-0100",
        publisher_country="US",
        app_bundle="",
        genre_id="",
        currency="USD",
        min_daily_installs=None,
        min_monthly_installs=None,
        video="",
        header_image="",
        rating=None,
        ratings_count=None,
        reviews_count=None,
        installs="",
        min_installs=None,
        real_installs=None,
        real_daily_installs=None,
        daily_installs=None,
        real_monthly_installs=None,
        monthly_installs=None,
        contains_ads=None,
        ad_supported=None,
        min_android_api=None,
        max_android_api=None,
        original_price=None,
        app_age_days=None,
        released="",
        updated="",
        version="",
        android_version="",
        content_rating="",
        price="",
        free=False,
        sale=None,
        has_iap=None,
        iap_price_range="",
        available=None,
        screenshots=[],
        histogram=[],
        categories=[],
        category="",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# --- has_app_detail_data / has_complete_app_detail_data -----------------


def test_has_app_detail_data_false_without_app_id():
    assert dc.has_app_detail_data(None) is False
    assert dc.has_app_detail_data(SimpleNamespace(app_id="")) is False


def test_has_app_detail_data_true_when_any_core_field_present():
    assert dc.has_app_detail_data(SimpleNamespace(app_id="com.demo", title="Demo")) is True
    assert (
        dc.has_app_detail_data(
            SimpleNamespace(app_id="com.demo", title="", summary="", store_url="", icon_url="", description="")
        )
        is False
    )


def test_has_complete_app_detail_data_requires_extended_fields():
    minimal = _gp_item()
    assert dc.has_complete_app_detail_data(minimal) is False
    assert dc.has_complete_app_detail_data(_gp_item(rating=4.5)) is True


# --- dev_links / dev_plain / more_info -----------------------------------


def test_dev_links_google_play_includes_email_and_privacy():
    item = _gp_item(developer_email="dev@example.com", developer_website="https://example.com")
    links = dc.dev_links(item, is_ios=False)

    labels = [link["label"] for link in links]
    assert labels == ["邮箱", "官网", "隐私政策"]
    assert links[0]["url"] == "mailto:dev@example.com"


def test_dev_links_app_store_omits_email_and_privacy():
    item = _gp_item(developer_website="https://example.com")
    links = dc.dev_links(item, is_ios=True)

    assert [link["label"] for link in links] == ["官网"]


def test_dev_plain_differs_by_platform():
    item = _gp_item()
    android_rows = dc.dev_plain(item, is_ios=False)
    ios_rows = dc.dev_plain(item, is_ios=True)

    assert {row["label"] for row in android_rows} == {"地址", "电话", "发布国"}
    assert {row["label"] for row in ios_rows} == {"卖家", "发布国"}


def test_more_info_app_store_shape():
    item = _gp_item(app_bundle="com.demo.bundle", genre_id="6014", categories=["Games"])
    rows = {row["label"]: row["value"] for row in dc.more_info(item, is_ios=True)}

    assert rows["Bundle ID"] == "com.demo.bundle"
    assert rows["全部类目"] == "Games"


def test_more_info_google_play_shape():
    item = _gp_item(app_bundle="com.demo", min_daily_installs=100)
    rows = {row["label"]: row["value"] for row in dc.more_info(item, is_ios=False)}

    assert rows["应用包"] == "com.demo"
    assert rows["最低日均安装"] == "100"


# --- metrics / metrics_app_store ------------------------------------------


def test_metrics_dispatches_to_app_store_variant():
    item = _gp_item(platform="app_store", rating=4.2, has_iap=True, available=True)
    rows = {row["label"]: row["value"] for row in dc.metrics(item)}

    assert rows["评分"] == "4.20"
    assert rows["内购"] == "是"


def test_metrics_google_play_shape():
    item = _gp_item(
        rating=4.7,
        ratings_count=1000,
        min_android_api=21,
        max_android_api=33,
        original_price=9.99,
        currency="USD",
    )
    rows = {row["label"]: row["value"] for row in dc.metrics(item)}

    assert rows["评分"] == "4.70"
    assert rows["评分数"] == "1,000"
    assert rows["Android API"] == "21 ~ 33"
    assert rows["原价"] == "USD 9.99"


# --- DetailController.fetch / list_cached_reviews --------------------------


class FakeApi:
    def __init__(self, cached=None, raise_first=False):
        self.cached = cached
        self.raise_first = raise_first
        self.calls = 0

    def cached_app_detail(self, app_id, country="us", lang="en", platform="google_play"):
        self.calls += 1
        if self.raise_first and self.calls == 1:
            raise RuntimeError("boom")
        return self.cached

    def list_cached_reviews(self, app_id, limit=10, platform="google_play"):
        return self.cached or []


class FakeStore:
    def __init__(self, detail):
        self.detail = detail

    def app_detail(self, app_id, country="us", lang="en"):
        return self.detail


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


def test_fetch_legacy_mode_uses_active_store():
    detail = _gp_item(title="Local Detail")
    bridge = FakeBridge(api=None, store=FakeStore(detail))
    controller = dc.DetailController(bridge)

    payload = controller.fetch("com.demo", {"country": "us", "lang": "en"}, "google_play", 1)

    assert payload == {"detail": detail, "queued": False, "request_id": 1}


def test_fetch_api_mode_returns_cache_hit_when_complete():
    detail = _gp_item(rating=4.5)
    api = FakeApi(cached=detail)
    bridge = FakeBridge(api=api)
    controller = dc.DetailController(bridge)

    payload = controller.fetch("com.demo", {"country": "us", "lang": "en"}, "google_play", 1)

    assert payload["detail"] is detail
    assert payload["partial"] is False
    assert bridge.refresh_calls == []


def test_fetch_api_mode_refreshes_on_incomplete_cache():
    detail = _gp_item(title="Demo")  # has core fields but not "complete" fields
    api = FakeApi(cached=detail)
    bridge = FakeBridge(api=api)
    controller = dc.DetailController(bridge)

    payload = controller.fetch("com.demo", {"country": "us", "lang": "en"}, "google_play", 1)

    assert bridge.refresh_calls and bridge.refresh_calls[0][0] == "app"
    assert payload["partial"] is True


def test_list_cached_reviews_refreshes_on_empty_cache():
    api = FakeApi(cached=[])
    bridge = FakeBridge(api=api)
    controller = dc.DetailController(bridge)

    controller.list_cached_reviews(api, "com.demo", "us", "en", 10)

    assert bridge.refresh_calls and bridge.refresh_calls[0][0] == "reviews"
