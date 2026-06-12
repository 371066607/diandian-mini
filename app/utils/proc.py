"""Subprocess helpers that keep child console windows hidden on Windows.

The GUI is packaged with ``console=False`` (the app has no console of its own).
When such a process spawns a *console* program — our ``curl`` scraping/image
fallbacks, the ``git`` update checks — Windows pops a black console window for
the child every time. Passing ``CREATE_NO_WINDOW`` suppresses it. The flag only
exists on Windows, so it degrades to ``0`` (a no-op) on macOS/Linux.

Always launch child processes through ``proc.run`` / ``proc.popen`` instead of
``subprocess.*`` so no call site can forget the flag and flash a window.
"""

from __future__ import annotations

import subprocess
import sys

# Referencing the attribute is guarded — it does not exist off Windows.
CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def run(*args, **kwargs):
    """``subprocess.run`` that never flashes a console window on Windows."""
    kwargs["creationflags"] = kwargs.get("creationflags", 0) | CREATE_NO_WINDOW
    return subprocess.run(*args, **kwargs)


def popen(*args, **kwargs):
    """``subprocess.Popen`` that never flashes a console window on Windows."""
    kwargs["creationflags"] = kwargs.get("creationflags", 0) | CREATE_NO_WINDOW
    return subprocess.Popen(*args, **kwargs)
