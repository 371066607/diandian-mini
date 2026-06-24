from __future__ import annotations

import sys
from pathlib import Path

from bootstrap import user_data_dir

BASE_DIR = Path(__file__).resolve().parent.parent

# When packaged, keep DB + logs in a per-user data dir OUTSIDE the app bundle, so an
# update that replaces the app folder never wipes the user's data. In dev, use the
# project directory as before.
if getattr(sys, "frozen", False):
    DATA_DIR = Path(user_data_dir()) / "data"
else:
    DATA_DIR = BASE_DIR / "data"
LOG_DIR = DATA_DIR / "logs"
DEFAULT_DB_PATH = DATA_DIR / "catch_radar.sqlite3"


def ensure_runtime_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def resolve_database_path(database_path: str | None = None) -> Path:
    if not database_path:
        return DEFAULT_DB_PATH

    path = Path(database_path)
    if not path.is_absolute():
        path = BASE_DIR / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
