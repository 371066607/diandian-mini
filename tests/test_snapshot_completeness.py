import json

from app.db.database import Database
from app.db.models import AppSnapshotModel
from app.db.repositories import SnapshotRepository
from app.schemas.app_schema import AppDetail
from app.utils.normalize import bool_to_int, dump_json
from app.utils.time_utils import now_iso


def _full_detail() -> AppDetail:
    return AppDetail(
        app_id="com.example.app",
        title="Example App",
        developer="Example Dev",
        developer_id="dev-123",
        category="GAME",
        summary="A short summary.",
        rating=4.5,
        ratings_count=12345,
        reviews_count=6789,
        installs="1,000,000+",
        min_installs=1_000_000,
        real_installs=1_234_567,
        price="Free",
        currency="USD",
        free=True,
        has_iap=True,
        icon_url="https://example.com/icon.png",
        store_url="https://play.google.com/store/apps/details?id=com.example.app",
        version="1.2.3",
        updated="2026-01-01",
        released="Oct 18, 2010",
        android_version="8.0",
        content_rating="Everyone",
        description="Full description.",
        changelog="Bug fixes.",
        screenshots=["https://example.com/s1.png", "https://example.com/s2.png"],
        histogram=[1, 2, 3, 4, 5],
        contains_ads=True,
        ad_supported=False,
        iap_price_range="$0.99 - $9.99",
        developer_email="dev@example.com",
        developer_website="https://example.com",
        developer_address="123 Main St",
        developer_phone="+1-555-0100",
        publisher_country="US",
        privacy_policy="https://example.com/privacy",
        header_image="https://example.com/header.png",
        genre_id="GAME_ACTION",
        categories=["Action", "Adventure"],
        available=True,
        app_age_days=5000,
        video="https://example.com/video.mp4",
        video_image="https://example.com/video.png",
        daily_installs=100,
        min_daily_installs=80,
        real_daily_installs=120,
        monthly_installs=3000,
        min_monthly_installs=2400,
        real_monthly_installs=3600,
        max_android_api=34,
        min_android_api=21,
        app_bundle="com.example.app",
        content_rating_description="No objectionable content.",
        permissions={"Storage": ["read", "write"]},
        data_safety=[{"category": "Location", "shared": True}],
        sale=False,
        original_price=4.99,
        raw={"appId": "com.example.app", "extra": "value"},
    )


def _snapshot_from_detail(detail: AppDetail, country: str, lang: str) -> AppSnapshotModel:
    """Build an AppSnapshotModel the same way the retired
    SnapshotRepository.save_detail used to, so read-path tests can seed rows
    directly through the ORM instead of the deleted write method."""
    return AppSnapshotModel(
        captured_at=now_iso(),
        platform=detail.platform,
        app_id=detail.app_id,
        country=country,
        lang=lang,
        title=detail.title,
        developer=detail.developer,
        category=detail.category,
        rating=detail.rating,
        ratings_count=detail.ratings_count,
        reviews_count=detail.reviews_count,
        installs=detail.installs,
        min_installs=detail.min_installs,
        real_installs=detail.real_installs,
        price=detail.price,
        free=bool_to_int(detail.free),
        has_iap=bool_to_int(detail.has_iap),
        version=detail.version,
        updated=detail.updated,
        released=detail.released,
        android_version=detail.android_version,
        content_rating=detail.content_rating,
        description=detail.description,
        summary=detail.summary,
        changelog=detail.changelog,
        icon_url=detail.icon_url,
        screenshots_json=dump_json(detail.screenshots),
        contains_ads=bool_to_int(detail.contains_ads),
        ad_supported=bool_to_int(detail.ad_supported),
        daily_installs=detail.daily_installs,
        min_daily_installs=detail.min_daily_installs,
        real_daily_installs=detail.real_daily_installs,
        monthly_installs=detail.monthly_installs,
        min_monthly_installs=detail.min_monthly_installs,
        real_monthly_installs=detail.real_monthly_installs,
        app_age_days=detail.app_age_days,
        genre_id=detail.genre_id,
        developer_id=detail.developer_id,
        currency=detail.currency,
        sale=bool_to_int(detail.sale),
        original_price=detail.original_price,
        developer_email=detail.developer_email,
        developer_website=detail.developer_website,
        developer_address=detail.developer_address,
        developer_phone=detail.developer_phone,
        publisher_country=detail.publisher_country,
        privacy_policy=detail.privacy_policy,
        header_image=detail.header_image,
        video=detail.video,
        content_rating_description=detail.content_rating_description,
        available=bool_to_int(detail.available),
        max_android_api=detail.max_android_api,
        min_android_api=detail.min_android_api,
        app_bundle=detail.app_bundle,
        histogram_json=dump_json(detail.histogram),
        categories_json=dump_json(detail.categories),
        permissions_json=dump_json(detail.permissions),
        data_safety_json=dump_json(detail.data_safety),
        raw_json=dump_json(detail.raw),
    )


def test_save_detail_persists_all_extended_columns(tmp_path):
    database = Database(str(tmp_path / "x.sqlite3"))
    database.create_all()
    repo = SnapshotRepository()
    detail = _full_detail()

    with database.session() as session:
        session.add(_snapshot_from_detail(detail, country="us", lang="en"))

    with database.session() as session:
        row = repo.latest(session, "com.example.app", country="us", lang="en")

    assert row is not None

    # Scalars
    assert row.developer_id == "dev-123"
    assert row.genre_id == "GAME_ACTION"
    assert row.currency == "USD"
    assert row.real_installs == 1_234_567
    assert row.daily_installs == 100
    assert row.min_daily_installs == 80
    assert row.real_daily_installs == 120
    assert row.monthly_installs == 3000
    assert row.min_monthly_installs == 2400
    assert row.real_monthly_installs == 3600
    assert row.app_age_days == 5000
    assert row.original_price == 4.99
    assert row.developer_email == "dev@example.com"
    assert row.developer_website == "https://example.com"
    assert row.developer_address == "123 Main St"
    assert row.developer_phone == "+1-555-0100"
    assert row.publisher_country == "US"
    assert row.privacy_policy == "https://example.com/privacy"
    assert row.header_image == "https://example.com/header.png"
    assert row.video == "https://example.com/video.mp4"
    assert row.content_rating_description == "No objectionable content."
    assert row.max_android_api == 34
    assert row.min_android_api == 21
    assert row.app_bundle == "com.example.app"

    # Booleans persist as 1/0
    assert row.contains_ads == 1
    assert row.ad_supported == 0
    assert row.available == 1
    assert row.sale == 0

    # JSON columns round-trip via json.loads
    assert json.loads(row.histogram_json) == [1, 2, 3, 4, 5]
    assert json.loads(row.categories_json) == ["Action", "Adventure"]
    assert json.loads(row.permissions_json) == {"Storage": ["read", "write"]}
    assert json.loads(row.data_safety_json) == [{"category": "Location", "shared": True}]


def test_save_detail_handles_none_booleans(tmp_path):
    database = Database(str(tmp_path / "x.sqlite3"))
    database.create_all()
    repo = SnapshotRepository()
    detail = AppDetail(app_id="com.minimal.app", title="Minimal")

    with database.session() as session:
        session.add(_snapshot_from_detail(detail, country="us", lang="en"))

    with database.session() as session:
        row = repo.latest(session, "com.minimal.app", country="us", lang="en")

    assert row is not None
    assert row.contains_ads is None
    assert row.ad_supported is None
    assert row.sale is None
    # available defaults to None on AppDetail when not enriched
    assert row.available is None
    # Empty list/dict JSON columns still round-trip.
    assert json.loads(row.histogram_json) == {}
    assert json.loads(row.categories_json) == {}
    assert json.loads(row.permissions_json) == {}
    assert json.loads(row.data_safety_json) == {}
