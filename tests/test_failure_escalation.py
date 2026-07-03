"""Retirement guard: the legacy live-fetch sync entry points (``sync_app_now`` /
``sync_keyword_now``) are permanently retired stubs that always raise
``ServiceError`` — the consecutive-failure tracking, escalation, and recovery
alert behavior they used to drive no longer exists anywhere in the codebase."""

from __future__ import annotations

import pytest

from app.db.database import Database
from app.services.alert_service import AlertService
from app.services.google_play_service import ServiceError
from app.services.settings_service import SettingsService
from app.services.tracking_service import TrackingService


def _build(tmp_path, name):
    db = Database(str(tmp_path / f"{name}.sqlite3"))
    db.create_all()
    settings = SettingsService(db)
    settings.ensure_defaults()
    alert = AlertService(db, settings_service=settings)
    ts = TrackingService(db, None, alert_service=alert, settings_service=settings)
    return db, alert, ts


def test_sync_app_now_raises_retired_error(tmp_path):
    _, _, ts = _build(tmp_path, "esc")
    ts.add_app("com.x", "us", "en")
    with pytest.raises(ServiceError):
        ts.sync_app_now("com.x")


def test_sync_keyword_now_raises_retired_error(tmp_path):
    _, _, ts = _build(tmp_path, "kw")
    ts.add_keyword("messenger", "com.x", "us", "en")
    with pytest.raises(ServiceError):
        ts.sync_keyword_now("messenger", "com.x", "us", "en")
