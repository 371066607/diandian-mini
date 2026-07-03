import pytest

from app.ui.controllers.settings_controller import SettingsController, SettingsError


class FakeSettingsService:
    def __init__(self):
        self.saved = None

    def set_many(self, values):
        self.saved = dict(values)


class FakeGooglePlay:
    def __init__(self):
        self.configured_delay = None

    def configure(self, request_delay_seconds=None):
        self.configured_delay = request_delay_seconds


class FakeScheduler:
    def __init__(self):
        self.reloaded = False

    def reload_jobs(self):
        self.reloaded = True


def test_build_updates_merges_payload_over_current_and_fills_defaults():
    controller = SettingsController(services={})

    updates = controller.build_updates(
        current={"default_country": "gb", "daily_sync_time": "09:00"},
        payload={"default_country": "us"},
    )

    assert updates["default_country"] == "us"
    assert updates["daily_sync_time"] == "09:00"
    assert updates["default_lang"] == "en"
    assert updates["default_limit"] == "50"
    assert updates["request_delay_seconds"] == "1"


def test_build_updates_rejects_malformed_sync_time():
    controller = SettingsController(services={})

    with pytest.raises(SettingsError, match="每日同步时间格式不正确"):
        controller.build_updates(current={}, payload={"daily_sync_time": "not-a-time"})


def test_build_updates_falls_back_to_default_sync_time_when_missing():
    controller = SettingsController(services={})

    updates = controller.build_updates(current={}, payload={})

    assert updates["daily_sync_time"]  # DEFAULT_SYNC_TIME, non-empty and valid


def test_apply_legacy_persists_and_retunes_scraper():
    settings_service = FakeSettingsService()
    google_play = FakeGooglePlay()
    controller = SettingsController(
        services={"settings_service": settings_service, "google_play_service": google_play}
    )

    controller.apply_legacy({"proxy": "", "request_delay_seconds": "2.5", "theme": "teal"})

    assert settings_service.saved == {"proxy": "", "request_delay_seconds": "2.5", "theme": "teal"}
    assert google_play.configured_delay == 2.5


def test_apply_legacy_tolerates_missing_google_play_service():
    settings_service = FakeSettingsService()
    controller = SettingsController(services={"settings_service": settings_service})

    controller.apply_legacy({"request_delay_seconds": "1"})

    assert settings_service.saved == {"request_delay_seconds": "1"}


def test_reload_scheduler_calls_reload_jobs_when_present():
    scheduler = FakeScheduler()
    controller = SettingsController(services={"scheduler": scheduler})

    controller.reload_scheduler()

    assert scheduler.reloaded is True


def test_reload_scheduler_tolerates_missing_scheduler():
    controller = SettingsController(services={})
    controller.reload_scheduler()  # must not raise
