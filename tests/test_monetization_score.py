from app.schemas.app_schema import AppDetail
from app.services.monetization_service import MonetizationService


def test_score_clamped_and_level():
    service = MonetizationService()
    detail = AppDetail(
        app_id="com.demo",
        title="Demo",
        free=False,
        has_iap=True,
        min_installs=150_000_000,
        rating=4.8,
        ratings_count=2_000_000,
    )
    result = service.score(detail, grossing_rank=5, review_growth_rate=0.2)
    assert result["score"] == 100
    assert result["level"] == "very_high"
