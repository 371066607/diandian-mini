from __future__ import annotations

import os
import urllib.request

_PROXY_ENV_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")


def urlopen_proxied(request, timeout: float, proxy: str | None = None):
    """``urlopen`` that can route a single request through an explicit ``proxy``.

    A fresh opener is built per call, so this is thread-safe — unlike
    ``install_opener``/env vars it lets concurrent threads each use a different proxy
    (the coverage scan leases one proxy per worker). With ``proxy=None`` the opener's
    default ``ProxyHandler`` still honours the ``HTTP(S)_PROXY`` env vars that
    ``apply_proxy_env`` sets, preserving the app-wide proxy for every other call site.
    """
    if proxy:
        handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
    else:
        handler = urllib.request.ProxyHandler()  # no-arg = read proxies from the env
    opener = urllib.request.build_opener(handler)
    return opener.open(request, timeout=timeout)


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
