from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from urllib.request import urlopen

import bootstrap
from app.constants import GITHUB_REPO
from app.utils import proc

CODE_TAG = "code"  # the GitHub release tag that carries the hot-patch (app-code.zip)


@dataclass
class UpdateResult:
    mode: str  # "git" (running from source) or "patch" (packaged build)
    up_to_date: bool
    local_version: int = 0
    latest_version: int = 0
    behind: int = 0
    changelog: str = ""
    can_patch: bool = False
    error: str | None = None
    sha256: str = ""  # expected SHA-256 of app-code.zip, from the release body

    @property
    def local_label(self) -> str:
        return bootstrap.version_to_date(self.local_version)

    @property
    def latest_label(self) -> str:
        return bootstrap.version_to_date(self.latest_version)


class UpdateService:
    """Checks for / applies updates the way the referenced desktop project does:

    - running from source (.git present) → ``git fetch`` + offer ``git pull`` + restart
    - packaged build → read the ``code`` release's ``codever`` and, if newer, hot-patch
      (download a small ``app-code.zip`` into the user override dir, then restart)
    """

    def __init__(self, repo: str = GITHUB_REPO, project_root: str | None = None, timeout: float = 15.0):
        self.repo = repo
        self.project_root = project_root or os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        self.timeout = timeout

    def current_version(self) -> int:
        return bootstrap.effective_code_version()

    def current_label(self) -> str:
        return bootstrap.version_to_date(self.current_version())

    # --- check ---------------------------------------------------------------

    def check(self) -> UpdateResult:
        if os.path.isdir(os.path.join(self.project_root, ".git")):
            return self._check_git()
        return self._check_patch()

    def _git(self, *args: str) -> str:
        out = proc.run(
            ["git", *args], cwd=self.project_root, capture_output=True, text=True, timeout=30
        )
        return out.stdout.strip()

    def _remote_branch(self) -> str:
        for ref in ("origin/main", "origin/master"):
            check = proc.run(
                ["git", "rev-parse", "--verify", ref],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if check.returncode == 0:
                return ref
        return "origin/main"

    def _check_git(self) -> UpdateResult:
        try:
            self._git("fetch", "--quiet")
            local = self._git("rev-parse", "HEAD")
            ref = self._remote_branch()
            remote = self._git("rev-parse", ref)
            behind = self._git("rev-list", "--count", f"HEAD..{ref}") or "0"
            return UpdateResult(
                mode="git", up_to_date=bool(local) and local == remote, behind=int(behind or 0)
            )
        except Exception as exc:  # noqa: BLE001
            return UpdateResult(mode="git", up_to_date=False, error=str(exc))

    def _fetch_code_release(self) -> dict:
        url = f"https://api.github.com/repos/{self.repo}/releases/tags/{CODE_TAG}"
        from urllib.request import Request

        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "CatchRadar",
            "Accept-Encoding": "identity",
        }
        # urllib path — 3 attempts
        last_exc: Exception | None = None
        for _ in range(3):
            try:
                with urlopen(Request(url, headers=headers), timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception as exc:  # noqa: BLE001
                last_exc = exc

        # curl fallback — same as _request_text; handles IncompleteRead / RemoteDisconnected.
        # curl exits 0 even on a 4xx/5xx response (the transport itself succeeded), so the
        # HTTP status has to be checked explicitly — otherwise a 404 body (no "codever" in
        # it) silently parses into an empty/zero result instead of surfacing as a failure.
        curl = shutil.which("curl")
        if curl:
            try:
                result = proc.run(
                    [curl, "-sS", "-L", "--http1.1", "-w", "\n%{http_code}",
                     "-H", f"Accept: {headers['Accept']}",
                     "-H", f"User-Agent: {headers['User-Agent']}",
                     url],
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode == 0 and result.stdout:
                    body, _, status = result.stdout.rpartition("\n")
                    if status.strip() == "200" and body:
                        return json.loads(body)
                    last_exc = RuntimeError(f"GitHub API request failed: HTTP {status.strip() or '?'}")
            except Exception as exc:  # noqa: BLE001
                last_exc = exc

        raise last_exc  # type: ignore[misc]

    def _check_patch(self) -> UpdateResult:
        local = self.current_version()
        try:
            data = self._fetch_code_release()
        except Exception as exc:  # noqa: BLE001 - any failure is non-fatal
            return UpdateResult(mode="patch", up_to_date=False, local_version=local, error=str(exc))
        body = data.get("body") or ""
        match = re.search(r"codever:(\d+)", body)
        latest = int(match.group(1)) if match else 0
        changelog = re.search(r"changelog:(.+)", body)
        return UpdateResult(
            mode="patch",
            local_version=local,
            latest_version=latest,
            changelog=changelog.group(1).strip() if changelog else "",
            up_to_date=local > 0 and latest > 0 and latest <= local,
            can_patch=latest > local,
            sha256=self._parse_sha256(body),
        )

    @staticmethod
    def _parse_sha256(body: str) -> str:
        match = re.search(r"sha256:([0-9a-fA-F]{64})", body or "")
        return match.group(1).lower() if match else ""

    # --- apply ---------------------------------------------------------------

    def patch_zip_url(self) -> str:
        return f"https://github.com/{self.repo}/releases/download/{CODE_TAG}/app-code.zip"

    def download_and_apply_patch(self, progress=None, expected_sha256: str | None = None) -> None:
        """Download the code patch, verify it, and atomically replace the override dir."""
        zip_path = os.path.join(tempfile.gettempdir(), "catch_radar_code.zip")
        staging = os.path.join(tempfile.gettempdir(), "catch_radar_code_stage")
        override = bootstrap.code_override_dir()

        if expected_sha256 is None:
            # None = caller didn't carry the checksum from check() — re-read the
            # release body so a corrupted download can still be rejected. An empty
            # string means the caller already knows the release publishes none.
            try:
                expected_sha256 = self._parse_sha256(self._fetch_code_release().get("body") or "")
            except Exception:  # noqa: BLE001 - metadata refetch is best-effort
                expected_sha256 = ""

        if progress:
            progress("正在下载更新补丁…", None)
        patch_url = self.patch_zip_url()
        data: bytes | None = None
        try:
            with urlopen(patch_url, timeout=60) as resp:
                data = resp.read()
        except Exception:  # noqa: BLE001
            pass
        if not data:
            curl = shutil.which("curl")
            if not curl:
                raise RuntimeError("urllib 下载失败且系统中未找到 curl，无法下载补丁")
            completed = proc.run(
                [curl, "-sS", "-L", "--http1.1", "-o", zip_path, patch_url],
                capture_output=True, text=True, timeout=120,
            )
            if completed.returncode != 0:
                raise RuntimeError(f"curl 下载补丁失败：{completed.stderr[:200]}")
            # curl wrote directly to zip_path — skip the write step below
            data = b""  # sentinel: file already written
        if data:
            with open(zip_path, "wb") as fh:
                fh.write(data)

        # Integrity gate: the release publishes "sha256:<hex>" in its body. A zip
        # that doesn't match (truncated download, CDN corruption, tampering) must
        # never be extracted over the code override dir. Releases published before
        # this convention carry no checksum — those proceed unverified.
        if expected_sha256:
            actual = self._file_sha256(zip_path)
            if actual != expected_sha256.lower():
                try:
                    os.remove(zip_path)
                except Exception:  # noqa: BLE001
                    pass
                raise RuntimeError(
                    f"补丁校验失败：SHA-256 不匹配（期望 {expected_sha256[:12]}…，"
                    f"实际 {actual[:12]}…），已中止更新。"
                )

        if progress:
            progress("正在应用补丁…", None)
        if os.path.isdir(staging):
            shutil.rmtree(staging, ignore_errors=True)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(staging)
        if bootstrap.read_code_version(staging) <= 0:
            raise RuntimeError("补丁内容不完整（缺 code_version.txt）")
        os.makedirs(os.path.dirname(override), exist_ok=True)
        if os.path.isdir(override):
            shutil.rmtree(override, ignore_errors=True)
        shutil.move(staging, override)
        try:
            os.remove(zip_path)
        except Exception:
            pass

    @staticmethod
    def _file_sha256(path: str) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def git_pull(self) -> tuple[bool, str]:
        try:
            out = proc.run(
                ["git", "pull"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return out.returncode == 0, (out.stdout + out.stderr).strip()[-400:]
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    @staticmethod
    def restart() -> None:
        if getattr(sys, "frozen", False):
            proc.popen([sys.executable])
        else:
            os.execv(sys.executable, [sys.executable, *sys.argv])
        os._exit(0)
