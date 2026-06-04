from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.constants import APP_VERSION, GITHUB_REPO


@dataclass
class UpdateResult:
    current_version: str
    latest_version: str | None
    has_update: bool
    download_url: str | None = None
    notes: str = ""
    error: str | None = None


def parse_version(value: str | None) -> tuple[int, ...]:
    """Parse a version/tag like ``v1.2.3`` into a comparable tuple ``(1, 2, 3)``.

    Drops a leading ``v`` and any pre-release/build suffix (``1.2.0-beta`` -> ``(1, 2)``).
    """
    if not value:
        return ()
    cleaned = value.strip().lstrip("vV").split("-")[0].split("+")[0]
    numbers: list[int] = []
    for part in cleaned.split("."):
        match = re.match(r"\d+", part)
        if not match:
            break
        numbers.append(int(match.group()))
    return tuple(numbers)


def is_newer(latest: str | None, current: str | None) -> bool:
    """True if ``latest`` is a strictly newer version than ``current``."""
    latest_parts = parse_version(latest)
    current_parts = parse_version(current)
    if not latest_parts:
        return False
    length = max(len(latest_parts), len(current_parts))
    latest_parts += (0,) * (length - len(latest_parts))
    current_parts += (0,) * (length - len(current_parts))
    return latest_parts > current_parts


class UpdateService:
    """Checks the project's GitHub Releases for a newer version (notify-only)."""

    def __init__(
        self,
        repo: str = GITHUB_REPO,
        current_version: str = APP_VERSION,
        timeout: float = 8.0,
    ):
        self.repo = repo
        self.current_version = current_version
        self.timeout = timeout

    def _fetch_latest_release(self) -> dict:
        url = f"https://api.github.com/repos/{self.repo}/releases/latest"
        request = Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "DiandianMini-UpdateChecker",
            },
        )
        with urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def check(self) -> UpdateResult:
        try:
            data = self._fetch_latest_release()
        except HTTPError as exc:
            if exc.code == 404:  # repo has no published releases yet
                return UpdateResult(self.current_version, None, False, notes="暂无发布版本")
            return UpdateResult(
                self.current_version, None, False, error=f"检查更新失败：HTTP {exc.code}"
            )
        except Exception as exc:  # noqa: BLE001 - any network/parse failure is non-fatal
            return UpdateResult(self.current_version, None, False, error=f"检查更新失败：{exc}")

        latest = (data.get("tag_name") or "").strip()
        return UpdateResult(
            current_version=self.current_version,
            latest_version=latest or None,
            has_update=is_newer(latest, self.current_version),
            download_url=data.get("html_url"),
            notes=(data.get("body") or "")[:500],
        )
