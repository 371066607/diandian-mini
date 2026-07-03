from types import SimpleNamespace

from app.ui.controllers.alert_controller import AlertController


def _alert(**overrides):
    defaults = dict(
        id=1,
        created_at="2026-06-18T09:00:00",
        severity="warning",
        type="rating_drop",
        app_id="com.demo",
        message="评分下降",
        is_read=False,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class FakeApi:
    def __init__(self, alerts, unread):
        self._alerts = alerts
        self._unread = unread
        self.calls = []

    def list_alerts(self, limit=200):
        self.calls.append(("list_alerts", limit))
        return self._alerts

    def unread_count(self):
        return self._unread

    def mark_alerts_read(self, ids=None):
        self.calls.append(("mark_alerts_read", ids))
        return len(ids) if ids is not None else self._unread


class FakeAlertService:
    def __init__(self, alerts, unread):
        self._alerts = alerts
        self._unread = unread
        self.calls = []

    def list_alerts(self, limit=200):
        self.calls.append(("list_alerts", limit))
        return self._alerts

    def unread_count(self):
        return self._unread

    def mark_read(self, ids):
        self.calls.append(("mark_read", ids))
        return len(ids)

    def mark_all_read(self):
        self.calls.append(("mark_all_read",))
        return self._unread


def test_collect_uses_api_when_available():
    api = FakeApi([_alert(id=1), _alert(id=2, is_read=True)], unread=1)
    controller = AlertController(services={})

    result = controller.collect(api)

    assert result["unread"] == 1
    assert [row["id"] for row in result["rows"]] == [1, 2]
    assert result["rows"][0]["unread"] is True
    assert result["rows"][1]["unread"] is False
    assert ("list_alerts", 200) in api.calls


def test_collect_falls_back_to_local_alert_service_without_api():
    service = FakeAlertService([_alert(id=5)], unread=3)
    controller = AlertController(services={"alert_service": service})

    result = controller.collect(None)

    assert result["unread"] == 3
    assert result["rows"][0]["id"] == 5
    assert ("list_alerts", 200) in service.calls


def test_mark_all_read_fn_prefers_api():
    api = FakeApi([], unread=0)
    controller = AlertController(services={})

    fn = controller.mark_all_read_fn(api)
    fn()

    assert ("mark_alerts_read", None) in api.calls


def test_mark_all_read_fn_falls_back_to_local_service():
    service = FakeAlertService([], unread=0)
    controller = AlertController(services={"alert_service": service})

    fn = controller.mark_all_read_fn(None)
    fn()

    assert ("mark_all_read",) in service.calls


def test_mark_read_prefers_api():
    api = FakeApi([], unread=0)
    controller = AlertController(services={})

    result = controller.mark_read(api, 42)

    assert result == 1
    assert ("mark_alerts_read", [42]) in api.calls


def test_mark_read_falls_back_to_local_service():
    service = FakeAlertService([], unread=0)
    controller = AlertController(services={"alert_service": service})

    result = controller.mark_read(None, 42)

    assert result == 1
    assert ("mark_read", [42]) in service.calls
