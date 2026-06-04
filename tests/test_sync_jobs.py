from app.jobs.sync_jobs import sync_tracked_job


class FakeTrackingService:
    def __init__(self):
        self.sync_all_called = False

    def sync_all(self):
        self.sync_all_called = True
        return {"apps": 2, "keywords": 3}


def test_sync_tracked_job_runs_sync_all_for_apps_and_keywords():
    fake = FakeTrackingService()
    result = sync_tracked_job(fake)
    assert fake.sync_all_called is True
    assert result == {"apps": 2, "keywords": 3}
