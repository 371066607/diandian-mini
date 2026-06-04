from app.db.database import Database
from app.db.repositories import SettingsRepository, SnapshotRepository
from app.schemas.app_schema import AppDetail


def test_settings_repository_roundtrip(tmp_path):
    database = Database(str(tmp_path / "test.sqlite3"))
    database.create_all()
    repository = SettingsRepository()

    with database.session() as session:
        repository.upsert(session, "default_country", "jp")

    with database.session() as session:
        values = repository.get_all(session)

    assert values["default_country"] == "jp"


def test_save_detail_persists_real_installs(tmp_path):
    database = Database(str(tmp_path / "snap.sqlite3"))
    database.create_all()
    repository = SnapshotRepository()
    detail = AppDetail(
        app_id="com.x",
        title="X",
        installs="10,000,000,000+",
        real_installs=12004145776,
    )

    with database.session() as session:
        repository.save_detail(session, detail, "us", "en")
    with database.session() as session:
        history = repository.get_history(session, "com.x", "us", "en")

    assert len(history) == 1
    assert history[0].real_installs == 12004145776
