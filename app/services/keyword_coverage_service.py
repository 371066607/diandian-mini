from __future__ import annotations

import re
import threading
from concurrent.futures import ThreadPoolExecutor

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

    # How many keywords may fail BEFORE the first success before the scan gives up: one
    # keyword failing is noise, but an opening run of nothing-but-failures means the
    # network/store is down and every further candidate would just grind the full retry
    # chain to report a false "0 covered". Once anything has succeeded the scan never
    # aborts — flaky free proxies can drop individual keywords without killing the run.
    ABORT_AFTER_FAILURES = 5
    # Distinct proxies to try for one keyword before recording it as failed — bounds the
    # cost of a keyword hitting several dead proxies in a row.
    MAX_PROXY_ATTEMPTS = 3
    # Deep mode (深度挖掘) searches a much larger candidate pool than a normal scan —
    # more keywords checked = more coverage found, at proportionally more requests.
    DEEP_MAX_CANDIDATES = 200
    # Alphabet-soup harvesting (deep only): expand the strongest few seeds by appending
    # a-z and reading autocomplete back. Each seed ≈ 26 requests, so bound the count.
    SOUP_SEEDS = 2
    SOUP_LETTERS = "abcdefghijklmnopqrstuvwxyz"

    def __init__(self, google_play_service, app_store_service=None, keyword_corpus_service=None):
        self.google_play_service = google_play_service
        self.app_store_service = app_store_service
        # Optional self-accumulating keyword pool. When injected, every scan reads from
        # it (reflux) and feeds it (sediment); when None, behaviour is unchanged.
        self.keyword_corpus_service = keyword_corpus_service

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
        deep: bool = False,
    ) -> list[str]:
        """app metadata -> seed terms -> autocomplete expansion -> candidate keywords."""
        store = self._store(platform)
        detail = store.app_detail(app_id, country=country, lang=lang)
        return self._candidates_from_detail(
            store, detail, country, lang, max_seeds, max_candidates,
            deep=deep, platform=platform, app_id=app_id,
        )

    def _candidates_from_detail(
        self,
        store,
        detail: AppDetail,
        country: str,
        lang: str,
        max_seeds: int = 12,
        max_candidates: int = 120,
        deep: bool = False,
        platform: str = "google_play",
        app_id: str | None = None,
    ) -> list[str]:
        seeds = self._seed_terms(detail, max_seeds)
        # deep scans search a larger pool — the explicit "more / slower" of 深度挖掘.
        cap = max(max_candidates, self.DEEP_MAX_CANDIDATES) if deep else max_candidates

        pool: list[str] = []
        seen: set[str] = set()
        source_of: dict[str, str] = {}

        def _add(term: str, source: str) -> bool:
            """Add a normalized candidate; returns False once the pool is full."""
            t = self._norm(term)
            if t and t not in seen and 2 <= len(t) <= 50:
                seen.add(t)
                pool.append(t)
                source_of[t] = source
            return len(pool) < cap

        def _flat(seed: str) -> None:
            for hint in store.suggest(seed, country=country, lang=lang, count=8):
                if not _add(hint, "autocomplete"):
                    return

        for seed in seeds:
            _add(seed, "seed")

        # 1) autocomplete expansion. deep mode goes one level further (suggest_nested);
        # falls back to flat when nested is unsupported or comes back empty.
        nested_fn = getattr(store, "suggest_nested", None) if deep else None
        for seed in seeds:
            if len(pool) >= cap:
                break
            nested = nested_fn(seed, country=country, lang=lang, count=6) if nested_fn else None
            if nested:
                stop = False
                for parent, children in nested.items():
                    if not _add(parent, "autocomplete"):
                        break
                    for child in children:
                        if not _add(child, "autocomplete"):
                            stop = True
                            break
                    if stop:
                        break
            else:
                _flat(seed)

        # 2) reflux: fold in RELEVANT keywords accumulated from earlier scans of this
        # locale (the self-built corpus). Always on and cheap — this is what makes the
        # candidate pool grow richer over time without any external word list.
        if self.keyword_corpus_service is not None and len(pool) < cap:
            seed_tokens = {tok for s in seeds for tok in s.split()}
            for kw in self.keyword_corpus_service.candidates(
                platform, country, lang, seed_tokens, limit=cap
            ):
                if not _add(kw, "corpus"):
                    break

        # 3) deep-only harvesting. Competitor (similar) titles are high-relevance, so
        # they join THIS scan's search pool; alphabet-soup is noisier, so it only feeds
        # the corpus (to be validated by reflux in future scans) rather than spending
        # this scan's search budget. Both also widen the corpus for next time.
        soup: list[tuple[str, str]] = []
        if deep:
            for term, source in self._competitor_terms(store, app_id, country, lang):
                _add(term, source)
            soup = list(self._soup_terms(store, seeds, country, lang))

        # 4) sediment the search pool + soup harvest back into the corpus (non-confirmed).
        if self.keyword_corpus_service is not None:
            items = [(t, source_of.get(t, "seed"), False) for t in pool]
            items += [(n, s, False) for t, s in soup if (n := self._norm(t))]
            self.keyword_corpus_service.record(platform, country, lang, items)

        return pool[:cap]

    def _competitor_terms(self, store, app_id, country, lang):
        """Yield ``(phrase, "similar")`` mined from competitor (similar) app titles —
        phrases real rival apps rank on. Best-effort: ``similar`` raises on failure, but
        the corpus is optional so any error just means no competitor terms this scan."""
        if not app_id:
            return
        try:
            similar = store.similar(app_id, country=country, lang=lang, limit=20)
        except Exception:  # noqa: BLE001 - optional enrichment, never fatal
            return
        for item in similar or []:
            title = getattr(item, "title", "") or ""
            head = re.split(r"[:\-–—|·,，、（(]", title)[0].strip()
            if head:
                yield head, "similar"
            toks = [w for w in self._tokens(title) if w not in _STOPWORDS]
            for first, second in zip(toks, toks[1:]):
                yield f"{first} {second}", "similar"

    def _soup_terms(self, store, seeds, country, lang):
        """Yield ``(suggestion, "soup")`` from alphabet-soup expansion of the strongest
        seeds — append a-z and read autocomplete back, turning the suggest endpoint into
        a much larger keyword generator. Deep-only, bounded by ``SOUP_SEEDS`` (each seed
        ≈ 26 requests). ``store.suggest`` is already best-effort (returns [])."""
        for seed in seeds[: self.SOUP_SEEDS]:
            for letter in self.SOUP_LETTERS:
                for hint in store.suggest(f"{seed} {letter}", country=country, lang=lang, count=8):
                    yield hint, "soup"

    def analyze_coverage(
        self,
        platform: str,
        app_id: str,
        country: str = "us",
        lang: str = "en",
        limit: int = 50,
        max_candidates: int = 120,
        deep: bool = False,
        candidates: list[str] | None = None,
        canonical_app_id: str | None = None,
        proxy_pool=None,
        max_workers: int = 1,
        progress=None,
    ) -> KeywordCoverageResult:
        """For each candidate keyword, search and keep it if the app ranks within
        ``limit``. ``progress(message, fraction)`` is called per keyword if provided.

        Search results carry the store's canonical id (App Store: numeric trackId), so a
        Bundle-ID input would never match them — the match target therefore includes the
        canonical id from ``app_detail``. Callers re-running a scan can pass back both
        ``candidates`` and ``canonical_app_id`` (from the prior result) to skip the
        detail + autocomplete requests entirely.

        Concurrency is gated on a proxy pool: with ``proxy_pool`` set, up to
        ``max_workers`` keywords are searched in parallel, each request leased a proxy so
        the load is spread across IPs. WITHOUT a usable pool the scan stays strictly
        serial regardless of ``max_workers`` — parallelising same-IP scraping just
        multiplies the rate-limit/ban risk, so that combination is refused by design.
        """
        store = self._store(platform)
        has_proxies = proxy_pool is not None and proxy_pool.has_proxies()
        workers = max(1, int(max_workers)) if has_proxies else 1

        canonical = (canonical_app_id or "").strip()
        if candidates is None:
            if progress:
                progress("正在生成候选关键词...", 0.0)
            detail = store.app_detail(app_id, country=country, lang=lang)
            canonical = canonical or str(detail.app_id or "").strip()
            candidates = self._candidates_from_detail(
                store, detail, country, lang, max_candidates=max_candidates,
                deep=deep, platform=platform, app_id=app_id,
            )
        targets = {t for t in (normalize_app_id(app_id), normalize_app_id(canonical)) if t}
        total = len(candidates)

        covered: list[dict] = []
        state = {"done": 0, "failures": 0, "successes": 0}
        lock = threading.Lock()
        stop = threading.Event()

        def scan_one(keyword: str) -> None:
            if stop.is_set():
                return
            rank, ok = self._search_keyword(
                store, keyword, country, lang, limit, targets,
                proxy_pool if has_proxies else None,
            )
            with lock:
                state["done"] += 1
                done = state["done"]
                if ok:
                    state["successes"] += 1
                    if rank is not None:
                        covered.append({"keyword": keyword, "rank": rank})
                else:
                    state["failures"] += 1
                    # Only an opening run of pure failure (network down) aborts the scan;
                    # once anything has succeeded, drop flaky keywords silently.
                    if state["successes"] == 0 and state["failures"] >= self.ABORT_AFTER_FAILURES:
                        stop.set()
            if progress:
                progress(f"覆盖检测 {done}/{total}：{keyword}", done / total if total else 1.0)

        if workers > 1:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                list(executor.map(scan_one, candidates))
        else:
            for keyword in candidates:
                if stop.is_set():
                    break
                scan_one(keyword)

        if stop.is_set() and state["successes"] == 0:
            raise ServiceError(
                f"前 {state['failures']} 个关键词检索均失败，已中止扫描，请检查网络/代理后重试。"
            )

        covered.sort(key=lambda row: row["rank"])
        # confirmed hits are the highest-value seeds for future scans of this locale
        if self.keyword_corpus_service is not None and covered:
            self.keyword_corpus_service.record(
                platform, country, lang,
                [(row["keyword"], "covered", True) for row in covered],
            )
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

    def _search_keyword(self, store, keyword, country, lang, limit, targets, proxy_pool):
        """Search one keyword and return ``(rank_or_None, ok)``. ``ok=False`` means the
        keyword could not be fetched at all (every attempt failed) — distinct from a
        successful search where the app simply didn't rank (rank None, ok True)."""
        if proxy_pool is None:
            try:
                results = store.search(keyword, country=country, lang=lang, limit=limit)
            except Exception:
                return None, False
            return self._rank_of(results, targets), True

        attempts = min(self.MAX_PROXY_ATTEMPTS, len(proxy_pool))
        for _ in range(max(1, attempts)):
            proxy = proxy_pool.lease()
            if proxy is None:
                break  # every proxy cooling down — treat as a fetch failure this round
            try:
                results = store.search(
                    keyword, country=country, lang=lang, limit=limit, proxy=proxy
                )
            except Exception:
                proxy_pool.report_bad(proxy)
                continue
            proxy_pool.report_ok(proxy)
            return self._rank_of(results, targets), True
        return None, False

    @staticmethod
    def _rank_of(results, targets: set[str]) -> int | None:
        for rank, item in enumerate(results, 1):
            if normalize_app_id(getattr(item, "app_id", None)) in targets:
                return rank
        return None

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
