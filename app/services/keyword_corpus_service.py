from __future__ import annotations

import logging

from app.db.repositories import KeywordCorpusRepository

logger = logging.getLogger(__name__)


class KeywordCorpusService:
    """Owns the self-accumulating keyword pool (``keyword_corpus`` table).

    Every coverage scan both FEEDS this pool (``record`` — its candidates, competitor
    terms and soup hits) and READS from it (``candidates`` — relevant rows enrich the
    next scan). So the candidate pool grows richer the more apps in a locale get
    scanned, without any external corpus.

    All methods are best-effort: the corpus is an optional enrichment, so a DB hiccup
    here must NEVER break a coverage scan — failures are swallowed (logged) and degrade
    to "no corpus contribution".
    """

    def __init__(self, database):
        self.database = database
        self.repo = KeywordCorpusRepository()

    def record(
        self,
        platform: str,
        country: str,
        lang: str,
        items: list[tuple[str, str, bool]],
    ) -> int:
        """Sediment a batch of ``(keyword, source, confirmed)`` into the pool."""
        if not items:
            return 0
        try:
            with self.database.session() as session:
                return self.repo.upsert_many(session, platform, country, lang, items)
        except Exception:  # noqa: BLE001 - corpus enrichment is never fatal
            logger.warning("keyword corpus record failed", exc_info=True)
            return 0

    def candidates(
        self,
        platform: str,
        country: str,
        lang: str,
        seed_tokens: set[str],
        limit: int = 80,
    ) -> list[str]:
        """Pull pool keywords RELEVANT to the app being scanned — those sharing at
        least one token with the app's own seed terms — most-relevant first (confirmed
        wins, then recurrence), capped at ``limit``.

        Token overlap is the v1 relevance gate: it reliably surfaces the locale's
        accumulated vocabulary AROUND the app's themes (e.g. a new shopping app inherits
        "ai shopping", "price compare", "cashback"… harvested from earlier shopping-app
        scans) without dragging unrelated terms into the (network-bound) search phase.
        Returns [] on any failure.
        """
        if not seed_tokens:
            return []
        try:
            with self.database.session() as session:
                rows = self.repo.fetch(session, platform, country, lang)
        except Exception:  # noqa: BLE001
            logger.warning("keyword corpus fetch failed", exc_info=True)
            return []
        out: list[str] = []
        for row in rows:
            if set((row.keyword or "").split()) & seed_tokens:
                out.append(row.keyword)
                if len(out) >= limit:
                    break
        return out

    def count(self, platform: str, country: str, lang: str) -> int:
        try:
            with self.database.session() as session:
                return self.repo.count(session, platform, country, lang)
        except Exception:  # noqa: BLE001
            return 0
