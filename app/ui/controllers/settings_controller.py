from __future__ import annotations

from typing import Any

from app.constants import DEFAULT_SETTINGS
from app.utils.network import apply_proxy_env
from app.utils.normalize import safe_float
from app.utils.time_utils import DEFAULT_SYNC_TIME, is_valid_time_of_day


class SettingsError(RuntimeError):
    """A user-facing validation failure (e.g. a malformed daily_sync_time)."""


class SettingsController:
    """Domain logic for saving app settings, shared between API mode (the
    backend owns persistence) and legacy/offline mode (local SettingsService
    + retuning the local scraper/scheduler). QmlBridge owns the actual
    saveSettings @Slot, async dispatch (_run), and signal emission; this
    class owns validation/merge and the legacy-mode side effects only.
    """

    def __init__(self, services: dict[str, object]) -> None:
        self.services = services

    def build_updates(self, current: dict[str, Any], payload: dict[str, Any]) -> dict[str, str]:
        """Merge a partial QML payload over current settings (defaulted),
        validating daily_sync_time. Raises SettingsError with a user-facing
        message on invalid input."""
        updates = DEFAULT_SETTINGS.copy()
        updates.update(current)
        for key in updates:
            if key in payload:
                updates[key] = str(payload[key]).strip()

        sync_time = updates.get("daily_sync_time") or DEFAULT_SYNC_TIME
        if not is_valid_time_of_day(sync_time):
            raise SettingsError("每日同步时间格式不正确，请使用 HH:MM（例如 09:00）。")
        updates["daily_sync_time"] = sync_time
        updates["default_country"] = updates.get("default_country") or "us"
        updates["default_lang"] = updates.get("default_lang") or "en"
        updates["default_limit"] = updates.get("default_limit") or "50"
        updates["request_delay_seconds"] = updates.get("request_delay_seconds") or "1"
        return updates

    def apply_legacy(self, updates: dict[str, str]) -> None:
        """Persist updates via the local SettingsService and retune the
        scraper — legacy/offline mode only (API mode instead calls
        api.set_settings directly, see QmlBridge.saveSettings)."""
        self.services["settings_service"].set_many(updates)
        apply_proxy_env(updates.get("proxy", ""))
        google_play_service = self.services.get("google_play_service")
        if google_play_service is not None and hasattr(google_play_service, "configure"):
            google_play_service.configure(
                request_delay_seconds=safe_float(updates["request_delay_seconds"], 1.0)
            )

    def reload_scheduler(self) -> None:
        scheduler = self.services.get("scheduler")
        if scheduler is not None and hasattr(scheduler, "reload_jobs"):
            scheduler.reload_jobs()
