"""Reviews in the monitoring loop: sync fetches + persists reviews, alerts on new
low-star ones, and any review error is a non-fatal enhancement to the snapshot sync."""

from __future__ import annotations

from app.db.database import Database
from app.schemas.app_schema import AppDetail
from app.schemas.review_schema import ReviewItem
from app.services.alert_service import AlertService
from app.services.review_service import ReviewService
from app.services.settings_service import SettingsService
from app.services.tracking_service import TrackingService


class DetailGP:
    def app_detail(self, app_id, country="us", lang="en"):
        return AppDetail(
            app_id=app_id, title="App", rating=4.4, ratings_count=100,
            reviews_count=10, version="1.0", installs="1,000,000+",
        )


class FakeReviewService:
    """Stands in for ReviewService: returns scripted new low-star reviews, counts calls."""

    def __init__(self, new_negative):
        self._new_negative = new_negative
        self.calls = 0

    def monitor_reviews(self, app_id, country="us", lang="en", limit=50, max_rating=2):
        self.calls += 1
        return list(self._new_negative)


class FailingReviewService:
    def monitor_reviews(self, *a, **k):
        raise RuntimeError("reviews down")


class ReviewsGP:
    """google_play_service.reviews stub for unit-testing ReviewService.monitor_reviews."""

    def reviews(self, app_id, country="us", lang="en", sort="newest", continuation_token=None):
        return (
            [
                ReviewItem(app_id=app_id, review_id="r1", rating=1, content="awful"),
                ReviewItem(app_id=app_id, review_id="r2", rating=5, content="great"),
                ReviewItem(app_id=app_id, review_id="r3", rating=2, content="meh"),
            ],
            None,
        )


def _build(tmp_path, name, review_service, overrides=None):
    db = Database(str(tmp_path / f"{name}.sqlite3"))
    db.create_all()
    settings = SettingsService(db)
    settings.ensure_defaults()
    if overrides:
        settings.set_many(overrides)
    alert = AlertService(db, settings_service=settings)
    ts = TrackingService(
        db, DetailGP(), alert_service=alert, settings_service=settings,
        review_service=review_service,
    )
    return db, alert, ts


def _neg(n):
    return [ReviewItem(app_id="com.x", review_id=f"n{i}", rating=1, content=f"bad {i}") for i in range(n)]


def test_review_spike_creates_alert(tmp_path):
    _, alert, ts = _build(tmp_path, "spike", FakeReviewService(_neg(3)))
    ts.add_app("com.x", "us", "en")
    ts.sync_app_now("com.x")  # first of day -> 3 new negative >= min_count(3) -> alert
    assert "review_negative_spike" in {a.type for a in alert.recent_alerts(limit=10)}


def test_below_min_count_no_alert(tmp_path):
    _, alert, ts = _build(tmp_path, "below", FakeReviewService(_neg(2)))
    ts.add_app("com.x", "us", "en")
    ts.sync_app_now("com.x")  # 2 < 3 -> no review alert
    assert "review_negative_spike" not in {a.type for a in alert.recent_alerts(limit=10)}


def test_review_failure_is_non_fatal(tmp_path):
    _, alert, ts = _build(tmp_path, "fail", FailingReviewService())
    ts.add_app("com.x", "us", "en")
    detail = ts.sync_app_now("com.x")  # must NOT raise
    assert detail is not None
    assert len(ts.get_history("com.x", "us", "en")) == 1  # snapshot still saved
    app = next(a for a in ts.list_apps() if a.app_id == "com.x")
    assert app.consecutive_failures == 0  # review failure is not a sync failure


def test_disabled_skips_review_fetch(tmp_path):
    fake = FakeReviewService(_neg(5))
    _, alert, ts = _build(tmp_path, "disabled", fake, {"review_monitor_enabled": "false"})
    ts.add_app("com.x", "us", "en")
    ts.sync_app_now("com.x")
    assert fake.calls == 0
    assert "review_negative_spike" not in {a.type for a in alert.recent_alerts(limit=10)}


def test_not_injected_behaves_normally(tmp_path):
    db = Database(str(tmp_path / "noinject.sqlite3"))
    db.create_all()
    settings = SettingsService(db)
    settings.ensure_defaults()
    alert = AlertService(db, settings_service=settings)
    ts = TrackingService(db, DetailGP(), alert_service=alert, settings_service=settings)
    ts.add_app("com.x", "us", "en")
    detail = ts.sync_app_now("com.x")  # no review_service -> unchanged behavior
    assert detail is not None
    assert len(ts.get_history("com.x", "us", "en")) == 1


def test_monitor_reviews_returns_only_new_low_star(tmp_path):
    db = Database(str(tmp_path / "unit.sqlite3"))
    db.create_all()
    rs = ReviewService(db, ReviewsGP())
    new_negative = rs.monitor_reviews("com.x", "us", "en", max_rating=2)
    ids = {r.review_id for r in new_negative}
    assert ids == {"r1", "r3"}  # 1★ and 2★ are new; 5★ excluded
    # second call: everything already persisted -> nothing new
    assert rs.monitor_reviews("com.x", "us", "en", max_rating=2) == []
