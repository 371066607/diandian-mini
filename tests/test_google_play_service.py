import pytest

from app.services.google_play_service import (
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
