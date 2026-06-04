from datetime import time

from app.utils.time_utils import (
    DEFAULT_SYNC_TIME,
    is_valid_time_of_day,
    parse_time_of_day,
)


def test_parse_time_of_day_valid():
    assert parse_time_of_day("09:30") == time(9, 30)
    assert parse_time_of_day("8:5") == time(8, 5)
    assert parse_time_of_day("23:59") == time(23, 59)
    assert parse_time_of_day("00:00") == time(0, 0)


def test_parse_time_of_day_falls_back_on_malformed():
    # Malformed values must NEVER raise — a bad persisted value cannot be allowed
    # to crash the scheduler (and thus app startup). They fall back to 09:00.
    for bad in ["9", "", "abc", "25:00", "12:60", "-1:00", "9:", ":30", "1:2:3"]:
        assert parse_time_of_day(bad) == time(9, 0)


def test_parse_time_of_day_custom_default():
    assert parse_time_of_day("nope", default="06:15") == time(6, 15)
    # if both the value and the default are unusable, hard-fall back to 09:00
    assert parse_time_of_day("nope", default="also-bad") == time(9, 0)


def test_is_valid_time_of_day():
    assert is_valid_time_of_day("09:00")
    assert is_valid_time_of_day("8:5")
    assert not is_valid_time_of_day("9")
    assert not is_valid_time_of_day("25:00")
    assert not is_valid_time_of_day("12:60")
    assert not is_valid_time_of_day("")
    assert not is_valid_time_of_day("nine")


def test_default_sync_time_constant_is_valid():
    assert is_valid_time_of_day(DEFAULT_SYNC_TIME)
