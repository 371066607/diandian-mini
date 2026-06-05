from app.db.database import Database
from app.db.models import AppSnapshotModel
from app.db.repositories import AlertRepository
from app.schemas.app_schema import AppDetail
from app.services.alert_service import AlertService


def test_create_snapshot_alerts_emits_expected_rules(tmp_path):
    database = Database(str(tmp_path / "alerts.sqlite3"))
    database.create_all()
    service = AlertService(database)
    repository = AlertRepository()

    previous = AppSnapshotModel(
        platform="google_play",
        app_id="com.whatsapp",
        country="us",
        lang="en",
        captured_at="2026-06-03T09:00:00",
        title="WhatsApp",
        rating=4.6,
        ratings_count=100,
        reviews_count=100,
        installs="1M+",
        min_installs=1_000_000,
        version="2.25.0",
    )
    current = AppDetail(
        app_id="com.whatsapp",
        title="WhatsApp",
        rating=4.3,
        ratings_count=120,
        reviews_count=115,
        installs="5M+",
        version="2.26.0",
    )

    with database.session() as session:
        created = service.create_snapshot_alerts(session, previous, current)

    with database.session() as session:
        alerts = repository.list_recent(session, limit=10)

    assert len(created) == 5
    assert {item.type for item in alerts} == {
        "rating_drop",
        "ratings_growth",
        "reviews_growth",
        "version_changed",
        "install_band_changed",
    }


def test_mark_all_read_clears_unread_count(tmp_path):
    database = Database(str(tmp_path / "alerts-read.sqlite3"))
    database.create_all()
    service = AlertService(database)
    repository = AlertRepository()

    with database.session() as session:
        repository.create(session, "rating_drop", "high", "msg1", app_id="com.x", title="X")
        repository.create(session, "version_changed", "medium", "msg2", app_id="com.x", title="X")

    assert service.unread_count() == 2

    affected = service.mark_all_read()
    assert affected == 2
    assert service.unread_count() == 0

    # idempotent: nothing left to mark
    assert service.mark_all_read() == 0
