from __future__ import annotations

from app.utils.proxy_pool import ProxyPool, load_proxies, parse_proxies


class FakeClock:
    """Controllable monotonic clock for deterministic cooldown tests."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def test_parse_proxies_normalizes_dedups_and_skips_comments():
    text = """
    http://1.1.1.1:8080
    2.2.2.2:3128            # bare host:port gets an http:// scheme
    # a comment line
    http://1.1.1.1:8080     , socks5://3.3.3.3:1080
    """
    assert parse_proxies(text) == [
        "http://1.1.1.1:8080",
        "http://2.2.2.2:3128",
        "socks5://3.3.3.3:1080",
    ]


def test_parse_proxies_empty():
    assert parse_proxies("") == []
    assert parse_proxies(None) == []


def test_lease_round_robins_healthy_proxies():
    pool = ProxyPool(["http://a", "http://b", "http://c"])
    assert [pool.lease() for _ in range(4)] == [
        "http://a", "http://b", "http://c", "http://a",
    ]


def test_empty_pool_leases_none():
    pool = ProxyPool([])
    assert not pool.has_proxies()
    assert pool.lease() is None


def test_report_bad_cools_down_then_recovers():
    clock = FakeClock()
    pool = ProxyPool(
        ["http://a", "http://b"], max_failures=2, cooldown_seconds=10, clock=clock
    )
    # two failures on `a` put it on cooldown; only `b` is leased meanwhile
    pool.report_bad("http://a")
    pool.report_bad("http://a")
    assert {pool.lease() for _ in range(4)} == {"http://b"}
    # after the cooldown window `a` returns to rotation
    clock.t = 11
    assert {pool.lease() for _ in range(4)} == {"http://a", "http://b"}


def test_report_ok_resets_failures():
    clock = FakeClock()
    pool = ProxyPool(["http://a"], max_failures=2, cooldown_seconds=10, clock=clock)
    pool.report_bad("http://a")  # 1 failure, not yet cooling down
    pool.report_ok("http://a")  # reset
    pool.report_bad("http://a")  # 1 failure again — still under the threshold
    assert pool.lease() == "http://a"  # never hit 2-in-a-row, stays healthy


def test_all_cooling_down_leases_none():
    clock = FakeClock()
    pool = ProxyPool(["http://a"], max_failures=1, cooldown_seconds=10, clock=clock)
    pool.report_bad("http://a")  # threshold 1 -> immediate cooldown
    assert pool.lease() is None
    clock.t = 11
    assert pool.lease() == "http://a"


def test_load_proxies_merges_settings_and_file(tmp_path):
    class FakeSettings:
        def get(self, key, default=None):
            return "http://from-setting:8080" if key == "coverage_proxies" else default

    (tmp_path / "proxies.txt").write_text(
        "http://from-file:3128\nhttp://from-setting:8080\n", encoding="utf-8"
    )
    proxies = load_proxies(FakeSettings(), tmp_path)
    # setting first, file second, the duplicate dropped
    assert proxies == ["http://from-setting:8080", "http://from-file:3128"]


def test_load_proxies_empty_sources():
    assert load_proxies(None, None) == []
