from __future__ import annotations

from app.db.repositories import ReviewRepository


class ReviewService:
    def __init__(self, database, google_play_service):
        self.database = database
        self.google_play_service = google_play_service
        self.repository = ReviewRepository()

    def fetch(self, app_id: str, country: str, lang: str, sort: str, limit: int):
        return self.google_play_service.reviews(
            app_id,
            country=country,
            lang=lang,
            sort=sort,
            limit=limit,
        )

    def save(self, app_id: str, country: str, lang: str, items):
        with self.database.session() as session:
            return self.repository.save_reviews(session, app_id, country, lang, items)

    def list_cached(self, app_id: str, limit: int = 100):
        with self.database.session() as session:
            return self.repository.list_by_app(session, app_id, limit=limit)
