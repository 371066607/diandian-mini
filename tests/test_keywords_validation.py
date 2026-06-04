import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from app.ui.pages.keywords_page import KeywordsPage


def test_looks_like_package_accepts_package_ids():
    assert KeywordsPage._looks_like_package("com.hotshotai")
    assert KeywordsPage._looks_like_package("com.example.app")
    assert KeywordsPage._looks_like_package("a.b")


def test_looks_like_package_rejects_display_names():
    # the exact bug source: a display name typed into the target field
    assert not KeywordsPage._looks_like_package("hotshot")
    assert not KeywordsPage._looks_like_package("hotshot AI")
    assert not KeywordsPage._looks_like_package("Hotshot AI: Photo Generator")
