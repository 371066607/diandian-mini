from __future__ import annotations

import os

_PROXY_ENV_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")


def apply_proxy_env(proxy: str | None) -> None:
    """Apply (or clear) the HTTP/HTTPS proxy for every network path in the app.

    Both code paths used here honour the environment: urllib's default opener reads
    proxies via ``getproxies()`` and curl honours ``http_proxy`` / ``https_proxy``.
    Setting these covers the scraper and the image loader without threading a proxy
    argument through each call site. An empty value clears the app-managed proxy.
    """
    proxy = (proxy or "").strip()
    for key in _PROXY_ENV_KEYS:
        if proxy:
            os.environ[key] = proxy
        else:
            os.environ.pop(key, None)
