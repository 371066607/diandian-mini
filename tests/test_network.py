import os

from app.utils.network import apply_proxy_env

_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")


def _clear_proxy_env():
    for key in _KEYS:
        os.environ.pop(key, None)


def test_apply_proxy_env_sets_all_keys():
    _clear_proxy_env()
    try:
        apply_proxy_env("http://127.0.0.1:7890")
        for key in _KEYS:
            assert os.environ[key] == "http://127.0.0.1:7890"
    finally:
        _clear_proxy_env()


def test_apply_proxy_env_empty_clears():
    try:
        for key in _KEYS:
            os.environ[key] = "http://stale:1"
        apply_proxy_env("")
        for key in _KEYS:
            assert key not in os.environ
    finally:
        _clear_proxy_env()


def test_apply_proxy_env_none_clears():
    try:
        for key in _KEYS:
            os.environ[key] = "http://stale:1"
        apply_proxy_env(None)
        for key in _KEYS:
            assert key not in os.environ
    finally:
        _clear_proxy_env()


def test_apply_proxy_env_strips_whitespace():
    _clear_proxy_env()
    try:
        apply_proxy_env("  http://proxy:8080  ")
        assert os.environ["HTTP_PROXY"] == "http://proxy:8080"
    finally:
        _clear_proxy_env()
