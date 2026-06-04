from __future__ import annotations

from datetime import datetime, time

DEFAULT_SYNC_TIME = "09:00"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


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
