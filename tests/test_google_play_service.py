import pytest

from app.services.google_play_service import (
    _CHART_DEPENDENCY_UNAVAILABLE_MESSAGE,
    GooglePlayService,
    ServiceError,
    _FEATURE_RETIRED_MESSAGE,
)

pytestmark = pytest.mark.legacy


def test_search_raises_retired_feature_error():
    service = GooglePlayService()

    with pytest.raises(ServiceError) as exc_info:
        service.search("notes")

    assert str(exc_info.value) == _FEATURE_RETIRED_MESSAGE


def test_similar_raises_retired_feature_error():
    service = GooglePlayService()

    with pytest.raises(ServiceError) as exc_info:
        service.similar("com.example.demo")

    assert str(exc_info.value) == _FEATURE_RETIRED_MESSAGE


def test_chart_raises_retired_feature_error():
    service = GooglePlayService()

    with pytest.raises(ServiceError) as exc_info:
        service.chart("top_free")

    assert str(exc_info.value) == _FEATURE_RETIRED_MESSAGE


def test_list_analyze_without_gplay_scraper_raises_dependency_message_not_retired_message():
    """list_analyze() itself isn't retired — only its old fallback-to-chart() path was, when
    chart() became a stub. Falling through to chart()'s _FEATURE_RETIRED_MESSAGE would wrongly
    tell the user this feature is retired, when the real issue is the optional gplay_scraper
    dependency being unavailable."""
    service = GooglePlayService()
    service._gplay_scraper = None

    with pytest.raises(ServiceError) as exc_info:
        service.list_analyze("top_free")

    assert str(exc_info.value) == _CHART_DEPENDENCY_UNAVAILABLE_MESSAGE
    assert str(exc_info.value) != _FEATURE_RETIRED_MESSAGE
