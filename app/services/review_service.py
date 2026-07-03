from __future__ import annotations

from app.db.repositories import ReviewRepository
from app.services.google_play_service import ServiceError, _FEATURE_RETIRED_MESSAGE


class ReviewService:
    def __init__(self, database, google_play_service):
        self.database = database
        self.google_play_service = google_play_service
        self.repository = ReviewRepository()

    def fetch(self, app_id: str, country: str, lang: str, sort: str, continuation_token=None):
        return self.google_play_service.reviews(
            app_id,
            country=country,
            lang=lang,
            sort=sort,
            continuation_token=continuation_token,
        )

    def save(self, app_id: str, country: str, lang: str, items):
        raise ServiceError(_FEATURE_RETIRED_MESSAGE)

    def list_cached(self, app_id: str, limit: int = 100):
        with self.database.session() as session:
            return self.repository.list_by_app(session, app_id, limit=limit)

    def monitor_reviews(
        self,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 50,
        max_rating: int = 2,
    ):
        """Retired: this feature depended on the scrape-persist flow, which has been
        removed. Always raises ``ServiceError``."""
        raise ServiceError(_FEATURE_RETIRED_MESSAGE)
