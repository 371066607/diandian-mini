from app.db.database import Database
from app.db.repositories import ChartRankRepository
from app.schemas.chart_rank_schema import ChartRankResult
from app.schemas.chart_schema import ChartItem
from app.services.chart_rank_service import ChartRankService


class FakeGooglePlayService:
    def list_analyze(self, collection, category=None, country="us", lang="en", limit=100):
        return [
            ChartItem(app_id="com.a", title="A", rank=1, chart_type=collection),
            ChartItem(app_id="com.b", title="B", rank=2, chart_type=collection),
            ChartItem(app_id="com.c", title="C", rank=3, chart_type=collection),
        ]


class FallbackGooglePlayService:
    """list_analyze blows up; chart() returns the list — exercises the fallback path."""

    def list_analyze(self, *a, **k):
        raise RuntimeError("library path unavailable")

    def chart(self, collection, category=None, country="us", lang="en", limit=100):
        return [
            ChartItem(app_id="com.a", title="A", rank=1, chart_type=collection),
            ChartItem(app_id="com.b", title="B", rank=2, chart_type=collection),
        ]


def test_chart_rank_found():
    service = ChartRankService(FakeGooglePlayService())
    result = service.rank("com.b", "top_free", "APPLICATION")
    assert result.found is True
    assert result.rank == 2


def test_chart_rank_not_found():
    service = ChartRankService(FakeGooglePlayService())
    result = service.rank("com.z", "top_free", "APPLICATION")
    assert result.found is False
    assert result.rank is None


def test_chart_rank_uses_chart_fallback():
    service = ChartRankService(FallbackGooglePlayService())
    result = service.rank("com.b", "top_free", "APPLICATION")
    assert result.found is True
    assert result.rank == 2


def test_chart_save_result_roundtrip_dedups_per_day(tmp_path):
    database = Database(str(tmp_path / "chart.sqlite3"))
    database.create_all()
    service = ChartRankService(FakeGooglePlayService(), database=database)

    result = service.rank("com.b", "top_free", "APPLICATION")  # persists once today
    service.save_result(result)  # same calendar day -> updates, no new row
    history = service.history("com.b", "top_free", "APPLICATION", "us", "en")

    assert len(history) == 1
    assert history[-1].rank == 2


def test_chart_latest_returns_most_recent_rank(tmp_path):
    database = Database(str(tmp_path / "latest.sqlite3"))
    database.create_all()
    repo = ChartRankRepository()

    def _result(rank, captured_at):
        return ChartRankResult(
            app_id="com.whatsapp",
            collection="top_free",
            category="APPLICATION",
            country="us",
            lang="en",
            found=True,
            rank=rank,
            checked_limit=100,
            captured_at=captured_at,
        )

    with database.session() as session:
        repo.upsert_for_day(session, _result(10, "2026-06-01T09:00:00"), now="2026-06-01T09:00:00")
        repo.upsert_for_day(session, _result(3, "2026-06-03T09:00:00"), now="2026-06-03T09:00:00")

    with database.session() as session:
        latest = repo.latest(session, "com.whatsapp", "top_free", "APPLICATION", "us", "en")
    assert latest is not None
    assert latest.rank == 3


def test_chart_latest_rank_is_none_when_never_synced(tmp_path):
    database = Database(str(tmp_path / "none.sqlite3"))
    database.create_all()
    service = ChartRankService(FakeGooglePlayService(), database=database)
    assert service.latest_rank("com.x", "top_free", "APPLICATION", "us", "en") is None
