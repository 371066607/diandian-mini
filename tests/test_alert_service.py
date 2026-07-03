from app.db.database import Database
from app.db.models import AlertModel
from app.services.alert_service import AlertService
from app.utils.time_utils import now_iso


def test_mark_all_read_clears_unread_count(tmp_path):
    database = Database(str(tmp_path / "alerts-read.sqlite3"))
    database.create_all()
    service = AlertService(database)

    with database.session() as session:
        session.add(
            AlertModel(
                type="rating_drop",
                severity="high",
                app_id="com.x",
                title="X",
                message="msg1",
                is_read=0,
                created_at=now_iso(),
            )
        )
        session.add(
            AlertModel(
                type="version_changed",
                severity="medium",
                app_id="com.x",
                title="X",
                message="msg2",
                is_read=0,
                created_at=now_iso(),
            )
        )

    assert service.unread_count() == 2

    affected = service.mark_all_read()
    assert affected == 2
    assert service.unread_count() == 0

    # idempotent: nothing left to mark
    assert service.mark_all_read() == 0
