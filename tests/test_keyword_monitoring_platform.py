from __future__ import annotations

from app.db.database import Database
from app.schemas.app_schema import AppSummary
from app.services.keyword_service import KeywordService
from app.services.settings_service import SettingsService
from app.services.tracking_service import TrackingService


class RecordingSearch:
    """A search backend that records which keywords it was asked for, so a test can tell
    the Google Play and App Store rank services apart by which one actually got called."""

    def __init__(self, results):
        self._results = results
        self.calls: list[str] = []

    def search(self, keyword, country="us", lang="en", limit=50):
        self.calls.append(keyword)
        return self._results


def _make(tmp_path):
    database = Database(str(tmp_path / "kw.sqlite3"))
    database.create_all()
    settings_service = SettingsService(database)
    settings_service.ensure_defaults()
    gp_backend = RecordingSearch([AppSummary(app_id="com.gp.app", title="GP App")])
    as_backend = RecordingSearch(
        [
            AppSummary(platform="app_store", app_id="000", title="Other"),
            AppSummary(platform="app_store", app_id="587366035", title="Picsart"),
        ]
    )
    tracking = TrackingService(
        database=database,
        google_play_service=None,
        keyword_service=KeywordService(gp_backend, database=database),
        keyword_service_app_store=KeywordService(
            as_backend, database=database, platform="app_store"
        ),
        settings_service=settings_service,
    )
    return tracking, gp_backend, as_backend


def test_app_store_keyword_syncs_via_itunes_backend(tmp_path):
    tracking, gp_backend, as_backend = _make(tmp_path)
    tracking.add_keyword("photo editor", "587366035", "us", "en", platform="app_store")

    result = tracking.sync_keyword_now(
        "photo editor", "587366035", "us", "en", platform="app_store"
    )

    # routed to the App Store backend, never touched Google Play
    assert as_backend.calls == ["photo editor"]
    assert gp_backend.calls == []
    assert result.platform == "app_store"
    assert result.found is True
    assert result.rank == 2  # Picsart sits at position 2 in the canned App Store results


def test_tracked_keyword_remembers_its_platform(tmp_path):
    tracking, _gp, _as = _make(tmp_path)
    tracking.add_keyword("vpn", "123456", "us", "en", platform="app_store")
    tracking.add_keyword("vpn", "com.gp.app", "us", "en")  # defaults to google_play

    rows = {(k.app_id, k.platform) for k in tracking.list_keywords()}
    assert ("123456", "app_store") in rows
    assert ("com.gp.app", "google_play") in rows


def test_sync_all_keywords_routes_each_platform(tmp_path):
    tracking, gp_backend, as_backend = _make(tmp_path)
    tracking.add_keyword("editor", "587366035", "us", "en", platform="app_store")
    tracking.add_keyword("editor", "com.gp.app", "us", "en")

    synced = tracking.sync_all_keywords()

    assert synced == 2
    assert gp_backend.calls == ["editor"]  # GP keyword -> GP backend
    assert as_backend.calls == ["editor"]  # App Store keyword -> iTunes backend


def test_same_tuple_on_both_platforms_keeps_separate_rows(tmp_path):
    """Regression: the same (keyword, app_id, country, lang) tracked on BOTH platforms
    must stay two independent monitors — platform-blind accessors used to raise
    MultipleResultsFound on sync and let same-day rank upserts overwrite each other."""
    tracking, _gp, _as = _make(tmp_path)
    tracking.add_keyword("photo editor", "587366035", "us", "en", platform="app_store")
    tracking.add_keyword("photo editor", "587366035", "us", "en")  # google_play twin

    # Both syncs must succeed (no MultipleResultsFound) and stamp their own row only.
    tracking.sync_keyword_now("photo editor", "587366035", "us", "en", platform="app_store")
    tracking.sync_keyword_now("photo editor", "587366035", "us", "en")

    rows = {row.platform: row for row in tracking.list_keywords()}
    assert set(rows) == {"app_store", "google_play"}
    assert all(row.last_synced_at is not None for row in rows.values())

    # Rank history stays platform-scoped: the iTunes backend finds rank 2, the GP
    # backend's results don't contain the id at all — neither overwrote the other.
    as_latest = tracking.keyword_service_app_store.latest_rank(
        "photo editor", "587366035", "us", "en"
    )
    gp_latest = tracking.keyword_service.latest_rank("photo editor", "587366035", "us", "en")
    assert as_latest is not None and as_latest.rank == 2 and as_latest.found
    assert gp_latest is not None and not gp_latest.found


def test_remove_keyword_only_touches_its_platform(tmp_path):
    tracking, _gp, _as = _make(tmp_path)
    tracking.add_keyword("vpn", "587366035", "us", "en", platform="app_store")
    tracking.add_keyword("vpn", "587366035", "us", "en")

    removed = tracking.remove_keyword("vpn", "587366035", "us", "en")  # google_play only

    assert removed == 1
    remaining = tracking.list_keywords()
    assert len(remaining) == 1
    assert remaining[0].platform == "app_store"


def test_toggle_keyword_only_touches_its_platform(tmp_path):
    tracking, _gp, _as = _make(tmp_path)
    tracking.add_keyword("vpn", "587366035", "us", "en", platform="app_store")
    tracking.add_keyword("vpn", "587366035", "us", "en")

    enabled = tracking.toggle_keyword("vpn", "587366035", "us", "en", platform="app_store")

    assert enabled is False
    rows = {row.platform: bool(row.enabled) for row in tracking.list_keywords()}
    assert rows == {"app_store": False, "google_play": True}


def test_keyword_service_for_missing_app_store_service_fails_loudly(tmp_path):
    """Regression: a missing platform service must raise, not silently rank the keyword
    through Google Play and record bogus found=False rows."""
    import pytest

    database = Database(str(tmp_path / "loud.sqlite3"))
    database.create_all()
    tracking = TrackingService(
        database=database,
        google_play_service=None,
        keyword_service=KeywordService(RecordingSearch([]), database=database),
        keyword_service_app_store=None,
    )
    with pytest.raises(RuntimeError, match="App Store"):
        tracking.sync_keyword_now("vpn", "587366035", "us", "en", platform="app_store")
