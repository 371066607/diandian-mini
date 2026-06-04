"""Launcher helpers: per-user data dir, code versioning, and hot-patch loading.

Mirrors the approach of the referenced desktop project: the packaged app keeps its
data OUTSIDE the bundle (so an update that replaces the app never wipes the user's
DB/settings), and a downloaded code patch in the user dir is loaded ahead of the
bundled code so updates are a few-KB code download instead of a full re-bundle.

Pure stdlib only and imported FIRST by main.py — before any ``app.*`` import — so the
override path is on ``sys.path`` before application modules are resolved.
"""

from __future__ import annotations

import datetime as _dt
import os
import sys

APP_DIR_NAME = "DiandianMini"


def user_data_dir() -> str:
    """Per-user data directory outside the app bundle."""
    if sys.platform == "darwin":
        base = os.path.expanduser(f"~/Library/Application Support/{APP_DIR_NAME}")
    elif sys.platform == "win32":
        base = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), APP_DIR_NAME)
    else:
        base = os.path.expanduser("~/.diandian_mini")
    return base


def code_override_dir() -> str:
    """Where a downloaded hot-patch is extracted (takes import precedence)."""
    return os.path.join(user_data_dir(), "app_override")


def read_code_version(directory: str | None) -> int:
    """Read the integer commit-timestamp version from ``<dir>/code_version.txt``."""
    try:
        with open(os.path.join(directory or "", "code_version.txt"), encoding="utf-8") as fh:
            return int((fh.read() or "0").strip() or 0)
    except Exception:
        return 0


def bundled_code_version() -> int:
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return read_code_version(base)


def effective_code_version() -> int:
    """Currently effective version = max(bundled, downloaded patch)."""
    return max(bundled_code_version(), read_code_version(code_override_dir()))


def version_to_date(version: int) -> str:
    """Render a commit-timestamp version as ``YYYY.MM.DD.HHMM`` (or 开发版 for 0)."""
    if not version:
        return "开发版"
    try:
        return _dt.datetime.fromtimestamp(int(version)).strftime("%Y.%m.%d.%H%M")
    except Exception:
        return str(version)


def apply_code_override() -> None:
    """In a packaged build, load a newer downloaded code patch ahead of the bundle."""
    if not getattr(sys, "frozen", False):
        return
    override = code_override_dir()
    try:
        if os.path.isdir(override) and read_code_version(override) > bundled_code_version():
            sys.path.insert(0, override)
    except Exception:
        pass
