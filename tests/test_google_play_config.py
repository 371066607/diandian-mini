import pytest

from app.services.google_play_service import GooglePlayService

pytestmark = pytest.mark.legacy


def test_request_delay_default_and_configure():
    service = GooglePlayService()
    assert service.request_delay_seconds == 1.0

    service.configure(request_delay_seconds=2.5)
    assert service.request_delay_seconds == 2.5

    service.configure()  # no-op: None leaves the current value untouched
    assert service.request_delay_seconds == 2.5


def test_request_delay_clamped_non_negative():
    service = GooglePlayService(request_delay_seconds=-3.0)
    assert service.request_delay_seconds == 0.0

    service.configure(request_delay_seconds=-1.0)
    assert service.request_delay_seconds == 0.0
