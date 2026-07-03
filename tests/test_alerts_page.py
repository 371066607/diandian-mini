from app.db.database import Database
from app.db.models import AlertModel
from app.db.repositories import AlertRepository
from app.services.alert_service import AlertService
from app.utils.normalize import dump_json
from app.utils.time_utils import now_iso


def _make_db(tmp_path):
    database = Database(str(tmp_path / "alerts.sqlite3"))
    database.create_all()
    return database


def _add_alert(session, alert_type, severity, message, **payload):
    """Construct an AlertModel directly (AlertRepository.create was retired
    along with the live-scrape write path it existed to serve)."""
    session.add(
        AlertModel(
            type=alert_type,
            severity=severity,
            message=message,
            payload_json=dump_json(payload),
            title=payload.get("title"),
            app_id=payload.get("app_id"),
            is_read=0,
            created_at=now_iso(),
        )
    )


def _seed(database):
    """Insert a fixed spread of alerts across app_id / type / severity / is_read."""
    repo = AlertRepository()
    with database.session() as session:
        _add_alert(session, "rating_drop", "high", "A 评分下降", app_id="com.a")
        _add_alert(session, "version_changed", "medium", "A 版本变化", app_id="com.a")
        _add_alert(session, "reviews_growth", "low", "B 评论增长", app_id="com.b")
        _add_alert(session, "fetch_failed", "high", "无 app 告警")  # app_id None
    # Mark the second-created alert (com.a / version_changed) read via its id.
    with database.session() as session:
        all_alerts = repo.list_filtered(session)
        version_alert = next(a for a in all_alerts if a.type == "version_changed")
        repo.mark_read_by_ids(session, [version_alert.id])
    return repo


def test_list_filtered_single_and_combined(tmp_path):
    database = _make_db(tmp_path)
    repo = _seed(database)
    with database.session() as session:
        # app_id filter
        assert {a.app_id for a in repo.list_filtered(session, app_id="com.a")} == {"com.a"}
        assert len(repo.list_filtered(session, app_id="com.a")) == 2

        # type filter
        types = [a.type for a in repo.list_filtered(session, alert_type="rating_drop")]
        assert types == ["rating_drop"]

        # severity filter
        highs = repo.list_filtered(session, severity="high")
        assert len(highs) == 2
        assert all(a.severity == "high" for a in highs)

        # combined: com.a + high
        combined = repo.list_filtered(session, app_id="com.a", severity="high")
        assert len(combined) == 1
        assert combined[0].type == "rating_drop"


def test_list_filtered_is_read_distinguishes_zero_from_none(tmp_path):
    database = _make_db(tmp_path)
    repo = _seed(database)
    with database.session() as session:
        # No filter -> all four.
        assert len(repo.list_filtered(session)) == 4
        # is_read=1 -> only the one marked read.
        read = repo.list_filtered(session, is_read=1)
        assert len(read) == 1
        assert read[0].type == "version_changed"
        # is_read=0 -> the other three (0 must NOT be treated as "no filter").
        unread = repo.list_filtered(session, is_read=0)
        assert len(unread) == 3
        assert all(a.is_read == 0 for a in unread)


def test_distinct_app_ids(tmp_path):
    database = _make_db(tmp_path)
    repo = _seed(database)
    with database.session() as session:
        # Two distinct non-null app_ids; the None-app alert is excluded.
        assert repo.distinct_app_ids(session) == ["com.a", "com.b"]


def test_mark_read_by_ids_lowers_unread_count(tmp_path):
    database = _make_db(tmp_path)
    repo = _seed(database)
    with database.session() as session:
        before = repo.unread_count(session)
        assert before == 3  # one already read in _seed
        target = repo.list_filtered(session, alert_type="rating_drop")[0]
        affected = repo.mark_read_by_ids(session, [target.id])
        assert affected == 1
    with database.session() as session:
        assert repo.unread_count(session) == 2
        reloaded = repo.list_filtered(session, alert_type="rating_drop")[0]
        assert reloaded.is_read == 1


def test_mark_read_by_ids_empty_is_noop(tmp_path):
    database = _make_db(tmp_path)
    _seed(database)
    repo = AlertRepository()
    with database.session() as session:
        assert repo.mark_read_by_ids(session, []) == 0


def test_alert_service_wrappers(tmp_path):
    database = _make_db(tmp_path)
    _seed(database)
    service = AlertService(database)

    # list_alerts wrapper, including the is_read=0 path.
    assert len(service.list_alerts()) == 4
    assert len(service.list_alerts(is_read=0)) == 3
    assert len(service.list_alerts(app_id="com.a")) == 2
    assert len(service.list_alerts(severity="high")) == 2

    # distinct_alert_apps wrapper.
    assert service.distinct_alert_apps() == ["com.a", "com.b"]

    # mark_read wrapper.
    target = service.list_alerts(alert_type="reviews_growth")[0]
    assert service.mark_read([target.id]) == 1
    assert len(service.list_alerts(is_read=0)) == 2
