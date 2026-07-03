import csv

from app.db.database import Database
from app.db.models import AlertModel, AppSnapshotModel
from app.services.export_service import ExportService
from app.utils.normalize import bool_to_int, dump_json
from app.utils.time_utils import now_iso


def _make_db(tmp_path):
    database = Database(str(tmp_path / "export.sqlite3"))
    database.create_all()
    return database


def _seed_snapshots(database):
    # SnapshotRepository.save_detail was removed with the live-scrape write path;
    # construct the ORM rows directly (same fields it used to populate) instead.
    with database.session() as session:
        session.add(
            AppSnapshotModel(
                platform="google_play",
                app_id="com.wechat",
                country="cn",
                lang="zh",
                captured_at="2026-01-01T00:00:00",
                title="微信",
                rating=4.5,
                ratings_count=1000,
                reviews_count=200,
                installs="1B+",
                real_installs=1_200_000_000,
                version="8.0.0",
                price="免费",
                currency="USD",
                contains_ads=bool_to_int(False),
                content_rating="3+",
                updated="2026-01-01",
                released="2011-01-21",
                description="x" * 5000,
                summary="some summary",
                changelog="some changelog",
                screenshots_json=dump_json(["http://a/1.png", "http://a/2.png"]),
                raw_json=dump_json({"big": "y" * 5000}),
            )
        )
        session.add(
            AppSnapshotModel(
                platform="google_play",
                app_id="com.wechat",
                country="cn",
                lang="zh",
                captured_at="2026-02-01T00:00:00",
                title="微信",
                rating=4.6,
                ratings_count=1100,
                reviews_count=220,
                installs="1B+",
                real_installs=1_300_000_000,
                version="8.0.1",
                price="免费",
                currency="USD",
                contains_ads=bool_to_int(True),
                content_rating="3+",
                updated="2026-02-01",
                released="2011-01-21",
            )
        )


def test_export_app_snapshots_row_count_and_values(tmp_path):
    database = _make_db(tmp_path)
    _seed_snapshots(database)
    service = ExportService(database)
    dest = tmp_path / "snap.csv"

    written = service.export_app_snapshots("com.wechat", "cn", "zh", str(dest))

    assert written == 2
    text = dest.read_text(encoding="utf-8-sig")
    lines = [ln for ln in text.splitlines() if ln]
    assert len(lines) == 3  # header + 2 data rows

    with open(dest, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 2
    assert rows[0]["应用"] == "微信"
    assert rows[0]["评分"] == "4.5"
    assert rows[0]["真实安装"] == "1200000000"
    assert rows[0]["版本"] == "8.0.0"
    assert rows[0]["含广告"] == "0"
    assert rows[1]["含广告"] == "1"

    # Large-text columns must never appear in the export.
    headers = rows[0].keys()
    for banned in ("raw_json", "description", "summary", "changelog", "screenshots_json"):
        assert banned not in headers


def test_export_app_snapshots_utf8_bom_and_chinese(tmp_path):
    database = _make_db(tmp_path)
    _seed_snapshots(database)
    service = ExportService(database)
    dest = tmp_path / "snap.csv"

    service.export_app_snapshots("com.wechat", "cn", "zh", str(dest))

    with open(dest, "rb") as fh:
        assert fh.read(3) == b"\xef\xbb\xbf"  # UTF-8 BOM

    with open(dest, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["应用"] == "微信"


def test_export_app_snapshots_empty_returns_zero_header_only(tmp_path):
    database = _make_db(tmp_path)
    service = ExportService(database)
    dest = tmp_path / "empty.csv"

    written = service.export_app_snapshots("com.nonexistent", "us", "en", str(dest))

    assert written == 0
    lines = [ln for ln in dest.read_text(encoding="utf-8-sig").splitlines() if ln]
    assert len(lines) == 1  # header only


def test_export_app_snapshots_none_fields_become_empty(tmp_path):
    database = _make_db(tmp_path)
    with database.session() as session:
        # Only app_id/title set; rating/version/etc. left as None.
        session.add(
            AppSnapshotModel(
                platform="google_play",
                app_id="com.sparse",
                country="us",
                lang="en",
                captured_at=now_iso(),
                title="稀疏应用",
            )
        )
    service = ExportService(database)
    dest = tmp_path / "sparse.csv"

    service.export_app_snapshots("com.sparse", "us", "en", str(dest))

    with open(dest, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["应用"] == "稀疏应用"
    assert rows[0]["评分"] == ""
    assert rows[0]["版本"] == ""
    assert rows[0]["价格"] == ""


def test_export_app_alerts_filters_by_app_and_chinese_labels(tmp_path):
    database = _make_db(tmp_path)
    # AlertRepository.create was removed with the live-scrape write path (alerts are no
    # longer generated from fresh scrapes); construct the ORM rows directly instead.
    with database.session() as session:
        session.add(
            AlertModel(
                type="rating_drop",
                severity="high",
                message="评分从 4.6 降到 4.5",
                app_id="com.wechat",
                title="评分下降",
                payload_json=dump_json({"app_id": "com.wechat", "title": "评分下降"}),
                created_at=now_iso(),
            )
        )
        session.add(
            AlertModel(
                type="version_changed",
                severity="low",
                message="版本更新到 8.0.1",
                app_id="com.wechat",
                title="版本变化",
                payload_json=dump_json({"app_id": "com.wechat", "title": "版本变化"}),
                created_at=now_iso(),
            )
        )
        session.add(
            AlertModel(
                type="rating_drop",
                severity="high",
                message="别的应用告警",
                app_id="com.other",
                title="评分下降",
                payload_json=dump_json({"app_id": "com.other", "title": "评分下降"}),
                created_at=now_iso(),
            )
        )
    service = ExportService(database)
    dest = tmp_path / "alerts.csv"

    written = service.export_app_alerts("com.wechat", str(dest))

    assert written == 2
    with open(dest, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 2
    types = {r["类型"] for r in rows}
    assert types == {"评分下降", "版本变化"}
    severities = {r["级别"] for r in rows}
    assert severities == {"高", "低"}
    # The other app's alert must be excluded.
    assert all("别的应用" not in r["内容"] for r in rows)
