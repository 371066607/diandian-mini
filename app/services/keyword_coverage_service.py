from __future__ import annotations

import re

from app.schemas.app_schema import AppDetail
from app.services.google_play_service import ServiceError
from app.utils.normalize import normalize_app_id

# Minimal English stopword / store-filler list — enough to keep seed terms meaningful
# without pulling a heavy NLP dependency. Tokens here never become seeds on their own.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "with", "your",
    "you", "app", "apps", "free", "best", "new", "get", "all", "this", "that", "it",
    "is", "are", "be", "by", "from", "at", "as", "can", "will", "now", "more", "my",
    "our", "we", "us", "android", "google", "play", "store", "mobile", "phone", "com",
    "ios", "iphone", "ipad", "apple",
}


class KeywordCoverageResult:
    """The set of keywords a given app is reachable by, with its rank for each."""

    def __init__(
        self,
        platform: str,
        app_id: str,
        country: str,
        lang: str,
        candidates: list[str],
        covered: list[dict],
        checked_limit: int,
        canonical_app_id: str | None = None,
    ) -> None:
        self.platform = platform
        self.app_id = app_id  # as the user typed it (may be a Bundle ID on App Store)
        # The store's own id for the app (App Store: numeric trackId), as returned by
        # app_detail — what search results carry, and what monitors should be keyed on.
        self.canonical_app_id = canonical_app_id
        self.country = country
        self.lang = lang
        self.candidates = candidates
        self.candidate_count = len(candidates)
        self.covered = covered  # [{"keyword": str, "rank": int}], sorted by rank
        self.checked_limit = checked_limit


class KeywordCoverageService:
    """Discovers which search keywords surface a given app — the inverse of a normal
    rank lookup ("what keywords can find MY app").

    No app store exposes a reverse keyword index, so this mirrors, in miniature, how
    ASO tools build one: derive seed terms from the app's own metadata, expand them via
    the store's autocomplete into real query phrases, then run each candidate through
    search and keep the keywords where the app ranks within ``limit``. It is therefore
    an approximation bounded by the app's own vocabulary + what autocomplete suggests
    around it — not an exhaustive corpus scan.
    """

    # Consecutive per-keyword search failures after which the scan aborts: one keyword
    # failing is noise, an unbroken run means the network/store is down and every further
    # candidate would just grind the full retry chain to report a false "0 covered".
    MAX_CONSECUTIVE_FAILURES = 5

    def __init__(self, google_play_service, app_store_service=None):
        self.google_play_service = google_play_service
        self.app_store_service = app_store_service

    def _store(self, platform: str):
        if platform == "app_store":
            if self.app_store_service is None:
                raise ServiceError("App Store 服务未注入，无法分析 App Store 覆盖关键词。")
            return self.app_store_service
        return self.google_play_service

    def discover_candidates(
        self,
        platform: str,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        max_seeds: int = 12,
        max_candidates: int = 120,
    ) -> list[str]:
        """app metadata -> seed terms -> autocomplete expansion -> candidate keywords."""
        store = self._store(platform)
        detail = store.app_detail(app_id, country=country, lang=lang)
        return self._candidates_from_detail(
            store, detail, country, lang, max_seeds, max_candidates
        )

    def _candidates_from_detail(
        self,
        store,
        detail: AppDetail,
        country: str,
        lang: str,
        max_seeds: int = 12,
        max_candidates: int = 120,
    ) -> list[str]:
        seeds = self._seed_terms(detail, max_seeds)

        pool: list[str] = []
        seen: set[str] = set()

        def _add(term: str) -> None:
            t = self._norm(term)
            if t and t not in seen and 2 <= len(t) <= 50:
                seen.add(t)
                pool.append(t)

        for seed in seeds:
            _add(seed)
        # expand each seed through the store's autocomplete
        for seed in seeds:
            if len(pool) >= max_candidates:
                break
            for hint in store.suggest(seed, country=country, lang=lang, count=8):
                _add(hint)
                if len(pool) >= max_candidates:
                    break
        return pool[:max_candidates]

    def analyze_coverage(
        self,
        platform: str,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 50,
        max_candidates: int = 120,
        candidates: list[str] | None = None,
        canonical_app_id: str | None = None,
        progress=None,
    ) -> KeywordCoverageResult:
        """For each candidate keyword, search and keep it if the app ranks within
        ``limit``. ``progress(message, fraction)`` is called per keyword if provided.

        Search results carry the store's canonical id (App Store: numeric trackId), so a
        Bundle-ID input would never match them — the match target therefore includes the
        canonical id from ``app_detail``. Callers re-running a scan can pass back both
        ``candidates`` and ``canonical_app_id`` (from the prior result) to skip the
        detail + autocomplete requests entirely.
        """
        store = self._store(platform)
        canonical = (canonical_app_id or "").strip()
        if candidates is None:
            if progress:
                progress("正在生成候选关键词...", 0.0)
            detail = store.app_detail(app_id, country=country, lang=lang)
            canonical = canonical or str(detail.app_id or "").strip()
            candidates = self._candidates_from_detail(
                store, detail, country, lang, max_candidates=max_candidates
            )
        targets = {t for t in (normalize_app_id(app_id), normalize_app_id(canonical)) if t}
        covered: list[dict] = []
        consecutive_failures = 0
        total = len(candidates)
        for index, keyword in enumerate(candidates, 1):
            if progress:
                progress(f"覆盖检测 {index}/{total}：{keyword}", index / total if total else 1.0)
            try:
                results = store.search(keyword, country=country, lang=lang, limit=limit)
            except Exception as exc:
                # A single keyword's search failing must not abort the scan, but an
                # unbroken failure run means the network is down — abort loudly instead
                # of grinding every remaining candidate into a false "0 covered".
                consecutive_failures += 1
                if consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                    raise ServiceError(
                        f"连续 {consecutive_failures} 个关键词检索失败，已中止扫描，"
                        "请检查网络后重试。"
                    ) from exc
                continue
            consecutive_failures = 0
            for rank, item in enumerate(results, 1):
                if normalize_app_id(getattr(item, "app_id", None)) in targets:
                    covered.append({"keyword": keyword, "rank": rank})
                    break
        covered.sort(key=lambda row: row["rank"])
        return KeywordCoverageResult(
            platform,
            app_id,
            country,
            lang,
            candidates,
            covered,
            limit,
            canonical_app_id=canonical or None,
        )

    # --- seed extraction -----------------------------------------------------

    def _seed_terms(self, detail: AppDetail, max_seeds: int) -> list[str]:
        seeds: list[str] = []
        seen: set[str] = set()

        def _add(term: str) -> None:
            t = self._norm(term)
            if t and t not in seen and len(t) >= 3 and not t.isdigit():
                seen.add(t)
                seeds.append(t)

        title = detail.title or ""
        # the leading phrase of the title (before a separator) is the strongest seed
        head = re.split(r"[:\-–—|·,，、（(]", title)[0].strip()
        _add(head)

        title_tokens = [w for w in self._tokens(title) if w not in _STOPWORDS]
        # title bigrams ("photo editor") tend to be high-value search phrases
        for first, second in zip(title_tokens, title_tokens[1:]):
            _add(f"{first} {second}")
        for token in title_tokens:
            _add(token)

        if detail.category:
            _add(detail.category)

        # most frequent meaningful terms from summary + description head
        text = f"{detail.summary or ''} {(detail.description or '')[:600]}"
        freq: dict[str, int] = {}
        for word in self._tokens(text):
            if word in _STOPWORDS or len(word) < 4 or word.isdigit():
                continue
            freq[word] = freq.get(word, 0) + 1
        for word, _count in sorted(freq.items(), key=lambda kv: (-kv[1], kv[0])):
            if len(seeds) >= max_seeds:
                break
            _add(word)

        return seeds[:max_seeds]

    @staticmethod
    def _tokens(text: str) -> list[str]:
        # ASCII word tokens. CJK titles still seed via the whole-title head + category.
        return [w.lower() for w in re.findall(r"[A-Za-z0-9]+", text or "")]

    @staticmethod
    def _norm(term: str) -> str:
        return re.sub(r"\s+", " ", (term or "").strip().lower())
