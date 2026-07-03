"""Retirement guard for the notification-dispatch pipeline.

The live-fetch sync path this file used to exercise is gone: ``TrackingService.
sync_app_now`` / ``sync_keyword_now`` / ``sync_chart_now`` are now permanent
raising stubs (see ``app/services/google_play_service.ServiceError``), and the
alert-creation methods that used to feed the notifier — ``AlertService.
create_snapshot_alerts``, ``create_keyword_alerts``, ``create_chart_alerts``,
``record_fetch_failure``, ``record_fetch_recovered`` — were deleted outright,
along with ``SnapshotRepository.upsert_for_day`` (the fixture helper this file
used to seed a "yesterday" baseline).

Every test previously here (high/medium severity dispatch, disabled-notifications
suppression, min-severity filtering, persistent-failure escalation alerts, and
sync_all's aggregated single-dispatch behavior) exercised that now-deleted path
through ``sync_app_now``/``sync_all`` and has no remaining equivalent: since
``sync_*_now`` always raises, ``sync_all_apps``/``sync_all_keywords``/
``sync_all_charts`` catch-and-skip every item and ``sync_all`` always dispatches
an empty batch. That "always raises" contract is already guarded by
``tests/test_failure_escalation.py`` (``test_sync_app_now_raises_retired_error``
/ ``test_sync_keyword_now_raises_retired_error``), so nothing here would add
coverage — this file is intentionally left as a documented no-op rather than
resurrected with fixtures for functionality that no longer exists.
"""

from __future__ import annotations
