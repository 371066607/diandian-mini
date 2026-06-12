from __future__ import annotations

import math
import re
import shutil
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap

from app.utils import proc

# Bounded in-memory cache so the same icon/screenshot isn't re-downloaded every time
# a list is shown — capped by total bytes AND entry count (LRU eviction) so it can't
# grow without limit.
IMAGE_CACHE_MAX_BYTES = 48 * 1024 * 1024  # 48 MB
IMAGE_CACHE_MAX_ENTRIES = 1500


class _ImageCache:
    """Thread-safe LRU byte-budget cache (fetch_images runs concurrent workers)."""

    def __init__(self, max_bytes: int, max_entries: int):
        self._store: OrderedDict[str, bytes] = OrderedDict()
        self._bytes = 0
        self._max_bytes = max_bytes
        self._max_entries = max_entries
        self._lock = threading.Lock()

    def get(self, key: str) -> bytes | None:
        with self._lock:
            data = self._store.get(key)
            if data is not None:
                self._store.move_to_end(key)  # most-recently-used
            return data

    def put(self, key: str, data: bytes) -> None:
        if not key or not data or len(data) > self._max_bytes:
            return
        with self._lock:
            if key in self._store:
                self._bytes -= len(self._store[key])
            self._store[key] = data
            self._store.move_to_end(key)
            self._bytes += len(data)
            while self._store and (
                self._bytes > self._max_bytes or len(self._store) > self._max_entries
            ):
                _, evicted = self._store.popitem(last=False)  # drop least-recently-used
                self._bytes -= len(evicted)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._bytes = 0

    def stats(self) -> tuple[int, int]:
        with self._lock:
            return len(self._store), self._bytes


_image_cache = _ImageCache(IMAGE_CACHE_MAX_BYTES, IMAGE_CACHE_MAX_ENTRIES)


def clear_image_cache() -> None:
    _image_cache.clear()


def image_cache_stats() -> tuple[int, int]:
    """(entry_count, total_bytes) currently held in the image cache."""
    return _image_cache.stats()


def placeholder_pixmap(text: str, width: int = 96, height: int = 96) -> QPixmap:
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor("#DDEAFE"))
    painter = QPainter(pixmap)
    painter.setPen(QColor("#2563EB"))
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, text[:8].upper())
    painter.end()
    return pixmap


def _download_image_bytes(url: str, timeout: float) -> bytes | None:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0 Safari/537.36"
            )
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read()
    except Exception:
        curl_path = shutil.which("curl")
        if not curl_path:
            return None
        try:
            completed = proc.run(
                [
                    curl_path,
                    "-fsSL",
                    "--max-time",
                    str(max(3, math.ceil(timeout))),
                    "-A",
                    (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0 Safari/537.36"
                    ),
                    url,
                ],
                check=True,
                capture_output=True,
            )
            return completed.stdout or None
        except Exception:
            return None


def fetch_image_bytes(
    url: str | None, timeout: float = 15.0, use_cache: bool = True
) -> bytes | None:
    if not url:
        return None
    if use_cache:
        cached = _image_cache.get(url)
        if cached is not None:
            return cached
    data = _download_image_bytes(url, timeout)
    if use_cache and data:
        _image_cache.put(url, data)
    return data


def thumbnail_url(url: str | None, size: int | None) -> str | None:
    """Rewrite a Google CDN image URL to request a server-side thumbnail.

    play/lh googleusercontent URLs accept an ``=s<px>`` suffix that makes the CDN
    resize before sending, cutting the payload (icons render at 36–96px, so there is
    no point downloading the full-resolution master). Non-Google URLs pass through.
    """
    if not url or size is None or "googleusercontent.com/" not in url:
        return url
    base = re.sub(r"=[a-z]\d+[-\w]*$", "", url)  # strip an existing =s512 / =w240-h480 spec
    return f"{base}=s{size}"


def fetch_images(
    urls: list[str | None],
    timeout: float = 6.0,
    max_workers: int = 12,
    thumbnail_size: int | None = None,
) -> list[bytes | None]:
    """Fetch many images concurrently in a single wave, preserving input order.

    Each URL gets its own worker (capped) so a full grid is one round-trip deep, and
    already-fetched images come straight from the bounded cache. ``thumbnail_size``
    requests smaller images from the CDN. Result[i] corresponds to urls[i].
    """
    urls = [thumbnail_url(u, thumbnail_size) for u in urls]
    if not urls:
        return []
    workers = min(max_workers, len(urls))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(lambda url: fetch_image_bytes(url, timeout=timeout), urls))


def pixmap_from_bytes(
    data: bytes | None,
    *,
    width: int = 96,
    height: int = 96,
    fallback_text: str = "IMG",
) -> QPixmap:
    if data:
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            return pixmap.scaled(
                width,
                height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
    return placeholder_pixmap(fallback_text, width=width, height=height)
