import pytest

from app.utils.identity import (
    APP_STORE,
    APP_STORE_LANG_SENTINEL,
    GOOGLE_PLAY,
    PLATFORMS,
    normalize_identity,
)


def test_google_play_lowercases_and_trims():
    assert normalize_identity(
        platform="google_play", app_id=" com.x ", country="US", lang="EN"
    ) == ("google_play", "com.x", "us", "en")


def test_app_store_forces_lang_sentinel():
    # 即便传入具体 lang，App Store 也强制成哨兵值，避免伪 locale 把同一 app 裂成两行。
    assert normalize_identity(
        platform="app_store", app_id="310633997", country="US", lang="ja"
    ) == ("app_store", "310633997", "us", APP_STORE_LANG_SENTINEL)
    assert APP_STORE_LANG_SENTINEL == "default"


def test_defaults_when_omitted():
    assert normalize_identity(platform=GOOGLE_PLAY, app_id="com.y") == (
        "google_play",
        "com.y",
        "us",
        "en",
    )


def test_blank_country_lang_fall_back():
    assert normalize_identity(platform=GOOGLE_PLAY, app_id="com.z", country="  ", lang="  ") == (
        "google_play",
        "com.z",
        "us",
        "en",
    )


def test_app_id_trimmed_but_not_resolved():
    # helper 不联网解析 bundleId→trackId，原样保留（仅 trim）。
    _, app_id, _, _ = normalize_identity(platform=APP_STORE, app_id="  com.bundle.id  ")
    assert app_id == "com.bundle.id"


def test_unknown_platform_raises():
    with pytest.raises(ValueError):
        normalize_identity(platform="amazon", app_id="com.x")


def test_empty_app_id_raises():
    with pytest.raises(ValueError):
        normalize_identity(platform=GOOGLE_PLAY, app_id="   ")


def test_must_be_keyword_only():
    with pytest.raises(TypeError):
        normalize_identity("google_play", "com.x")  # type: ignore[misc]


def test_platforms_constant():
    assert PLATFORMS == frozenset({GOOGLE_PLAY, APP_STORE})
