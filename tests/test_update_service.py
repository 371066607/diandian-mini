from app.services.update_service import UpdateService, is_newer, parse_version


def test_parse_version():
    assert parse_version("v1.2.3") == (1, 2, 3)
    assert parse_version("1.2.3") == (1, 2, 3)
    assert parse_version("v2.0") == (2, 0)
    assert parse_version("1.2.0-beta.1") == (1, 2, 0)
    assert parse_version("") == ()
    assert parse_version(None) == ()


def test_is_newer():
    assert is_newer("1.1.0", "1.0.0")
    assert is_newer("v2.0.0", "1.9.9")
    assert is_newer("1.0.1", "1.0.0")
    assert not is_newer("1.0.0", "1.0.0")
    assert not is_newer("1.0.0", "1.2.0")  # current is newer
    assert not is_newer("", "1.0.0")
    assert is_newer("1.2", "1.1.9")  # uneven lengths


def test_check_detects_update(monkeypatch):
    service = UpdateService(repo="x/y", current_version="1.0.0")
    service._fetch_latest_release = lambda: {
        "tag_name": "v1.3.0",
        "html_url": "https://github.com/x/y/releases/tag/v1.3.0",
        "body": "新功能",
    }
    result = service.check()
    assert result.has_update is True
    assert result.latest_version == "v1.3.0"
    assert result.download_url.endswith("v1.3.0")
    assert result.error is None


def test_check_reports_up_to_date():
    service = UpdateService(repo="x/y", current_version="1.3.0")
    service._fetch_latest_release = lambda: {"tag_name": "v1.3.0", "html_url": "u", "body": ""}
    result = service.check()
    assert result.has_update is False
    assert result.latest_version == "v1.3.0"


def test_check_handles_no_releases():
    from urllib.error import HTTPError

    service = UpdateService(repo="x/y", current_version="1.0.0")

    def _raise_404():
        raise HTTPError("u", 404, "Not Found", {}, None)

    service._fetch_latest_release = _raise_404
    result = service.check()
    assert result.has_update is False
    assert result.error is None  # 404 (no releases) is not an error state
