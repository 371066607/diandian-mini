import pytest

from app.db.database import Database
from app.db.models import KeywordRankModel
from app.db.repositories import KeywordRankRepository
from app.schemas.app_schema import AppSummary
from app.schemas.keyword_schema import KeywordRankResult
from app.services.google_play_service import ServiceError
from app.services.keyword_service import KeywordService


class FakeGooglePlayService:
    def search(self, keyword, country="us", lang="en", limit=50):
        return [
            AppSummary(app_id="com.a", title="A"),
            AppSummary(app_id="com.b", title="B"),
            AppSummary(app_id="com.c", title="C"),
        ]


def test_keyword_rank_found():
    service = KeywordService(FakeGooglePlayService())
    result = service.rank("vpn", "com.b")
    assert result.found is True
    assert result.rank == 2


def test_keyword_rank_not_found():
    service = KeywordService(FakeGooglePlayService())
    result = service.rank("vpn", "com.z")
    assert result.found is False
    assert result.rank is None


def test_keyword_rank_matches_app_id_case_insensitively():
    """Regression: rank() used exact ==, so real mixed-case package ids (e.g. com.Slack)
    never matched a lowercase query while the coverage page said they ranked."""

    class MixedCaseService:
        def search(self, keyword, country="us", lang="en", limit=50):
            return [
                AppSummary(app_id="com.other", title="O"),
                AppSummary(app_id="com.Slack", title="Slack"),
            ]

    result = KeywordService(MixedCaseService()).rank("chat", "com.slack")
    assert result.found is True
    assert result.rank == 2


def test_keyword_save_result_raises_when_retired(tmp_path):
    """save_result() is a retired-feature stub now (live scraper write path removed);
    calling it must always raise ServiceError instead of persisting a row."""
    database = Database(str(tmp_path / "keyword.sqlite3"))
    database.create_all()
    service = KeywordService(FakeGooglePlayService(), database=database)

    result = KeywordRankResult(
        keyword="vpn",
        app_id="com.b",
        country="us",
        lang="en",
        found=True,
        rank=2,
        checked_limit=100,
        captured_at="2026-06-01T09:00:00",
    )

    with pytest.raises(ServiceError):
        service.save_result(result)


def test_keyword_latest_returns_most_recent_rank(tmp_path):
    database = Database(str(tmp_path / "latest.sqlite3"))
    database.create_all()
    repo = KeywordRankRepository()

    def _row(rank, captured_at):
        return KeywordRankModel(
            platform="google_play",
            keyword="messenger",
            app_id="com.whatsapp",
            country="us",
            lang="en",
            found=True,
            rank=rank,
            checked_limit=50,
            captured_at=captured_at,
        )

    with database.session() as session:
        session.add(_row(10, "2026-06-01T09:00:00"))
        session.add(_row(3, "2026-06-03T09:00:00"))

    with database.session() as session:
        latest = repo.latest(session, "messenger", "com.whatsapp", "us", "en")
    assert latest is not None
    assert latest.rank == 3


def test_keyword_latest_rank_is_none_when_never_synced(tmp_path):
    database = Database(str(tmp_path / "none.sqlite3"))
    database.create_all()
    service = KeywordService(FakeGooglePlayService(), database=database)
    assert service.latest_rank("nope", "com.x", "us", "en") is None
