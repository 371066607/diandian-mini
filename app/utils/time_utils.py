from __future__ import annotations

from datetime import datetime, time, timedelta

DEFAULT_SYNC_TIME = "09:00"

# Per-item auto-sync cadence. The scheduler fires once daily, so these gate how often a
# tracked item actually re-syncs on each fire. "manual" never auto-syncs (None interval).
# The daily interval is < 24h to tolerate scheduler drift / a slightly-early daily run.
FREQUENCY_HOURS: dict[str, float | None] = {"daily": 20, "weekly": 164, "manual": None}
SUPPORTED_FREQUENCIES = ("daily", "weekly", "manual")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def is_sync_due(last_synced_at: str | None, frequency: str | None, now: datetime | None = None) -> bool:
    """Whether a tracked item is due for an auto-sync given its cadence and last sync.

    Unknown frequencies fall back to daily; an item never synced (or with an unparseable
    timestamp) is always due; "manual" is never auto-due. Never raises."""
    interval = FREQUENCY_HOURS.get((frequency or "daily").lower(), FREQUENCY_HOURS["daily"])
    if interval is None:
        return False
    if not last_synced_at:
        return True
    try:
        last = _parse_iso_datetime(last_synced_at)
    except (ValueError, TypeError):
        return True
    current = now or datetime.now(last.tzinfo)
    if last.tzinfo is not None and current.tzinfo is None:
        current = current.replace(tzinfo=last.tzinfo)
    elif last.tzinfo is None and current.tzinfo is not None:
        current = current.replace(tzinfo=None)
    return current - last >= timedelta(hours=interval)


def _parse_iso_datetime(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    return datetime.fromisoformat(normalized)


def format_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.isoformat(timespec="seconds")


def parse_time_of_day(value: str, default: str = DEFAULT_SYNC_TIME) -> time:
    """Parse ``"HH:MM"`` into a :class:`time`, falling back to ``default``.

    This never raises: a malformed value that somehow made it into the settings
    table must not be able to crash the scheduler (and therefore app startup).
    """
    for candidate in (value, default):
        parsed = _try_parse_time(candidate)
        if parsed is not None:
            return parsed
    return time(hour=9, minute=0)


def is_valid_time_of_day(value: str) -> bool:
    """Return True if ``value`` is a well-formed ``HH:MM`` time of day."""
    return _try_parse_time(value) is not None


def _try_parse_time(value: str | None) -> time | None:
    if not value or ":" not in value:
        return None
    hour_text, minute_text = value.split(":", 1)
    try:
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError:
        return None
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return time(hour=hour, minute=minute)
    return None
