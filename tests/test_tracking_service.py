import pytest

from app.db.database import Database
from app.schemas.app_schema import AppDetail, AppSummary
from app.services.alert_service import AlertService
from app.services.google_play_service import ServiceError
from app.services.keyword_service import KeywordService
from app.services.settings_service import SettingsService
from app.services.tracking_service import TrackingService


class SearchOnlyGooglePlayService:
    def search(self, keyword, country="us", lang="en", limit=50):
        return [
            AppSummary(app_id="com.telegram", title="Telegram"),
            AppSummary(app_id="com.whatsapp", title="WhatsApp"),
        ]


class DetailGooglePlayService:
    def app_detail(self, app_id, country="us", lang="en"):
        return AppDetail(
            app_id=app_id,
            title="WhatsApp",
            rating=4.4,
            ratings_count=100,
            reviews_count=10,
            installs="1M+",
            version="2.26.0",
        )


def test_sync_keyword_now_raises_retired_error(tmp_path):
    # The live-network keyword sync path was retired; sync_keyword_now is now an
    # unconditional raising stub. This guards against an accidental regression back
    # to silent success.
    database = Database(str(tmp_path / "tracking.sqlite3"))
    database.create_all()
    keyword_service = KeywordService(SearchOnlyGooglePlayService(), database=database)
    settings_service = SettingsService(database)
    settings_service.ensure_defaults()
    tracking_service = TrackingService(
        database=database,
        google_play_service=DetailGooglePlayService(),
        keyword_service=keyword_service,
        settings_service=settings_service,
    )

    tracking_service.add_keyword("messenger", "com.whatsapp", "us", "en")
    with pytest.raises(ServiceError):
        tracking_service.sync_keyword_now("messenger", "com.whatsapp", "us", "en")


def test_sync_app_now_raises_retired_error(tmp_path):
    # The live-network app sync path was retired; sync_app_now is now an unconditional
    # raising stub, regardless of what the underlying google_play_service would do.
    database = Database(str(tmp_path / "tracking-failure.sqlite3"))
    database.create_all()
    alert_service = AlertService(database)
    tracking_service = TrackingService(
        database=database,
        google_play_service=DetailGooglePlayService(),
        alert_service=alert_service,
    )

    with pytest.raises(ServiceError):
        tracking_service.sync_app_now("com.whatsapp", "us", "en")


def test_recent_alerts_filters_by_severity(tmp_path):
    from app.db.models import AlertModel
    from app.utils.time_utils import now_iso

    database = Database(str(tmp_path / "severity.sqlite3"))
    database.create_all()
    alert_service = AlertService(database)
    with database.session() as session:
        session.add_all(
            [
                AlertModel(
                    type="rating_drop",
                    severity="high",
                    message="高1",
                    app_id="com.a",
                    created_at=now_iso(),
                ),
                AlertModel(
                    type="ratings_growth",
                    severity="medium",
                    message="中1",
                    app_id="com.b",
                    created_at=now_iso(),
                ),
                AlertModel(
                    type="keyword_dropped",
                    severity="high",
                    message="高2",
                    app_id="com.c",
                    created_at=now_iso(),
                ),
            ]
        )

    assert len(alert_service.recent_alerts(limit=10)) == 3
    high = alert_service.recent_alerts(limit=10, severity="high")
    assert len(high) == 2
    assert all(a.severity == "high" for a in high)
    assert len(alert_service.recent_alerts(limit=10, severity="medium")) == 1


class _DetailService:
    def app_detail(self, app_id, country="us", lang="en"):
        return AppDetail(app_id=app_id, title="T" + app_id, rating=4.4, reviews_count=10)


def test_sync_all_apps_skips_every_item_since_sync_is_retired(tmp_path):
    # sync_app_now is now an unconditional raising stub, so sync_all_apps must
    # catch-and-skip every item and settle on a count of 0 (each failure logged,
    # none propagated) instead of crashing the whole batch.
    database = Database(str(tmp_path / "sync-all.sqlite3"))
    database.create_all()
    tracking_service = TrackingService(
        database=database,
        google_play_service=_DetailService(),
        alert_service=AlertService(database),
    )
    for app_id in ("com.a", "com.b", "com.c", "com.d", "com.e"):
        tracking_service.add_app(app_id, "us", "en")

    assert tracking_service.sync_all_apps() == 0


def test_is_sync_due_honors_cadence():
    from datetime import datetime, timedelta, timezone

    from app.utils.time_utils import is_sync_due

    now = datetime(2026, 6, 5, 9, 0, 0)

    def ago(**kw):
        return (now - timedelta(**kw)).isoformat(timespec="seconds")

    # never synced / unparseable -> always due (fail-open)
    assert is_sync_due(None, "daily", now)
    assert is_sync_due("not-a-date", "daily", now)
    # daily: due after ~a day, not within hours
    assert is_sync_due(ago(hours=25), "daily", now)
    assert not is_sync_due(ago(hours=2), "daily", now)
    # weekly: due after a week, not after a few days
    assert is_sync_due(ago(days=8), "weekly", now)
    assert not is_sync_due(ago(days=3), "weekly", now)
    # manual: never auto-due, no matter how stale
    assert not is_sync_due(None, "manual", now)
    assert not is_sync_due(ago(days=99), "manual", now)
    # unknown cadence falls back to daily
    assert is_sync_due(ago(hours=25), "bogus", now)
    # Remote API timestamps may be UTC-aware while the desktop compares with local
    # naive datetimes. That must not crash the dashboard / tracking page.
    assert is_sync_due("2026-06-04T08:00:00Z", "daily", now)
    assert not is_sync_due(
        "2026-06-05T08:00:00+00:00",
        "daily",
        datetime(2026, 6, 5, 9, 0, 0, tzinfo=timezone.utc),
    )


def test_due_only_sync_returns_zero_since_sync_is_retired(tmp_path):
    # Even when an app is due, sync_app_now always raises now, so both a due-only
    # pass and a forced pass settle on 0 — cadence no longer matters, nothing syncs.
    database = Database(str(tmp_path / "due-only.sqlite3"))
    database.create_all()
    tracking_service = TrackingService(
        database=database,
        google_play_service=_DetailService(),
        alert_service=AlertService(database),
    )
    tracking_service.add_app("com.daily", "us", "en", frequency="daily")

    assert tracking_service.sync_all_apps(due_only=True) == 0
    assert tracking_service.sync_all_apps(due_only=False) == 0


def test_manual_frequency_never_auto_syncs(tmp_path):
    database = Database(str(tmp_path / "manual-freq.sqlite3"))
    database.create_all()
    tracking_service = TrackingService(
        database=database,
        google_play_service=_DetailService(),
        alert_service=AlertService(database),
    )
    tracking_service.add_app("com.manual", "us", "en", frequency="manual")

    # Manual items are still skipped by the due-only scheduler regardless of retirement.
    assert tracking_service.sync_all_apps(due_only=True) == 0
    # A forced (manual "同步全部") run is attempted, but sync_app_now now always
    # raises, so it settles on 0 too instead of actually syncing.
    assert tracking_service.sync_all_apps(due_only=False) == 0


def _bulk_tracking_service(tmp_path, name="bulk.sqlite3"):
    database = Database(str(tmp_path / name))
    database.create_all()
    return TrackingService(
        database=database,
        google_play_service=DetailGooglePlayService(),
    )


def test_add_keywords_bulk_dedups_and_counts(tmp_path):
    service = _bulk_tracking_service(tmp_path, "kw-bulk.sqlite3")
    result = service.add_keywords_bulk(
        ["messenger", "chat", "messenger", " "], "com.whatsapp", "us", "en"
    )
    assert result["added"] == 2
    assert result["existing"] == 0
    assert result["total"] == 2
    kws = service.list_keywords()
    assert {k.keyword for k in kws} == {"messenger", "chat"}
    assert all(k.app_id == "com.whatsapp" for k in kws)


def test_add_keywords_bulk_counts_existing(tmp_path):
    service = _bulk_tracking_service(tmp_path, "kw-bulk-existing.sqlite3")
    service.add_keyword("messenger", "com.whatsapp", "us", "en")
    result = service.add_keywords_bulk(["messenger", "chat"], "com.whatsapp", "us", "en")
    assert result["added"] == 1
    assert result["existing"] == 1


def test_add_keywords_bulk_invalid_target_fails_batch(tmp_path):
    service = _bulk_tracking_service(tmp_path, "kw-bulk-invalid.sqlite3")
    result = service.add_keywords_bulk(["messenger"], "not a package", "us", "en")
    assert result["added"] == 0
    assert len(result["failed"]) == 1
    assert service.list_keywords() == []


def test_add_apps_bulk_dedups_and_strips(tmp_path):
    service = _bulk_tracking_service(tmp_path)
    result = service.add_apps_bulk(["com.a", "com.b", "com.a", " "], "us", "en", "daily")

    assert result["added"] == 2
    assert result["existing"] == 0
    assert result["failed"] == []
    assert result["total"] == 2

    apps = service.list_apps()
    assert len(apps) == 2
    assert {item.app_id for item in apps} == {"com.a", "com.b"}
    assert all(item.frequency == "daily" for item in apps)


def test_add_apps_bulk_counts_existing_and_reenables(tmp_path):
    service = _bulk_tracking_service(tmp_path, "bulk-existing.sqlite3")
    # Pre-create with a real title, then disable it.
    with service.database.session() as session:
        service.tracking_repository.add_app(session, "com.a", "Original", "us", "en", "weekly")
    original = service.list_apps()[0]
    created_at = original.created_at
    service.toggle_app("com.a", "us", "en")  # disable
    assert service.list_apps()[0].enabled == 0

    result = service.add_apps_bulk(["com.a", "com.b"], "us", "en", "daily")

    assert result["added"] == 1  # only com.b is new
    assert result["existing"] == 1  # com.a already tracked
    assert result["failed"] == []

    apps = {item.app_id: item for item in service.list_apps()}
    assert len(apps) == 2
    a = apps["com.a"]
    assert a.enabled == 1  # re-enabled
    assert a.title == "Original"  # title not overwritten by None
    assert a.created_at == created_at  # created_at preserved


def test_add_apps_bulk_partial_success_on_invalid_package(tmp_path):
    service = _bulk_tracking_service(tmp_path, "bulk-invalid.sqlite3")
    result = service.add_apps_bulk(["com.valid", "not a package"], "us", "en", "daily")

    assert result["added"] == 1
    assert result["total"] == 2
    assert len(result["failed"]) == 1
    failed = result["failed"][0]
    assert failed["app_id"] == "not a package"
    assert failed["reason"]

    apps = service.list_apps()
    assert {item.app_id for item in apps} == {"com.valid"}


def test_add_apps_bulk_uses_single_session(tmp_path):
    service = _bulk_tracking_service(tmp_path, "bulk-session.sqlite3")
    calls = {"count": 0}
    original = service.database.session

    def counting_session(*args, **kwargs):
        calls["count"] += 1
        return original(*args, **kwargs)

    service.database.session = counting_session
    try:
        service.add_apps_bulk(["com.a", "com.b", "com.c"], "us", "en", "daily")
    finally:
        service.database.session = original
    assert calls["count"] == 1


def test_set_app_tag_sets_and_clears(tmp_path):
    service = _bulk_tracking_service(tmp_path, "tag.sqlite3")
    service.add_app("com.game", "us", "en")

    assert service.set_app_tag("com.game", "us", "en", "游戏") == "游戏"
    row = next(item for item in service.list_apps() if item.app_id == "com.game")
    assert row.tag == "游戏"

    # Empty string normalizes to None (a real clear).
    assert service.set_app_tag("com.game", "us", "en", "") is None
    row = next(item for item in service.list_apps() if item.app_id == "com.game")
    assert row.tag is None


def test_set_app_tag_missing_app_returns_none(tmp_path):
    service = _bulk_tracking_service(tmp_path, "tag-missing.sqlite3")
    assert service.set_app_tag("com.nope", "us", "en", "x") is None


def test_migrate_adds_tag_column_to_legacy_table(tmp_path):
    import sqlite3

    from app.db.migrations import migrate

    db_path = tmp_path / "legacy.sqlite3"
    # Build a legacy tracked_apps table that predates the tag column.
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE tracked_apps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL DEFAULT 'google_play',
            app_id TEXT NOT NULL,
            title TEXT,
            country TEXT DEFAULT 'us',
            lang TEXT DEFAULT 'en',
            frequency TEXT DEFAULT 'daily',
            enabled INTEGER NOT NULL DEFAULT 1,
            last_synced_at TEXT,
            consecutive_failures INTEGER NOT NULL DEFAULT 0,
            last_failed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (platform, app_id, country, lang)
        )
        """
    )
    conn.execute(
        "INSERT INTO tracked_apps (platform, app_id, country, lang, frequency, "
        "enabled, consecutive_failures, created_at, updated_at) "
        "VALUES ('google_play', 'com.old', 'us', 'en', 'daily', 1, 0, 't', 't')"
    )
    conn.commit()
    cols = {row[1] for row in conn.execute("PRAGMA table_info(tracked_apps)")}
    assert "tag" not in cols
    conn.close()

    database = Database(str(db_path))
    migrate(database)

    # tag column now exists and the legacy row has a NULL tag.
    service = TrackingService(database=database, google_play_service=DetailGooglePlayService())
    row = next(item for item in service.list_apps() if item.app_id == "com.old")
    assert row.tag is None
    # set_app_tag works against the migrated table.
    assert service.set_app_tag("com.old", "us", "en", "旧") == "旧"
