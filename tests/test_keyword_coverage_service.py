from __future__ import annotations

from app.schemas.app_schema import AppDetail, AppSummary
from app.services.keyword_coverage_service import KeywordCoverageService

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
    assert len(store.searched) == KeywordCoverageService.MAX_CONSECUTIVE_FAILURES


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
