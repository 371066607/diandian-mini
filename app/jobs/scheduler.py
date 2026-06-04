from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.jobs.sync_jobs import sync_tracked_job
from app.utils.time_utils import parse_time_of_day


class AppScheduler:
    def __init__(self, settings_service, tracking_service):
        self.settings_service = settings_service
        self.tracking_service = tracking_service
        self.scheduler = BackgroundScheduler()

    def start(self) -> None:
        settings = self.settings_service.get_all()
        if settings.get("scheduler_enabled", "true").lower() != "true":
            return
        if not self.scheduler.running:
            self.scheduler.start()
        self.reload_jobs()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def reload_jobs(self) -> None:
        enabled = self.settings_service.get("scheduler_enabled", "true").lower() == "true"
        if not enabled:
            if self.scheduler.running:
                self.scheduler.remove_all_jobs()
            return

        if not self.scheduler.running:
            self.scheduler.start()

        self.scheduler.remove_all_jobs()
        sync_time = parse_time_of_day(self.settings_service.get("daily_sync_time", "09:00"))
        trigger = CronTrigger(hour=sync_time.hour, minute=sync_time.minute)
        self.scheduler.add_job(
            sync_tracked_job,
            trigger=trigger,
            args=[self.tracking_service],
            id="sync_tracked",
            replace_existing=True,
        )
