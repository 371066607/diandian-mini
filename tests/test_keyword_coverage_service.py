from __future__ import annotations

import threading

from app.schemas.app_schema import AppDetail, AppSummary
from app.services.keyword_coverage_service import KeywordCoverageService
from app.utils.proxy_pool import ProxyPool

TARGET = "com.test.app"


class FakeStore:
    """Offline stand-in: canned detail, autocomplete and search — no network."""

    def __init__(self) -> None:
        self.searched: list[str] = []

    def app_detail(self, app_id, country="us", lang="en") -> AppDetail:
        return AppDetail(
            platform="google_play",
            app_id=app_id,
            title="Photo Editor Pro",
            category="Photography",
            summary="Edit photos with filters and collage.",
            description="A powerful photo editor with filters, collage and effects.",
        )

    def suggest(self, term, country="us", lang="en", count=8) -> list[str]:
        table = {
            "photo editor": ["photo editor", "photo editor free"],
            "photo": ["photo", "photo collage"],
            "editor": ["editor", "video editor"],
        }
        return table.get(term, [])

    def suggest_nested(self, term, country="us", lang="en", count=5) -> dict[str, list[str]]:
        # Each first-level suggestion expands one level further; the level-2 phrases
        # are reachable ONLY through deep mining, never through flat ``suggest``.
        table = {
            "photo editor": {
                "photo editor free": ["photo editor free download"],
                "photo editor background": ["photo editor background changer"],
            },
            "photo": {"photo collage": ["photo collage maker"]},
            "editor": {"video editor": ["video editor with music"]},
        }
        return table.get(term, {})

    def search(self, keyword, country="us", lang="en", limit=50) -> list[AppSummary]:
        self.searched.append(keyword)
        ranks = {"photo editor": 1, "photo collage": 3, "video editor": 12}
        target_rank = ranks.get(keyword)
        results: list[AppSummary] = []
        for position in range(1, min(limit, 20) + 1):
            app_id = TARGET if position == target_rank else f"com.other.{keyword}.{position}"
            results.append(AppSummary(platform="google_play", app_id=app_id))
        return results


def test_discover_candidates_seeds_from_metadata_and_autocomplete():
    store = FakeStore()
    service = KeywordCoverageService(store)
    candidates = service.discover_candidates("google_play", TARGET)
    # title bigram + token seeds are present, and autocomplete expansions are merged in
    assert "photo editor" in candidates
    assert "editor" in candidates
    assert "video editor" in candidates  # only reachable via suggest("editor")
    assert len(candidates) == len(set(candidates))  # deduped


def test_deep_discovery_expands_nested_autocomplete():
    store = FakeStore()
    service = KeywordCoverageService(store)
    shallow = service.discover_candidates("google_play", TARGET)
    deep = service.discover_candidates("google_play", TARGET, deep=True)
    # A level-2 phrase is reachable ONLY via suggest_nested, never via flat suggest.
    assert "photo editor background changer" not in shallow
    assert "photo editor background changer" in deep
    assert "photo editor background" in deep  # the level-1 parent is kept too
    assert len(deep) == len(set(deep))  # deduped


def test_deep_discovery_falls_back_to_flat_when_nested_empty():
    class NoNestedStore(FakeStore):
        def suggest_nested(self, term, country="us", lang="en", count=5):
            return {}  # nested backend yields nothing (e.g. a network hiccup)

    service = KeywordCoverageService(NoNestedStore())
    deep = service.discover_candidates("google_play", TARGET, deep=True)
    # with nested empty, deep mode must still fall back to the flat expansion
    assert "video editor" in deep  # only reachable via flat suggest("editor")


def test_analyze_coverage_keeps_only_ranked_keywords_sorted_by_rank():
    store = FakeStore()
    service = KeywordCoverageService(store)
    result = service.analyze_coverage("google_play", TARGET, limit=50)

    covered = {row["keyword"]: row["rank"] for row in result.covered}
    assert covered["photo editor"] == 1
    assert covered["video editor"] == 12
    # a candidate the app does not rank for is excluded
    assert "photo editor free" not in covered
    # sorted ascending by rank
    ranks = [row["rank"] for row in result.covered]
    assert ranks == sorted(ranks)
    assert result.candidate_count >= len(result.covered)


def test_coverage_respects_limit_cutoff():
    store = FakeStore()
    service = KeywordCoverageService(store)
    # with limit=5, the rank-12 "video editor" hit falls outside the window
    result = service.analyze_coverage("google_play", TARGET, limit=5)
    covered = {row["keyword"] for row in result.covered}
    assert "photo editor" in covered  # rank 1, within 5
    assert "video editor" not in covered  # rank 12, beyond 5


class BundleIdStore(FakeStore):
    """App Store shape: app_detail resolves a Bundle ID to the numeric trackId, and
    search results only ever carry the numeric id."""

    CANONICAL = "310633997"

    def app_detail(self, app_id, country="us", lang="en") -> AppDetail:
        detail = super().app_detail(app_id, country=country, lang=lang)
        return detail.model_copy(update={"platform": "app_store", "app_id": self.CANONICAL})

    def search(self, keyword, country="us", lang="en", limit=50):
        results = super().search(keyword, country=country, lang=lang, limit=limit)
        # the fake plants TARGET at the scripted rank — rewrite it to the numeric id
        return [
            item.model_copy(update={"app_id": self.CANONICAL})
            if item.app_id == TARGET
            else item
            for item in results
        ]


def test_bundle_id_input_matches_canonical_track_id():
    """Regression: matching used to compare the raw user input against results, so an
    App Store Bundle ID (which search results never contain) always yielded 0 covered."""
    store = BundleIdStore()
    service = KeywordCoverageService(None, app_store_service=store)
    result = service.analyze_coverage("app_store", "net.whatsapp.WhatsApp", limit=50)

    covered = {row["keyword"]: row["rank"] for row in result.covered}
    assert covered["photo editor"] == 1
    assert result.canonical_app_id == BundleIdStore.CANONICAL
    assert result.app_id == "net.whatsapp.WhatsApp"  # raw input preserved for display


def test_precomputed_candidates_skip_detail_fetch():
    """A re-scan that passes back candidates + canonical id must not re-pay the
    detail/autocomplete requests."""
    store = BundleIdStore()
    calls = {"detail": 0}
    original = store.app_detail

    def counting_detail(*args, **kwargs):
        calls["detail"] += 1
        return original(*args, **kwargs)

    store.app_detail = counting_detail
    service = KeywordCoverageService(None, app_store_service=store)
    result = service.analyze_coverage(
        "app_store",
        "net.whatsapp.WhatsApp",
        limit=50,
        candidates=["photo editor"],
        canonical_app_id=BundleIdStore.CANONICAL,
    )
    assert calls["detail"] == 0
    assert result.covered and result.covered[0]["rank"] == 1


class DeadNetworkStore(FakeStore):
    def search(self, keyword, country="us", lang="en", limit=50):
        self.searched.append(keyword)
        raise RuntimeError("connection refused")


def test_scan_aborts_after_consecutive_failures():
    """Regression: with the network down, the scan used to grind every candidate's full
    retry chain and then render '命中 0 个' as a successful result."""
    import pytest

    from app.services.google_play_service import ServiceError

    store = DeadNetworkStore()
    service = KeywordCoverageService(store)
    candidates = [f"kw{i}" for i in range(20)]
    with pytest.raises(ServiceError):
        service.analyze_coverage("google_play", TARGET, candidates=candidates)
    assert len(store.searched) == KeywordCoverageService.ABORT_AFTER_FAILURES


def test_failure_streak_resets_on_success():
    class FlakyStore(FakeStore):
        def __init__(self) -> None:
            super().__init__()
            self.attempts = 0

        def search(self, keyword, country="us", lang="en", limit=50):
            self.attempts += 1
            if self.attempts % 2 == 1:  # odd attempts fail, even attempts succeed
                raise RuntimeError("flaky")
            return super().search(keyword, country=country, lang=lang, limit=limit)

    store = FlakyStore()
    service = KeywordCoverageService(store)
    candidates = [f"kw{i}" for i in range(12)]
    result = service.analyze_coverage("google_play", TARGET, candidates=candidates)
    # alternating failures never reach the cutoff — the scan completes all candidates
    assert store.attempts == len(candidates)
    assert result.candidate_count == len(candidates)


class ProxyAwareStore:
    """Records which proxy each search ran through; ranks a couple of known keywords."""

    RANKS = {"photo editor": 1, "video editor": 12}

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.proxies_used: list[str | None] = []

    def search(self, keyword, country="us", lang="en", limit=50, proxy=None):
        with self._lock:
            self.proxies_used.append(proxy)
        target_rank = self.RANKS.get(keyword)
        results = []
        for pos in range(1, min(limit, 20) + 1):
            app_id = TARGET if pos == target_rank else f"com.other.{pos}"
            results.append(AppSummary(app_id=app_id))
        return results


def test_concurrent_scan_routes_every_search_through_a_proxy():
    store = ProxyAwareStore()
    pool = ProxyPool(["http://p1", "http://p2", "http://p3"])
    service = KeywordCoverageService(store)
    candidates = ["photo editor", "video editor", "nope"]

    result = service.analyze_coverage(
        "google_play", TARGET, limit=50, candidates=candidates,
        canonical_app_id=TARGET, proxy_pool=pool, max_workers=3,
    )

    covered = {row["keyword"]: row["rank"] for row in result.covered}
    assert covered == {"photo editor": 1, "video editor": 12}
    # concurrency is honoured AND every request went through a proxy (never direct/None)
    assert len(store.proxies_used) == 3
    assert all(p is not None for p in store.proxies_used)


def test_dead_proxy_is_reported_and_rotated_out():
    dead = "http://dead"

    class FlakyProxyStore(ProxyAwareStore):
        def search(self, keyword, country="us", lang="en", limit=50, proxy=None):
            if proxy == dead:
                raise RuntimeError("proxy dead")
            return super().search(keyword, country, lang, limit, proxy=proxy)

    store = FlakyProxyStore()
    pool = ProxyPool([dead, "http://good"], max_failures=1, cooldown_seconds=999)
    service = KeywordCoverageService(store)

    result = service.analyze_coverage(
        "google_play", TARGET, limit=50, candidates=["photo editor"],
        canonical_app_id=TARGET, proxy_pool=pool, max_workers=1,
    )
    # the dead proxy was leased first, failed, and the keyword still resolved via the good one
    assert result.covered and result.covered[0]["rank"] == 1


def test_no_proxy_pool_forces_serial_even_with_high_max_workers():
    # FakeStore.search has NO proxy kwarg — if the code tried to parallelise/inject a
    # proxy without a pool it would TypeError. Completing proves the safe-by-design gate.
    store = FakeStore()
    service = KeywordCoverageService(store)
    result = service.analyze_coverage("google_play", TARGET, limit=50, max_workers=8)
    covered = {row["keyword"] for row in result.covered}
    assert "photo editor" in covered
