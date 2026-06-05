from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

import app.ui.widgets.settings_form as settings_form
from app.db.database import Database
from app.services.settings_service import SettingsService
from app.ui.widgets.settings_form import SettingsFormWidget


class _FakeGooglePlayService:
    def __init__(self) -> None:
        self.configured: dict | None = None

    def configure(self, **kwargs) -> None:
        self.configured = kwargs


class _FakeScheduler:
    def __init__(self) -> None:
        self.reloaded = 0

    def reload_jobs(self) -> None:
        self.reloaded += 1


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def services(tmp_path):
    db = Database(str(tmp_path / "s.sqlite3"))
    db.create_all()
    settings_service = SettingsService(db)
    settings_service.ensure_defaults()
    return {
        "settings_service": settings_service,
        "google_play_service": _FakeGooglePlayService(),
        "scheduler": _FakeScheduler(),
    }


@pytest.fixture
def widget(qapp, services, monkeypatch):
    monkeypatch.setattr(settings_form, "show_info", lambda *a, **k: None)
    monkeypatch.setattr(settings_form, "show_error", lambda *a, **k: None)
    return SettingsFormWidget(services)


def test_load_reflects_defaults(widget):
    assert widget.scheduler_enabled.isChecked() is True
    assert widget.default_limit.value() == 50
    assert widget.daily_sync_time.time().toString("HH:mm") == "09:00"
    assert widget.request_delay.value() == 1.0
    assert widget.alert_rating_drop.value() == pytest.approx(0.2)
    assert widget.alert_growth_percent.value() == pytest.approx(10.0)
    assert widget.alert_keyword_top_band.value() == 10
    assert widget.alert_keyword_move.value() == 5


def test_save_persists_str_payload(widget, services):
    from PySide6.QtCore import QTime

    widget.scheduler_enabled.setChecked(False)
    widget.default_limit.setValue(120)
    widget.alert_rating_drop.setValue(0.5)
    widget.daily_sync_time.setTime(QTime(8, 30))

    widget.save()

    stored = services["settings_service"].get_all()
    assert stored["scheduler_enabled"] == "false"
    assert stored["default_limit"] == "120"
    assert stored["alert_rating_drop"] == "0.5"
    assert stored["daily_sync_time"] == "08:30"
    # every persisted value is a string
    assert all(isinstance(v, str) for v in stored.values())
    # single save path side effects fired
    assert services["google_play_service"].configured is not None
    assert services["scheduler"].reloaded == 1


def test_save_emits_valid_time(widget, services):
    from app.utils.time_utils import is_valid_time_of_day

    widget.save()
    stored = services["settings_service"].get_all()
    assert is_valid_time_of_day(stored["daily_sync_time"])
