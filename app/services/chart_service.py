from __future__ import annotations

from app.db.repositories import ChartRepository


class ChartService:
    def __init__(self, database, google_play_service, app_store_service=None):
        self.database = database
        self.google_play_service = google_play_service
        self.app_store_service = app_store_service
        self.repository = ChartRepository()

    def fetch(
        self,
        chart_type: str,
        category: str | None,
        country: str,
        lang: str,
        limit: int,
        platform: str = "google_play",
    ):
        if platform == "app_store" and self.app_store_service is not None:
            return self.app_store_service.chart(
                chart_type=chart_type,
                category=category,
                country=country,
                lang=lang,
                limit=limit,
            )
        return self.google_play_service.list_analyze(
            chart_type=chart_type,
            category=category,
            country=country,
            lang=lang,
            limit=limit,
        )

    def save(self, chart_type: str, category: str | None, country: str, lang: str, items):
        with self.database.session() as session:
            return self.repository.save_snapshot(
                session,
                chart_type,
                category,
                country,
                lang,
                items,
            )
