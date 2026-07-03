from __future__ import annotations

from typing import Any, Callable

from app.ui.formatting import alert_row


class AlertController:
    """Domain logic for listing and marking alerts read, shared between API
    mode (backend-owned alerts) and legacy/offline mode (local alert_service).
    QmlBridge owns the actual Slot surface, async dispatch (_run), and
    settingsChanged-style signal emission (alertsChanged, via _set_alerts).
    """

    def __init__(self, services: dict[str, object]) -> None:
        self.services = services

    def collect(self, api) -> dict[str, Any]:
        if api is not None:
            alerts = api.list_alerts(limit=200)
            return {
                "rows": [alert_row(alert) for alert in alerts],
                "unread": api.unread_count(),
            }
        alert_service = self.services["alert_service"]
        alerts = alert_service.list_alerts(limit=200)
        return {
            "rows": [alert_row(alert) for alert in alerts],
            "unread": alert_service.unread_count(),
        }

    def mark_all_read_fn(self, api) -> Callable[[], int]:
        """Returns the zero-arg callable that marks every alert read."""
        return api.mark_alerts_read if api is not None else self.services["alert_service"].mark_all_read

    def mark_read(self, api, alert_id: int) -> int:
        if api is not None:
            return api.mark_alerts_read([alert_id])
        return self.services["alert_service"].mark_read([alert_id])
