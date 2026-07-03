from app.db.database import Database
from app.db.models import ReviewModel
from app.db.repositories import ReviewRepository
from app.utils.time_utils import now_iso


def _row(review_id: str, **overrides) -> ReviewModel:
    defaults = dict(
        platform="google_play",
        app_id="com.x",
        country="us",
        lang="en",
        review_id=review_id,
        content="hi",
        captured_at=now_iso(),
    )
    defaults.update(overrides)
    return ReviewModel(**defaults)


def test_list_by_app_returns_seeded_rows(tmp_path):
    database = Database(str(tmp_path / "rev.sqlite3"))
    database.create_all()
    repo = ReviewRepository()

    with database.session() as session:
        session.add_all(_row(f"r{i}") for i in range(5))
        session.commit()

    with database.session() as session:
        rows = repo.list_by_app(session, "com.x", limit=100)
    assert len(rows) == 5


def test_existing_review_ids_reports_only_stored_ids(tmp_path):
    database = Database(str(tmp_path / "rev-existing.sqlite3"))
    database.create_all()
    repo = ReviewRepository()

    with database.session() as session:
        session.add_all(_row(f"r{i}") for i in range(3))
        session.commit()

    with database.session() as session:
        found = repo.existing_review_ids(session, "com.x", ["r0", "r1", "missing"])
    assert found == {"r0", "r1"}
