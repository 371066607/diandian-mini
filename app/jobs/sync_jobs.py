from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def sync_tracked_job(tracking_service, retention_service=None):
    """Daily job: sync every enabled tracked app *and* keyword that is *due* for its
    configured cadence (daily / weekly / manual). Manual items never auto-sync.

    After syncing, runs history retention cleanup if a retention service is available.
    The retention service may be passed explicitly or attached to ``tracking_service`` as
    ``retention_service`` (the scheduler's fixed ``args=[tracking_service]`` can't be
    changed without editing scheduler.py). Cleanup failures are logged, never propagated,
    so a retention problem can't break the sync job.
    """
    result = tracking_service.sync_all(due_only=True)

    retention = retention_service or getattr(tracking_service, "retention_service", None)
    if retention is not None:
        try:
            retention.cleanup()
        except Exception:
            logger.exception("sync_tracked_job: history retention cleanup failed")

    return result
