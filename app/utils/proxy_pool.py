"""A small thread-safe rotating pool of HTTP proxies for the coverage scan.

The keyword-coverage scan fires up to ~120 independent store searches. Running them
concurrently from a single IP just multiplies the rate-limit/ban risk (see
KeywordCoverageService) — the only way to go faster *and* safer is to spread the
requests across many IPs. This pool hands out one proxy per request and tracks each
proxy's health so dead free/public proxies are taken out of rotation on the fly.

Health model: a proxy that fails ``max_failures`` times in a row is put on a cooldown
for ``cooldown_seconds`` (and skipped by ``lease``); a success resets it. ``lease`` is
round-robin over the currently-healthy proxies. The pool never blocks — when every
proxy is cooling down it returns ``None`` and the caller falls back (retry later / use
the direct connection / abort), rather than waiting.
"""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path

# Accept a bare ``host:port`` (assume http) as well as a full ``scheme://...`` URL.
_SPLIT = re.compile(r"[\s,]+")


def parse_proxies(text: str) -> list[str]:
    """Parse a blob into proxy URLs, de-duplicated, order preserved.

    Tolerant of how people actually paste lists: one per line and/or comma/space
    separated, with full-line or trailing ``#`` comments. A bare ``host:port`` gets an
    ``http://`` scheme."""
    out: list[str] = []
    seen: set[str] = set()
    for line in (text or "").splitlines():
        line = line.split("#", 1)[0]  # drop a full-line or trailing comment
        for raw in _SPLIT.split(line):
            token = raw.strip()
            if not token:
                continue
            if "://" not in token:
                token = "http://" + token
            if token not in seen:
                seen.add(token)
                out.append(token)
    return out


def load_proxies(settings_service=None, data_dir=None) -> list[str]:
    """Gather coverage proxies from the ``coverage_proxies`` setting and an optional
    ``<data_dir>/proxies.txt`` file (so a user can just drop a list in without any UI).
    Both sources are merged, de-duplicated, and best-effort — any read error yields no
    proxies rather than blocking a scan."""
    blobs: list[str] = []
    if settings_service is not None:
        try:
            blobs.append(settings_service.get("coverage_proxies", "") or "")
        except Exception:
            pass
    if data_dir is not None:
        try:
            path = Path(data_dir) / "proxies.txt"
            if path.exists():
                blobs.append(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            pass
    merged: list[str] = []
    seen: set[str] = set()
    for blob in blobs:
        for proxy in parse_proxies(blob):
            if proxy not in seen:
                seen.add(proxy)
                merged.append(proxy)
    return merged


class ProxyPool:
    def __init__(
        self,
        proxies,
        *,
        max_failures: int = 2,
        cooldown_seconds: float = 120.0,
        clock=time.monotonic,
    ) -> None:
        self._lock = threading.Lock()
        self._clock = clock
        self._max_failures = max(1, int(max_failures))
        self._cooldown = max(0.0, float(cooldown_seconds))
        self._entries: list[dict] = []
        seen: set[str] = set()
        for proxy in proxies or []:
            if proxy and proxy not in seen:
                seen.add(proxy)
                self._entries.append({"url": proxy, "failures": 0, "until": 0.0})
        self._cursor = 0

    def __len__(self) -> int:
        return len(self._entries)

    def has_proxies(self) -> bool:
        return bool(self._entries)

    def lease(self) -> str | None:
        """The next healthy proxy (round-robin), or ``None`` when the pool is empty or
        every proxy is currently cooling down."""
        with self._lock:
            count = len(self._entries)
            if count == 0:
                return None
            now = self._clock()
            for _ in range(count):
                entry = self._entries[self._cursor]
                self._cursor = (self._cursor + 1) % count
                if entry["until"] <= now:
                    return entry["url"]
            return None

    def report_ok(self, proxy: str) -> None:
        with self._lock:
            entry = self._find(proxy)
            if entry is not None:
                entry["failures"] = 0
                entry["until"] = 0.0

    def report_bad(self, proxy: str) -> None:
        with self._lock:
            entry = self._find(proxy)
            if entry is None:
                return
            entry["failures"] += 1
            if entry["failures"] >= self._max_failures:
                entry["until"] = self._clock() + self._cooldown
                entry["failures"] = 0

    def _find(self, proxy: str) -> dict | None:
        for entry in self._entries:
            if entry["url"] == proxy:
                return entry
        return None
