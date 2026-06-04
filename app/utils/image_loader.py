from __future__ import annotations

import math
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen

from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtCore import Qt


def placeholder_pixmap(text: str, width: int = 96, height: int = 96) -> QPixmap:
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor("#DDEAFE"))
    painter = QPainter(pixmap)
    painter.setPen(QColor("#2563EB"))
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, text[:8].upper())
    painter.end()
    return pixmap


def fetch_image_bytes(url: str | None, timeout: float = 15.0) -> bytes | None:
    if not url:
        return None
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
            completed = subprocess.run(
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

    Fetching icons one-by-one cost up to 12×(timeout) sequentially; even the earlier
    6-worker version needed two waves for a 12-icon grid. Here every URL gets its own
    worker (capped) so a full grid is one round-trip deep. ``thumbnail_size`` requests
    smaller images from the CDN. Result[i] corresponds to urls[i] (None on failure).
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
