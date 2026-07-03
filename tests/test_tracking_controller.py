from types import SimpleNamespace

from app.ui.controllers.tracking_controller import (
    TrackingController,
    bulk_app_ids,
    is_valid_app_id,
    split_monitor_chart_key,
)


# --- pure helpers -----------------------------------------------------------


def test_split_monitor_chart_key_defaults():
    assert split_monitor_chart_key("") == ("top_free", "APPLICATION")
    assert split_monitor_chart_key("top_grossing|GAME") == ("top_grossing", "GAME")
    assert split_monitor_chart_key("top_free|") == ("top_free", "APPLICATION")


def test_is_valid_app_id_google_play_requires_dotted_package():
    assert is_valid_app_id("com.example.app") is True
    assert is_valid_app_id("com") is False
    assert is_valid_app_id("") is False
    assert is_valid_app_id("has space.app") is False


def test_is_valid_app_id_app_store_requires_digits():
    assert is_valid_app_id("587366035", "app_store") is True
    assert is_valid_app_id("com.example.app", "app_store") is False


def test_bulk_app_ids_dedupes_and_strips():
    raw = "com.a\ncom.b\n  \ncom.a\ncom.c  "
    assert bulk_app_ids(raw) == ["com.a", "com.b", "com.c"]


# --- FakeApi / FakeBridge ----------------------------------------------------


class FakeApi:
    def __init__(self, tracked_apps=None, tracked_keywords=None, tracked_chart_apps=None):
        self.tracked_apps = tracked_apps or []
        self.tracked_keywords = tracked_keywords or []
        self.tracked_chart_apps = tracked_chart_apps or []
        self.calls = []

    def list_tracked_apps(self, platform=None):
        return self.tracked_apps

    def list_tracked_keywords(self):
        return self.tracked_keywords

    def list_tracked_chart_apps(self):
        return self.tracked_chart_apps

    def add_tracked_app(self, app_id, country, lang, frequency, platform="google_play"):
        self.calls.append(("add_tracked_app", app_id, platform))
        return SimpleNamespace(app_id=app_id)

    def add_tracked_chart_app(self, app_id, collection, category, country, lang, platform="google_play"):
        self.calls.append(("add_tracked_chart_app", app_id, collection, category, platform))
        return SimpleNamespace(app_id=app_id)

    def set_tracked_app_enabled(self, app_id, enabled, country, lang, platform):
        self.calls.append(("set_tracked_app_enabled", app_id, enabled, platform))
        return SimpleNamespace(enabled=enabled)

    def set_tracked_keyword_enabled(self, keyword, app_id, enabled, country, lang, platform):
        self.calls.append(("set_tracked_keyword_enabled", keyword, enabled, platform))
        return SimpleNamespace(enabled=enabled)

    def set_tracked_chart_app_enabled(self, app_id, collection, enabled, category, country, lang, platform):
        self.calls.append(("set_tracked_chart_app_enabled", app_id, collection, enabled, platform))
        return SimpleNamespace(enabled=enabled)

    def request_refresh(self, kind, **kwargs):
        self.calls.append(("request_refresh", kind, kwargs))
        return SimpleNamespace(job_id="job-1")

    def set_tracked_app_frequency(self, app_id, frequency, country, lang, platform):
        self.calls.append(("set_tracked_app_frequency", app_id, frequency, platform))
        return SimpleNamespace(frequency=frequency)

    def set_tracked_keyword_frequency(self, keyword, app_id, frequency, country, lang, platform):
        self.calls.append(("set_tracked_keyword_frequency", keyword, frequency, platform))
        return SimpleNamespace(frequency=frequency)

    def set_tracked_app_tag(self, app_id, tag, country, lang, platform):
        self.calls.append(("set_tracked_app_tag", app_id, tag, platform))
        return SimpleNamespace(tag=tag)

    def remove_tracked_app(self, app_id, country, lang, platform):
        self.calls.append(("remove_tracked_app", app_id, platform))

    def remove_tracked_keyword(self, keyword, app_id, country, lang, platform):
        self.calls.append(("remove_tracked_keyword", keyword, platform))

    def remove_tracked_chart_app(self, app_id, collection, category, country, lang, platform):
        self.calls.append(("remove_tracked_chart_app", app_id, collection, platform))


class FakeTrackingService:
    def __init__(self):
        self.calls = []

    def add_app(self, app_id, country, lang, frequency):
        self.calls.append(("add_app", app_id))
        return SimpleNamespace(app_id=app_id)

    def add_chart_app(self, app_id, collection, category, country, lang):
        self.calls.append(("add_chart_app", app_id, collection, category))
        return SimpleNamespace(app_id=app_id)

    def add_apps_bulk(self, app_ids, country, lang, frequency):
        self.calls.append(("add_apps_bulk", app_ids))
        return {"added": len(app_ids), "existing": 0, "failed": [], "total": len(app_ids)}

    def sync_app_now(self, app_id, country, lang):
        self.calls.append(("sync_app_now", app_id))

    def sync_keyword_now(self, keyword, app_id, country, lang):
        self.calls.append(("sync_keyword_now", keyword))
        return SimpleNamespace(rank=3)

    def sync_chart_now(self, app_id, collection, category, country, lang):
        self.calls.append(("sync_chart_now", app_id))
        return SimpleNamespace(rank=5)

    def toggle_app(self, app_id, country, lang):
        self.calls.append(("toggle_app", app_id))
        return True

    def toggle_keyword(self, keyword, app_id, country, lang):
        self.calls.append(("toggle_keyword", keyword))
        return True

    def toggle_chart_app(self, app_id, collection, category, country, lang):
        self.calls.append(("toggle_chart_app", app_id))
        return True

    def set_app_frequency(self, app_id, country, lang, frequency):
        self.calls.append(("set_app_frequency", app_id, frequency))
        return frequency

    def set_keyword_frequency(self, keyword, app_id, country, lang, frequency):
        self.calls.append(("set_keyword_frequency", keyword, frequency))
        return frequency

    def set_app_tag(self, app_id, country, lang, tag):
        self.calls.append(("set_app_tag", app_id, tag))
        return tag

    def remove_app(self, app_id, country, lang):
        self.calls.append(("remove_app", app_id))

    def remove_keyword(self, keyword, app_id, country, lang):
        self.calls.append(("remove_keyword", keyword))

    def remove_chart_app(self, app_id, collection, category, country, lang):
        self.calls.append(("remove_chart_app", app_id))


class FakeBridge:
    def __init__(self, services=None):
        self.services = services or {}


def _controller(services=None):
    return TrackingController(FakeBridge(services=services))


# --- find_item / platform_of / toggle_via_api --------------------------------


def test_find_item_app_matches_identity():
    api = FakeApi(tracked_apps=[SimpleNamespace(app_id="com.a", country="us", lang="en", platform="google_play")])
    controller = _controller()

    found = controller.find_item(api, "app", "com.a", "us", "en", "")
    assert found is not None
    assert controller.find_item(api, "app", "com.b", "us", "en", "") is None


def test_platform_of_defaults_to_google_play_when_not_found():
    api = FakeApi()
    controller = _controller()
    assert controller.platform_of(api, "app", "com.a", "us", "en", "") == "google_play"


def test_platform_of_resolves_from_tracked_row():
    api = FakeApi(tracked_apps=[SimpleNamespace(app_id="com.a", country="us", lang="en", platform="app_store")])
    controller = _controller()
    assert controller.platform_of(api, "app", "com.a", "us", "en", "") == "app_store"


def test_toggle_via_api_flips_current_state():
    api = FakeApi(tracked_apps=[SimpleNamespace(app_id="com.a", country="us", lang="en", platform="google_play", enabled=True)])
    controller = _controller()

    result = controller.toggle_via_api(api, "app", "com.a", "us", "en", "")

    assert api.calls[0] == ("set_tracked_app_enabled", "com.a", False, "google_play")
    assert result is False


# --- add_app / add_chart_app / bulk_import -----------------------------------


def test_add_app_api_mode():
    api = FakeApi()
    controller = _controller()
    controller.add_app(api, "com.demo", "us", "en", "daily", "google_play")
    assert api.calls == [("add_tracked_app", "com.demo", "google_play")]


def test_add_app_legacy_mode():
    service = FakeTrackingService()
    controller = _controller(services={"tracking_service": service})
    controller.add_app(None, "com.demo", "us", "en", "daily", "google_play")
    assert service.calls == [("add_app", "com.demo")]


def test_add_chart_app_legacy_mode_defaults_category():
    service = FakeTrackingService()
    controller = _controller(services={"tracking_service": service})
    controller.add_chart_app(None, "com.demo", "", "", "us", "en", "google_play")
    assert service.calls == [("add_chart_app", "com.demo", "top_free", "APPLICATION")]


def test_bulk_import_api_mode_flags_invalid_and_existing():
    api = FakeApi(tracked_apps=[SimpleNamespace(app_id="com.existing", country="us", lang="en")])
    controller = _controller()

    result = controller.bulk_import(api, ["com.existing", "com.new", "bad id"], "us", "en", "daily", "google_play")

    assert result["added"] == 1
    assert result["existing"] == 1
    assert len(result["failed"]) == 1
    assert result["failed"][0]["app_id"] == "bad id"


def test_bulk_import_legacy_mode_delegates():
    service = FakeTrackingService()
    controller = _controller(services={"tracking_service": service})
    result = controller.bulk_import(None, ["com.a", "com.b"], "us", "en", "daily", "google_play")
    assert result["added"] == 2
    assert service.calls == [("add_apps_bulk", ["com.a", "com.b"])]


# --- sync_one / toggle_one / set_frequency / set_tag / remove_one -----------


def test_sync_one_api_mode_app():
    api = FakeApi()
    controller = _controller()
    message = controller.sync_one(api, ("app", "com.demo", "us", "en", ""))
    assert "已提交应用后台刷新" in message
    assert api.calls[0][0] == "request_refresh"


def test_sync_one_legacy_mode_keyword_reports_rank():
    service = FakeTrackingService()
    controller = _controller(services={"tracking_service": service})
    message = controller.sync_one(None, ("keyword", "com.demo", "us", "en", "notes"))
    assert "排名 3" in message


def test_toggle_one_legacy_mode_chart():
    service = FakeTrackingService()
    controller = _controller(services={"tracking_service": service})
    kind, enabled = controller.toggle_one(None, ("chart", "com.demo", "us", "en", "top_free|GAME"))
    assert kind == "chart"
    assert enabled is True
    assert service.calls == [("toggle_chart_app", "com.demo")]


def test_set_frequency_api_mode_app():
    api = FakeApi(tracked_apps=[SimpleNamespace(app_id="com.demo", country="us", lang="en", platform="google_play")])
    controller = _controller()
    result = controller.set_frequency(api, ("app", "com.demo", "us", "en", ""), "weekly")
    assert result == "weekly"
    assert ("set_tracked_app_frequency", "com.demo", "weekly", "google_play") in api.calls


def test_set_tag_legacy_mode():
    service = FakeTrackingService()
    controller = _controller(services={"tracking_service": service})
    result = controller.set_tag(None, ("app", "com.demo", "us", "en", ""), "core")
    assert result == "core"
    assert service.calls == [("set_app_tag", "com.demo", "core")]


def test_remove_one_api_mode_keyword():
    api = FakeApi(tracked_keywords=[SimpleNamespace(keyword="notes", app_id="com.demo", country="us", lang="en", platform="google_play")])
    controller = _controller()
    message = controller.remove_one(api, ("keyword", "com.demo", "us", "en", "notes"))
    assert message == "已删除关键词监控。"
    assert ("remove_tracked_keyword", "notes", "google_play") in api.calls


def test_remove_one_legacy_mode_chart():
    service = FakeTrackingService()
    controller = _controller(services={"tracking_service": service})
    message = controller.remove_one(None, ("chart", "com.demo", "us", "en", "top_free|GAME"))
    assert message == "已删除榜单监控。"
    assert service.calls == [("remove_chart_app", "com.demo")]
