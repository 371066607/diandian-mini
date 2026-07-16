import sys

from app.composition import build_services
from app.constants import (
    AUTH_DEVICE_ID_SETTING,
    DEFAULT_STOREINTEL_API_URL,
)
from app.db.database import Database
from app.jobs.scheduler import AppScheduler, RemoteSchedulerProxy
from app.services.settings_service import SettingsService


def _make_scheduler(tmp_path, *, enabled="true", sync_time="09:00"):
    db = Database(str(tmp_path / "sched.sqlite3"))
    db.create_all()
    settings = SettingsService(db)
    settings.ensure_defaults()
    settings.set_many({"scheduler_enabled": enabled, "daily_sync_time": sync_time})
    return AppScheduler(settings, object())


def test_scheduler_starts_registers_job_and_stops(tmp_path):
    sched = _make_scheduler(tmp_path)
    sched.start()
    assert sched.scheduler.running
    assert "sync_tracked" in [job.id for job in sched.scheduler.get_jobs()]

    sched.shutdown()
    assert not sched.scheduler.running  # closing the app must stop the scheduler thread


def test_scheduler_disabled_does_not_start(tmp_path):
    sched = _make_scheduler(tmp_path, enabled="false")
    sched.start()
    assert not sched.scheduler.running
    sched.shutdown()  # must be safe even when never started


def test_scheduler_malformed_sync_time_does_not_crash(tmp_path):
    sched = _make_scheduler(tmp_path, sync_time="not-a-time")
    sched.start()  # must not raise despite the bad value (falls back to 09:00)
    assert sched.scheduler.running
    sched.shutdown()


def test_build_services_defaults_to_remote_url_when_running_from_source(tmp_path, monkeypatch):
    monkeypatch.delenv("CATCH_RADAR_STOREINTEL_API_URL", raising=False)
    monkeypatch.delenv("STOREINTEL_API_URL", raising=False)
    monkeypatch.delenv("CATCH_RADAR_LEGACY_LOCAL_MODE", raising=False)
    monkeypatch.delenv("CATCH_RADAR_OFFLINE_MODE", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    db = Database(str(tmp_path / "default-api-mode.sqlite3"))
    db.create_all()

    services = build_services(db)

    client = services["store_intel_api_client"]
    assert client.enabled is True
    assert client.base_url == DEFAULT_STOREINTEL_API_URL
    stored_device_id = SettingsService(db).get(AUTH_DEVICE_ID_SETTING)
    assert stored_device_id == client.device_id
    assert stored_device_id.startswith("desktop-")

    services_again = build_services(db)
    assert services_again["store_intel_api_client"].device_id == stored_device_id
    scheduler = services["scheduler"]
    assert isinstance(scheduler, RemoteSchedulerProxy)
    scheduler.start()
    scheduler.reload_jobs()
    scheduler.shutdown()


def test_build_services_defaults_to_production_url_when_frozen(tmp_path, monkeypatch):
    monkeypatch.delenv("CATCH_RADAR_STOREINTEL_API_URL", raising=False)
    monkeypatch.delenv("STOREINTEL_API_URL", raising=False)
    monkeypatch.delenv("CATCH_RADAR_LEGACY_LOCAL_MODE", raising=False)
    monkeypatch.delenv("CATCH_RADAR_OFFLINE_MODE", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    db = Database(str(tmp_path / "frozen-default-api-mode.sqlite3"))
    db.create_all()

    services = build_services(db)

    client = services["store_intel_api_client"]
    assert client.enabled is True
    assert client.base_url == DEFAULT_STOREINTEL_API_URL


def test_build_services_honors_api_url_override(tmp_path, monkeypatch):
    monkeypatch.setenv("CATCH_RADAR_STOREINTEL_API_URL", "https://staging.catchradar.example")
    db = Database(str(tmp_path / "api-mode.sqlite3"))
    db.create_all()

    services = build_services(db)

    client = services["store_intel_api_client"]
    assert client.enabled is True
    assert client.base_url == "https://staging.catchradar.example"
    scheduler = services["scheduler"]
    assert isinstance(scheduler, RemoteSchedulerProxy)
    scheduler.start()
    scheduler.reload_jobs()
    scheduler.shutdown()


def test_build_services_ignores_local_mode_env_and_uses_remote_scheduler(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("CATCH_RADAR_STOREINTEL_API_URL", raising=False)
    monkeypatch.delenv("STOREINTEL_API_URL", raising=False)
    monkeypatch.setenv("CATCH_RADAR_LEGACY_LOCAL_MODE", "true")
    db = Database(str(tmp_path / "legacy-local-mode.sqlite3"))
    db.create_all()

    services = build_services(db)

    client = services["store_intel_api_client"]
    assert client.enabled is True
    assert client.base_url == DEFAULT_STOREINTEL_API_URL
    assert SettingsService(db).get(AUTH_DEVICE_ID_SETTING) == client.device_id
    scheduler = services["scheduler"]
    assert isinstance(scheduler, RemoteSchedulerProxy)
    scheduler.shutdown()


def test_build_services_ignores_localhost_api_override(tmp_path, monkeypatch):
    monkeypatch.setenv("CATCH_RADAR_STOREINTEL_API_URL", "http://127.0.0.1:8081")
    monkeypatch.delenv("CATCH_RADAR_ALLOW_LOCAL_API", raising=False)
    db = Database(str(tmp_path / "localhost-ignored.sqlite3"))
    db.create_all()

    services = build_services(db)

    client = services["store_intel_api_client"]
    assert client.enabled is True
    assert client.base_url == DEFAULT_STOREINTEL_API_URL


def test_build_services_allows_localhost_api_override_when_explicitly_enabled(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("CATCH_RADAR_STOREINTEL_API_URL", "http://127.0.0.1:18082")
    monkeypatch.setenv("CATCH_RADAR_ALLOW_LOCAL_API", "true")
    db = Database(str(tmp_path / "localhost-enabled.sqlite3"))
    db.create_all()

    services = build_services(db)

    client = services["store_intel_api_client"]
    assert client.enabled is True
    assert client.base_url == "http://127.0.0.1:18082"
    assert isinstance(services["scheduler"], RemoteSchedulerProxy)
    services["scheduler"].shutdown()
