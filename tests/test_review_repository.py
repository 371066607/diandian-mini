import concurrent.futures as cf

from app.db.database import Database
from app.db.repositories import ReviewRepository
from app.schemas.review_schema import ReviewItem


def _items(n):
    return [ReviewItem(app_id="com.x", review_id=f"r{i}", content="hi") for i in range(n)]


def test_save_reviews_dedups_on_repeat(tmp_path):
    database = Database(str(tmp_path / "rev.sqlite3"))
    database.create_all()
    repo = ReviewRepository()

    with database.session() as session:
        assert repo.save_reviews(session, "com.x", "us", "en", _items(5)) == 5
    # re-saving the same reviews inserts nothing new
    with database.session() as session:
        assert repo.save_reviews(session, "com.x", "us", "en", _items(5)) == 0

    with database.session() as session:
        rows = repo.list_by_app(session, "com.x", limit=100)
    assert len(rows) == 5


def test_concurrent_save_reviews_is_race_safe(tmp_path):
    database = Database(str(tmp_path / "rev-race.sqlite3"))
    database.create_all()
    repo = ReviewRepository()
    items = _items(20)
    errors = []

    def save(_):
        try:
            with database.session() as session:
                repo.save_reviews(session, "com.x", "us", "en", items)
        except Exception as exc:
            errors.append(repr(exc))

    with cf.ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(save, range(40)))

    assert errors == []
    with database.session() as session:
        rows = repo.list_by_app(session, "com.x", limit=1000)
    # exactly the 20 distinct reviews — no duplicates, no crash under concurrency
    assert len(rows) == 20
