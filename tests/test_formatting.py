from types import SimpleNamespace

from app.ui import formatting


def test_review_row_formats_all_fields():
    item = SimpleNamespace(
        platform="google_play",
        app_id="com.demo",
        country="us",
        lang="en",
        review_id="r1",
        user_name="Alice",
        rating=5,
        app_version="1.2.3",
        helpful_count=3,
        review_created_at="2026-06-18T09:30:00Z",
        captured_at="2026-06-18T10:00:00Z",
        content="  great   app  ",
        raw={"source": "test"},
    )

    row = formatting.review_row(item)

    assert row["appId"] == "com.demo"
    assert row["user"] == "Alice"
    assert row["rating"] == 5
    assert row["helpful"] == 3
    assert row["content"] == "great app"
    assert row["time"] == "2026-06-18"
    assert row["reviewCreatedAt"] == "2026-06-18 09:30:00"
    assert "source" in row["rawFull"]


def test_review_row_defaults_missing_fields_to_dash():
    row = formatting.review_row(SimpleNamespace())

    assert row["user"] == "-"
    assert row["rating"] == "-"
    assert row["helpful"] == "-"
    assert row["time"] == "-"
    assert row["content"] == ""
    assert row["rawFull"] == ""


def test_rank_text():
    assert formatting.rank_text(3) == "#3"
    assert formatting.rank_text(None) == "未命中"
    assert formatting.rank_text(0) == "未命中"


def test_fmt_size():
    assert formatting.fmt_size(500 * 1024) == "0.5 MB"
    assert formatting.fmt_size(2 * 1024**3) == "2.00 GB"
    assert formatting.fmt_size(None) == "-"
    assert formatting.fmt_size("not-a-number") == "-"


def test_histogram_rows():
    assert formatting.histogram_rows(None) == []
    assert formatting.histogram_rows([0, 0, 0, 0, 0]) == []
    rows = formatting.histogram_rows([1, 2, 3, 4, 10])
    assert len(rows) == 5
    assert rows[0]["star"] == 5
    assert rows[0]["count"] == 10
    assert rows[0]["ratio"] == 1.0
    assert rows[-1]["star"] == 1
    assert rows[-1]["count"] == 1


def test_price_label_free_and_paid():
    free_item = SimpleNamespace(
        price="", free=True, has_iap=True, contains_ads=False, ad_supported=None
    )
    assert formatting.price_label(free_item) == "免费 · 含内购 · 无广告"

    paid_item = SimpleNamespace(
        price="$4.99", free=False, has_iap=None, contains_ads=None, ad_supported=True
    )
    assert formatting.price_label(paid_item) == "$4.99 · 含广告"


def test_fmt_count():
    assert formatting.fmt_count(1234567) == "1,234,567"
    assert formatting.fmt_count(0) == "-"
    assert formatting.fmt_count(None) == "-"
    assert formatting.fmt_count("100") == "-"  # not int/float, treated as unknown


def test_yes_no():
    assert formatting.yes_no(True) == "是"
    assert formatting.yes_no(False) == "否"
    assert formatting.yes_no(None) == "-"


def test_data_safety_text():
    assert formatting.data_safety_text(None) == "-"
    assert formatting.data_safety_text([]) == "-"
    assert (
        formatting.data_safety_text([{"data": "Location"}, {"type": "Contacts"}])
        == "Location、Contacts"
    )
    assert formatting.data_safety_text([{}] * 3) == "3 项"
    many = [{"data": f"item{i}"} for i in range(10)]
    text = formatting.data_safety_text(many)
    assert text.endswith(" …")
    assert text.count("、") == 7  # 8 shown, 7 separators


def test_compact_text():
    assert formatting.compact_text(None) == ""
    assert formatting.compact_text("  hello   world  ") == "hello world"
    assert formatting.compact_text("a" * 10, limit=5) == "aaaa…"


def test_short_time():
    assert formatting.short_time(None) == "-"
    assert formatting.short_time("") == "-"
    assert formatting.short_time("2026-06-18T09:30:00Z") == "06-18 09:30"
    assert formatting.short_time("short") == "short"


def test_fmt_dt():
    assert formatting.fmt_dt(None) == "未同步"
    assert formatting.fmt_dt("2026-06-18T09:30:00") == "06-18 09:30"
    assert formatting.fmt_dt("not-a-date-but-long-enough") == "not-a-date"
    assert formatting.fmt_dt("bad") == "bad"


def test_latest_sync_time():
    group_a = [SimpleNamespace(last_synced_at="2026-06-01T00:00:00")]
    group_b = [
        SimpleNamespace(last_synced_at="2026-06-18T00:00:00"),
        SimpleNamespace(last_synced_at=None),
    ]
    assert formatting.latest_sync_time(group_a, group_b) == "2026-06-18T00:00:00"
    assert formatting.latest_sync_time([], []) is None


def test_frequency_label():
    assert formatting.frequency_label("daily") == "每日"
    assert formatting.frequency_label("weekly") == "每周"
    assert formatting.frequency_label("manual") == "手动"
    assert formatting.frequency_label(None) == "每日"
    assert formatting.frequency_label("custom") == "custom"


def test_fail_label():
    assert formatting.fail_label(SimpleNamespace(consecutive_failures=0)) == "-"
    assert formatting.fail_label(SimpleNamespace(consecutive_failures=3)) == "3 次"
    assert formatting.fail_label(SimpleNamespace()) == "-"


def test_next_sync_label_manual_and_missing():
    assert formatting.next_sync_label("2026-06-18T00:00:00", "manual") == "手动"
    assert formatting.next_sync_label(None, "daily") == "待首次同步"


def test_next_sync_label_computes_next_window():
    from app.utils.time_utils import now_iso

    label = formatting.next_sync_label(now_iso(), "daily")
    assert label not in ("待首次同步", "手动")
    assert "-" in label  # MM-DD HH:MM shape
