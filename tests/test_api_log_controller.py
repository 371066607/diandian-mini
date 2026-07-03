from app.ui.controllers.api_log_controller import ApiLogController


def test_api_log_controller_normalizes_and_appends_entries():
    controller = ApiLogController(limit=200)

    appended = controller.append(
        {
            "time": "12:00:00",
            "method": "GET",
            "path": "/api/store-intel/apps/search",
            "query": "q=notes",
            "body": None,
            "response": '{"items":[]}',
            "status": 200,
            "code": 200,
            "duration_ms": 42,
            "ok": True,
            "error": "",
            "stream": False,
        }
    )

    assert appended is True
    assert len(controller.entries) == 1
    row = controller.entries[0]
    assert row["method"] == "GET"
    assert row["query"] == "q=notes"
    assert row["queryFull"] == "q=notes"
    assert row["duration"] == "42ms"
    assert row["ok"] is True
    assert row["status"] == "200"


def test_api_log_controller_ignores_non_dict_entries():
    controller = ApiLogController()
    assert controller.append("not a dict") is False
    assert controller.append(None) is False
    assert controller.entries == []


def test_api_log_controller_trims_to_limit():
    controller = ApiLogController(limit=3)
    for i in range(5):
        controller.append({"path": f"/req/{i}"})

    assert len(controller.entries) == 3
    assert [row["path"] for row in controller.entries] == ["/req/2", "/req/3", "/req/4"]


def test_api_log_controller_clear_empties_entries():
    controller = ApiLogController()
    controller.append({"path": "/req/1"})
    assert controller.entries

    controller.clear()

    assert controller.entries == []
