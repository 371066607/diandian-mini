from __future__ import annotations

from app.db.repositories import ReviewRepository


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
        with self.database.session() as session:
            return self.repository.save_reviews(session, app_id, country, lang, items)

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
        """Fetch the newest reviews, persist them (dedup), and return the NEW low-star
        (``rating <= max_rating``) ones — the input to negative-review alerting. Reviews
        are an enhancement to the sync, so the caller treats any error here as non-fatal."""
        items, _token = self.fetch(app_id, country, lang, sort="newest")
        items = list(items)[:limit]
        if not items:
            return []
        with self.database.session() as session:
            existing = self.repository.existing_review_ids(
                session, app_id, [item.review_id for item in items]
            )
            self.repository.save_reviews(session, app_id, country, lang, items)
        return [
            item
            for item in items
            if item.review_id not in existing
            and item.rating is not None
            and item.rating <= max_rating
        ]
