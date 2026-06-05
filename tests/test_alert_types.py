from app.db.database import Database
from app.db.repositories import AlertRepository, SnapshotRepository
from app.schemas.app_schema import AppDetail
from app.services.alert_service import AlertService


def _setup(tmp_path, name):
    database = Database(str(tmp_path / f"{name}.sqlite3"))
    database.create_all()
    return database


def _save_and_read_previous(database, previous_detail):
    """Persist ``previous_detail`` as a snapshot, then read it back as the
    AppSnapshotModel that create_snapshot_alerts expects as previous_snapshot."""
    repo = SnapshotRepository()
    with database.session() as session:
        repo.save_detail(session, previous_detail, country="us", lang="en")
    with database.session() as session:
        return repo.latest(session, previous_detail.app_id, country="us", lang="en")


def _run(database, previous_snapshot, current):
    service = AlertService(database)
    with database.session() as session:
        service.create_snapshot_alerts(session, previous_snapshot, current)
    with database.session() as session:
        return AlertRepository().list_recent(session, limit=20)


def test_installs_milestone_crossed(tmp_path):
    database = _setup(tmp_path, "milestone")
    previous = AppDetail(app_id="com.x", title="X", real_installs=900_000)
    current = AppDetail(app_id="com.x", title="X", real_installs=6_000_000)
    previous_snapshot = _save_and_read_previous(database, previous)

    alerts = _run(database, previous_snapshot, current)
    milestone_alerts = [a for a in alerts if a.type == "installs_milestone"]
    assert len(milestone_alerts) == 1
    # highest crossed milestone is 5,000,000
    assert "5,000,000" in milestone_alerts[0].message
    assert milestone_alerts[0].severity == "medium"


def test_ads_changed_false_to_true(tmp_path):
    database = _setup(tmp_path, "ads")
    previous = AppDetail(app_id="com.x", title="X", contains_ads=False)
    current = AppDetail(app_id="com.x", title="X", contains_ads=True)
    previous_snapshot = _save_and_read_previous(database, previous)

    alerts = _run(database, previous_snapshot, current)
    ads_alerts = [a for a in alerts if a.type == "ads_changed"]
    assert len(ads_alerts) == 1
    assert ads_alerts[0].severity == "high"
    assert "无→有" in ads_alerts[0].message


def test_price_changed_sale_started(tmp_path):
    database = _setup(tmp_path, "sale")
    previous = AppDetail(app_id="com.x", title="X", sale=False, price="$4.99")
    current = AppDetail(app_id="com.x", title="X", sale=True, price="$2.99")
    previous_snapshot = _save_and_read_previous(database, previous)

    alerts = _run(database, previous_snapshot, current)
    price_alerts = [a for a in alerts if a.type == "price_changed"]
    # sale takes priority, at most one price_changed alert
    assert len(price_alerts) == 1
    assert price_alerts[0].severity == "medium"
    assert "开始促销" in price_alerts[0].message


def test_developer_email_changed(tmp_path):
    database = _setup(tmp_path, "email")
    previous = AppDetail(app_id="com.x", title="X", developer_email="old@dev.com")
    current = AppDetail(app_id="com.x", title="X", developer_email="new@dev.com")
    previous_snapshot = _save_and_read_previous(database, previous)

    alerts = _run(database, previous_snapshot, current)
    contact_alerts = [a for a in alerts if a.type == "developer_contact_changed"]
    assert len(contact_alerts) == 1
    assert contact_alerts[0].severity == "low"
    assert "old@dev.com" in contact_alerts[0].message
    assert "new@dev.com" in contact_alerts[0].message


def test_no_change_no_false_positives(tmp_path):
    database = _setup(tmp_path, "noop")
    detail = AppDetail(
        app_id="com.x",
        title="X",
        real_installs=6_000_000,
        contains_ads=True,
        sale=False,
        price="$4.99",
        developer_email="dev@dev.com",
        developer_website="https://dev.com",
        rating=4.5,
        ratings_count=100,
        reviews_count=100,
        version="1.0.0",
        installs="5M+",
    )
    previous_snapshot = _save_and_read_previous(database, detail)
    current = AppDetail(
        app_id="com.x",
        title="X",
        real_installs=6_000_000,
        contains_ads=True,
        sale=False,
        price="$4.99",
        developer_email="dev@dev.com",
        developer_website="https://dev.com",
        rating=4.5,
        ratings_count=100,
        reviews_count=100,
        version="1.0.0",
        installs="5M+",
    )

    alerts = _run(database, previous_snapshot, current)
    new_types = {"installs_milestone", "ads_changed", "price_changed", "developer_contact_changed"}
    assert not [a for a in alerts if a.type in new_types]


def test_negative_review_surge(tmp_path):
    database = _setup(tmp_path, "neg_surge")
    # prev: total 100, negative(1-2★)=10; curr: total 200, negative=60
    # -> 50 of the 100 new ratings are negative = 50% >= 20% threshold
    previous = AppDetail(app_id="com.x", title="X", histogram=[5, 5, 10, 30, 50])
    current = AppDetail(app_id="com.x", title="X", histogram=[30, 30, 20, 40, 80])
    prev_snap = _save_and_read_previous(database, previous)

    alerts = _run(database, prev_snap, current)
    surge = [a for a in alerts if a.type == "negative_review_surge"]
    assert len(surge) == 1
    assert surge[0].severity == "high"


def test_positive_ratio_drop_isolated(tmp_path):
    database = _setup(tmp_path, "pos_drop")
    # add 100 neutral (3★) ratings: positive share 70% -> 35% (drop 35pp), no negative surge
    previous = AppDetail(app_id="com.x", title="X", histogram=[10, 10, 10, 30, 40])
    current = AppDetail(app_id="com.x", title="X", histogram=[10, 10, 110, 30, 40])
    prev_snap = _save_and_read_previous(database, previous)

    alerts = _run(database, prev_snap, current)
    assert len([a for a in alerts if a.type == "positive_ratio_drop"]) == 1
    assert not [a for a in alerts if a.type == "negative_review_surge"]


def test_no_histogram_alert_when_below_threshold(tmp_path):
    database = _setup(tmp_path, "hist_below")
    # tiny shifts: 5 new ratings, 1 negative (20% exactly is >=, so use 0 negative); positive steady
    previous = AppDetail(app_id="com.x", title="X", histogram=[10, 10, 10, 30, 40])
    current = AppDetail(app_id="com.x", title="X", histogram=[10, 10, 15, 30, 40])  # +5 neutral
    prev_snap = _save_and_read_previous(database, previous)

    alerts = _run(database, prev_snap, current)
    # positive share 70% -> 66.7% = ~3.3pp drop, below 5pp; no negative new
    assert not [a for a in alerts if a.type in {"negative_review_surge", "positive_ratio_drop"}]


def test_no_histogram_alert_when_missing_or_malformed(tmp_path):
    database = _setup(tmp_path, "hist_missing")
    previous = AppDetail(app_id="com.x", title="X", histogram=[])  # empty -> skip
    current = AppDetail(app_id="com.x", title="X", histogram=[50, 50, 0, 0, 0])
    prev_snap = _save_and_read_previous(database, previous)

    alerts = _run(database, prev_snap, current)
    assert not [a for a in alerts if a.type in {"negative_review_surge", "positive_ratio_drop"}]
