import io
import zipfile

import pytest

import bootstrap
from app.services.update_service import UpdateService


def test_version_to_date():
    assert bootstrap.version_to_date(0) == "开发版"
    assert bootstrap.version_to_date(1_700_000_000).startswith("20")  # a real timestamp


def test_check_git_up_to_date(monkeypatch):
    service = UpdateService(project_root="/tmp")
    monkeypatch.setattr(service, "_remote_branch", lambda: "origin/main")

    def fake_git(*args):
        return {("rev-parse", "HEAD"): "abc", ("rev-parse", "origin/main"): "abc"}.get(
            args, "0" if args[:2] == ("rev-list", "--count") else ""
        )

    monkeypatch.setattr(service, "_git", fake_git)
    result = service._check_git()
    assert result.mode == "git" and result.up_to_date


def test_check_git_behind(monkeypatch):
    service = UpdateService(project_root="/tmp")
    monkeypatch.setattr(service, "_remote_branch", lambda: "origin/main")

    def fake_git(*args):
        return {
            ("rev-parse", "HEAD"): "aaa",
            ("rev-parse", "origin/main"): "bbb",
            ("rev-list", "--count", "HEAD..origin/main"): "3",
        }.get(args, "")

    monkeypatch.setattr(service, "_git", fake_git)
    result = service._check_git()
    assert not result.up_to_date and result.behind == 3


def test_check_patch_detects_update(monkeypatch):
    service = UpdateService()
    monkeypatch.setattr(service, "current_version", lambda: 100)
    service._fetch_code_release = lambda: {"body": "codever:200\nchangelog:修复若干问题"}
    result = service._check_patch()
    assert result.mode == "patch"
    assert result.can_patch and not result.up_to_date
    assert result.latest_version == 200
    assert result.changelog == "修复若干问题"


def test_check_patch_up_to_date(monkeypatch):
    service = UpdateService()
    monkeypatch.setattr(service, "current_version", lambda: 300)
    service._fetch_code_release = lambda: {"body": "codever:200"}
    result = service._check_patch()
    assert result.up_to_date and not result.can_patch


def test_fetch_code_release_raises_when_curl_fallback_gets_http_404(monkeypatch):
    # urllib fails outright (e.g. TLS/network hiccup) so it falls through to the curl
    # fallback. curl itself exits 0 on a 404 (the transport succeeded, only the HTTP
    # status is bad) and returns GitHub's error JSON — that must not be mistaken for a
    # real release body, or a nonexistent-repo 404 silently reads as "no update".
    service = UpdateService(repo="371066607/does-not-exist")
    monkeypatch.setattr(
        "app.services.update_service.urlopen",
        lambda *a, **k: (_ for _ in ()).throw(OSError("simulated network failure")),
    )
    monkeypatch.setattr("app.services.update_service.shutil.which", lambda name: "/usr/bin/curl")

    class FakeCurlResult:
        returncode = 0
        stdout = '{"message": "Not Found", "documentation_url": "https://docs.github.com/x"}\n404'

    monkeypatch.setattr(
        "app.services.update_service.proc.run", lambda *a, **k: FakeCurlResult()
    )

    with pytest.raises(Exception):
        service._fetch_code_release()


def test_check_patch_surfaces_error_instead_of_masking_it_as_up_to_date(monkeypatch):
    service = UpdateService()
    monkeypatch.setattr(service, "current_version", lambda: 1782489690)

    def boom():
        raise RuntimeError("GitHub API request failed: HTTP 404")

    monkeypatch.setattr(service, "_fetch_code_release", boom)
    result = service._check_patch()
    assert not result.up_to_date
    assert result.error and "404" in result.error


def test_download_and_apply_patch(tmp_path, monkeypatch):
    # a fake patch zip carrying code_version.txt + a marker module
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("code_version.txt", "999")
        zf.writestr("app/marker.txt", "patched")
    payload = buf.getvalue()

    override = tmp_path / "app_override"
    monkeypatch.setattr(bootstrap, "code_override_dir", lambda: str(override))

    class FakeResponse:
        def __init__(self, data):
            self._data = data
            self.headers = {"Content-Length": str(len(data))}
            self._sent = False

        def read(self, _n=-1):
            if self._sent:
                return b""
            self._sent = True
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        "app.services.update_service.urlopen", lambda url, timeout=60: FakeResponse(payload)
    )

    UpdateService().download_and_apply_patch()

    assert (override / "code_version.txt").read_text() == "999"
    assert (override / "app" / "marker.txt").read_text() == "patched"
    assert bootstrap.read_code_version(str(override)) == 999
