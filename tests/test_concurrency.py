import concurrent.futures as cf

from app.db.database import Database
from app.db.repositories import TrackingRepository


def test_concurrent_add_app_is_race_safe(tmp_path):
    database = Database(str(tmp_path / "race.sqlite3"))
    database.create_all()
    repo = TrackingRepository()
    errors = []

    def add(_):
        try:
            with database.session() as session:
                repo.add_app(session, "com.whatsapp", "WhatsApp", "us", "en")
        except Exception as exc:
            errors.append(repr(exc))

    with cf.ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(add, range(100)))

    assert errors == []
    with database.session() as session:
        apps = repo.list_apps(session)
    assert len([a for a in apps if a.app_id == "com.whatsapp"]) == 1


def test_concurrent_add_keyword_is_race_safe(tmp_path):
    database = Database(str(tmp_path / "race-kw.sqlite3"))
    database.create_all()
    repo = TrackingRepository()
    errors = []

    def add(_):
        try:
            with database.session() as session:
                repo.add_keyword(session, "vpn", "com.whatsapp", "us", "en")
        except Exception as exc:
            errors.append(repr(exc))

    with cf.ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(add, range(100)))

    assert errors == []
    with database.session() as session:
        keywords = repo.list_keywords(session)
    assert len(keywords) == 1


def test_add_app_upsert_is_idempotent_and_preserves_fields(tmp_path):
    database = Database(str(tmp_path / "idem.sqlite3"))
    database.create_all()
    repo = TrackingRepository()

    with database.session() as session:
        repo.add_app(session, "com.x", "X", "us", "en")
    with database.session() as session:
        repo.set_app_enabled(session, "com.x", "us", "en", False)
    with database.session() as session:
        repo.add_app(session, "com.x", None, "us", "en")  # re-add with no title

    with database.session() as session:
        apps = repo.list_apps(session)
    assert len(apps) == 1
    assert bool(apps[0].enabled) is True  # re-adding re-enables
    assert apps[0].title == "X"  # existing title preserved when new title is None
