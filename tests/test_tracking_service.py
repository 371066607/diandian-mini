import pytest

from app.db.database import Database
from app.schemas.app_schema import AppDetail, AppSummary
from app.services.alert_service import AlertService
from app.services.keyword_service import KeywordService
from app.services.settings_service import SettingsService
from app.services.tracking_service import TrackingService


class SearchOnlyGooglePlayService:
    def search(self, keyword, country="us", lang="en", limit=50):
        return [
            AppSummary(app_id="com.telegram", title="Telegram"),
            AppSummary(app_id="com.whatsapp", title="WhatsApp"),
        ]


class FailingGooglePlayService:
    def app_detail(self, app_id, country="us", lang="en"):
        raise RuntimeError("store unavailable")


class DetailGooglePlayService:
    def app_detail(self, app_id, country="us", lang="en"):
        return AppDetail(
            app_id=app_id,
            title="WhatsApp",
            rating=4.4,
            ratings_count=100,
            reviews_count=10,
            installs="1M+",
            version="2.26.0",
        )


def test_sync_keyword_now_persists_history_and_sync_time(tmp_path):
    database = Database(str(tmp_path / "tracking.sqlite3"))
    database.create_all()
    keyword_service = KeywordService(SearchOnlyGooglePlayService(), database=database)
    settings_service = SettingsService(database)
    settings_service.ensure_defaults()
    tracking_service = TrackingService(
        database=database,
        google_play_service=DetailGooglePlayService(),
        keyword_service=keyword_service,
        settings_service=settings_service,
    )

    tracking_service.add_keyword("messenger", "com.whatsapp", "us", "en")
    result = tracking_service.sync_keyword_now("messenger", "com.whatsapp", "us", "en")
    tracked_keywords = tracking_service.list_keywords()
    history = keyword_service.history("messenger", "com.whatsapp", "us", "en")

    assert result.rank == 2
    assert tracked_keywords[0].last_synced_at is not None
    assert len(history) == 1
    assert history[0].rank == 2


def test_sync_app_now_records_fetch_failure_alert(tmp_path):
    database = Database(str(tmp_path / "tracking-failure.sqlite3"))
    database.create_all()
    alert_service = AlertService(database)
    tracking_service = TrackingService(
        database=database,
        google_play_service=FailingGooglePlayService(),
        alert_service=alert_service,
    )

    with pytest.raises(RuntimeError):
        tracking_service.sync_app_now("com.whatsapp", "us", "en")

    alerts = alert_service.recent_alerts(limit=5)
    assert len(alerts) == 1
    assert alerts[0].type == "fetch_failed"
    assert "store unavailable" in alerts[0].message


class FailingKeywordService:
    def rank(self, keyword, app_id, country="us", lang="en", limit=100):
        raise RuntimeError("search blocked")


def test_sync_keyword_now_records_fetch_failure_alert(tmp_path):
    database = Database(str(tmp_path / "kw-failure.sqlite3"))
    database.create_all()
    alert_service = AlertService(database)
    tracking_service = TrackingService(
        database=database,
        google_play_service=DetailGooglePlayService(),
        keyword_service=FailingKeywordService(),
        alert_service=alert_service,
    )

    with pytest.raises(RuntimeError):
        tracking_service.sync_keyword_now("messenger", "com.whatsapp", "us", "en")

    alerts = alert_service.recent_alerts(limit=5)
    assert len(alerts) == 1
    assert alerts[0].type == "fetch_failed"
    assert "search blocked" in alerts[0].message
    assert "messenger" in alerts[0].message
