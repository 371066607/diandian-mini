from app.db.database import Database
from app.jobs.scheduler import AppScheduler
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
