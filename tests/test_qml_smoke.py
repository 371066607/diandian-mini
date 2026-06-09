"""QML UI regression guard: loads the real Main.qml offscreen against the real
QmlBridge (with fake, network-free scraping) and asserts the bridge exposes the
full AppDetail field set the page binds to.

QML errors only surface at runtime, so the engine-load assertion is what
catches syntax/typo regressions in Main.qml.
"""

import logging
import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

from app.db.database import Database
from app.db.migrations import migrate
from app.schemas.app_schema import AppDetail, AppSummary
from app.schemas.review_schema import ReviewItem
from app.services.alert_service import AlertService
from app.services.chart_rank_service import ChartRankService
from app.services.chart_service import ChartService
from app.services.export_service import ExportService
from app.services.keyword_service import KeywordService
from app.services.monetization_service import MonetizationService
from app.services.review_service import ReviewService
from app.services.settings_service import SettingsService
from app.services.tracking_service import TrackingService
from app.ui.qml_bridge import QmlBridge


class FakeGooglePlayService:
    """Canned schema objects; no network."""

    def search(self, keyword, country="us", lang="en", limit=20):
        return [AppSummary(app_id="com.telegram", title="Telegram", has_iap=True)]

    def app_detail(self, app_id, country="us", lang="en"):
        return AppDetail(
            app_id=app_id,
            title="WhatsApp Messenger",
            developer="WhatsApp LLC",
            developer_id="WhatsApp+LLC",
            category="Communication",
            categories=["Communication", "Social"],
            summary="Simple. Reliable. Private.",
            rating=4.4,
            ratings_count=190_000_000,
            reviews_count=12_000_000,
            installs="10,000,000,000+",
            min_installs=10_000_000_000,
            real_installs=12_345_678_901,
            daily_installs=1_000_000,
            monthly_installs=30_000_000,
            app_age_days=4000,
            version="2.24",
            android_version="5.0",
            min_android_api=21,
            max_android_api=34,
            content_rating="Everyone",
            content_rating_description="Mild language",
            histogram=[10, 20, 30, 40, 500],
            free=True,
            has_iap=False,
            contains_ads=False,
            icon_url="https://example.com/icon.png",
            screenshots=["https://example.com/s1.png", "https://example.com/s2.png"],
            developer_email="support@whatsapp.com",
            developer_website="https://www.whatsapp.com",
            privacy_policy="https://www.whatsapp.com/legal",
            developer_address="1601 Willow Road",
            publisher_country="US",
            app_bundle="com.whatsapp",
            genre_id="COMMUNICATION",
            data_safety=[{"data": "位置"}, {"data": "个人信息"}],
            description="D" * 500,
            changelog="bug fixes",
        )

    def similar(self, app_id, country="us", lang="en", limit=20):
        return [AppSummary(app_id="com.signal", title="Signal", rating=4.5)]

    def permissions(self, app_id, country="us", lang="en"):
        return {"位置": ["精确位置", "大致位置"], "相机": ["拍摄照片"]}

    def reviews(self, app_id, country="us", lang="en", sort="newest", continuation_token=None):
        items = [
            ReviewItem(app_id=app_id, review_id=f"r{i}", content="c", rating=5) for i in range(3)
        ]
        return items, None

    def chart(self, chart_type, category, country, lang, limit):
        return []

    def list_analyze(self, chart_type, category, country, lang, limit):
        return []

    def configure(self, **kwargs):
        pass


def _build_services(db):
    settings_service = SettingsService(db)
    settings_service.ensure_defaults()
    gp = FakeGooglePlayService()
    keyword_service = KeywordService(gp, database=db)
    chart_rank_service = ChartRankService(gp, database=db)
    alert_service = AlertService(db)
    review_service = ReviewService(db, gp)
    tracking_service = TrackingService(
        database=db,
        google_play_service=gp,
        keyword_service=keyword_service,
        alert_service=alert_service,
        settings_service=settings_service,
        review_service=review_service,
        chart_rank_service=chart_rank_service,
    )
    return {
        "settings_service": settings_service,
        "google_play_service": gp,
        "keyword_service": keyword_service,
        "chart_rank_service": chart_rank_service,
        "review_service": review_service,
        "chart_service": ChartService(db, gp),
        "monetization_service": MonetizationService(),
        "alert_service": alert_service,
        "tracking_service": tracking_service,
        "scheduler": None,
        "export_service": ExportService(db),
    }


def _wait_idle(app, bridge, timeout=10.0):
    deadline = time.time() + timeout
    for _ in range(3):
        app.processEvents()
    while bridge._workers and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    for _ in range(5):
        app.processEvents()
    assert not bridge._workers, "a bridge worker did not finish in time"


def test_qml_loads_and_detail_exposes_full_field_set(tmp_path):
    try:
        QQuickStyle.setStyle("Fusion")  # same as qml_app.run_qml_app; silences style warnings
        app = QApplication.instance() or QApplication([])
    except Exception:  # pragma: no cover - no Qt platform in this environment
        pytest.skip("no Qt platform available")

    db = Database(str(tmp_path / "qml.sqlite3"))
    migrate(db)
    services = _build_services(db)
    bridge = QmlBridge(database=db, services=services, logger=logging.getLogger("qml-test"))

    engine = QQmlApplicationEngine()
    engine.setInitialProperties({"bridge": bridge, "appTitle": "测试"})
    qml_file = Path(__file__).resolve().parents[1] / "app" / "qml" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))
    assert engine.rootObjects(), "Main.qml failed to load (check qml syntax errors above)"

    bridge.refreshAll()
    _wait_idle(app, bridge)

    # --- detail: full AppDetail field surface ---
    bridge.fetchAppDetail("com.whatsapp", "us", "en")
    _wait_idle(app, bridge)
    detail = bridge.detail
    assert detail["loaded"] is True
    assert detail["title"] == "WhatsApp Messenger"
    assert detail["iconUrl"].startswith("https://")
    assert detail["categories"] == ["Communication", "Social"]
    labels = [m["label"] for m in detail["metrics"]]
    for expected in (
        "评分",
        "评分数",
        "评论数",
        "安装量",
        "真实安装",
        "日均安装",
        "月均安装",
        "上线天数",
        "发布日期",
        "版本",
        "Android API",
        "内容分级",
        "价格",
        "促销",
        "内购",
        "含广告",
        "可下载",
    ):
        assert expected in labels, f"metric {expected} missing"
    by_label = {m["label"]: m["value"] for m in detail["metrics"]}
    assert by_label["真实安装"] == "12,345,678,901"
    assert by_label["Android API"] == "21 ~ 34"
    # histogram: 5 rows, 5-star first
    assert len(detail["histogram"]) == 5
    assert detail["histogram"][0]["star"] == 5
    assert detail["histogram"][0]["count"] == 500
    # developer links + plain rows
    assert detail["devLinks"][0]["url"] == "mailto:support@whatsapp.com"
    assert any(p["value"] == "US" for p in detail["devPlain"])
    assert detail["dataSafety"] == "位置、个人信息"
    assert len(detail["screenshots"]) == 2
    # async extras landed: history series has today's point, similar resolved
    assert detail["ratingValues"][-1] == 4.4
    assert detail["similarLoading"] is False
    assert detail["similar"][0]["appId"] == "com.signal"
    assert detail["recentReviews"] == []  # nothing cached yet

    # --- permissions on demand ---
    bridge.fetchDetailPermissions()
    _wait_idle(app, bridge)
    detail = bridge.detail
    assert detail["permissionsLoaded"] is True
    assert {g["group"] for g in detail["permissions"]} == {"位置", "相机"}

    # --- search rows carry icon + iap badge ---
    bridge.searchApps("messenger", "us", "en", "10")
    _wait_idle(app, bridge)
    assert bridge.search["rows"][0]["hasIap"] == "内购"
    assert "iconUrl" in bridge.search["rows"][0]

    # --- reviews: load-more state exposed ---
    bridge.fetchReviews("com.whatsapp", "us", "en", "newest")
    _wait_idle(app, bridge)
    assert len(bridge.reviews["rows"]) == 3
    assert bridge.reviews["hasMore"] is False  # fake returns no continuation token

    del engine  # release QML objects before the QApplication goes away
