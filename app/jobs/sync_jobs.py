from __future__ import annotations


def sync_tracked_job(tracking_service):
    """Daily job: sync every enabled tracked app *and* keyword."""
    return tracking_service.sync_all()
