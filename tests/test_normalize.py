from app.utils.normalize import (
    normalize_app_detail,
    normalize_app_summary,
    normalize_chart_item,
    normalize_review,
    safe_float,
    safe_int,
)


def test_normalize_app_summary_supports_aliases():
    item = normalize_app_summary(
        {
            "app_id": "com.demo.app",
            "title": "Demo",
            "developerId": "dev-1",
            "genre": "Tools",
            "score": "4.6",
            "ratings": "1200",
            "reviews": 88,
            "installs": "1,000+",
            "offersIAP": True,
            "icon": "https://cdn.example/icon.png",
            "url": "https://play.example/demo",
        }
    )

    assert item.app_id == "com.demo.app"
    assert item.rating == 4.6
    assert item.ratings_count == 1200
    assert item.min_installs == 1000
    assert item.has_iap is True


def test_normalize_app_detail_carries_screenshots_and_changes():
    detail = normalize_app_detail(
        {
            "appId": "com.demo.app",
            "title": "Demo",
            "developer": "Studio",
            "recentChanges": "Bug fixes",
            "screenshots": ["a.png", "b.png"],
            "androidVersion": "8.0+",
        }
    )

    assert detail.app_id == "com.demo.app"
    assert detail.changelog == "Bug fixes"
    assert detail.screenshots == ["a.png", "b.png"]
    assert detail.android_version == "8.0+"


def test_normalize_app_detail_captures_extended_fields():
    detail = normalize_app_detail(
        {
            "appId": "com.demo.app",
            "title": "Demo",
            "realInstalls": 12004145776,
            "histogram": [10, 20, 30, 40, 50],
            "containsAds": False,
            "inAppProductPrice": "$0.40 - $199.99 per item",
            "contentRating": "Everyone",
            "developerEmail": "dev@example.com",
            "developerWebsite": "https://example.com",
            "privacyPolicy": "https://example.com/privacy",
            "headerImage": "https://example.com/header.png",
        }
    )

    assert detail.real_installs == 12004145776
    assert detail.histogram == [10, 20, 30, 40, 50]
    assert detail.contains_ads is False
    assert detail.iap_price_range == "$0.40 - $199.99 per item"
    assert detail.content_rating == "Everyone"
    assert detail.developer_email == "dev@example.com"
    assert detail.developer_website == "https://example.com"
    assert detail.privacy_policy == "https://example.com/privacy"
    assert detail.header_image == "https://example.com/header.png"


def test_normalize_review_handles_common_fields():
    review = normalize_review(
        {
            "reviewId": "r1",
            "userName": "Alice",
            "score": "5",
            "content": "Great",
            "thumbsUpCount": "7",
            "at": "2026-06-03T12:00:00",
        },
        "com.demo.app",
    )

    assert review.app_id == "com.demo.app"
    assert review.rating == 5
    assert review.helpful_count == 7


def test_normalize_chart_item_preserves_rank_context():
    item = normalize_chart_item(
        {
            "appId": "com.demo.app",
            "title": "Demo",
            "developer": "Studio",
            "score": 4.2,
            "installs": "10M+",
        },
        rank=3,
        chart_type="top_free",
        country="us",
        lang="en",
    )

    assert item.rank == 3
    assert item.chart_type == "top_free"
    assert item.country == "us"
    assert item.lang == "en"


def test_safe_int_handles_garbage():
    assert safe_int("50") == 50
    assert safe_int("1,000") == 1000
    assert safe_int("  20 ") == 20
    assert safe_int("12.9") == 12
    assert safe_int("abc", 100) == 100
    assert safe_int("", 7) == 7
    assert safe_int(None, 9) == 9
    assert safe_int("nope") == 0  # default default is 0


def test_safe_float_handles_garbage():
    assert safe_float("1.5") == 1.5
    assert safe_float("2") == 2.0
    assert safe_float("abc", 2.0) == 2.0
    assert safe_float("", 1.0) == 1.0
    assert safe_float(None, 0.5) == 0.5
