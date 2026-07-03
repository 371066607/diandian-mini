from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request

from app.db.repositories import KeywordCorpusRepository

logger = logging.getLogger(__name__)

# --- Shared (crowd-sourced) corpus backend ----------------------------------
# A Cloudflare Worker + D1 endpoint shared by ALL clients (see server/corpus-worker).
# When CORPUS_API_URL is set, every scan also READS candidates from / CONTRIBUTES
# keywords to this shared pool, so the corpus grows with the whole user base — not just
# this one machine. Empty (the default) = pure local mode. Only keywords + locale +
# source + confirmed are ever sent; never an app id or any user identifier.
# No default remote endpoint: the backend retired the shared external corpus service
# in favor of a local seed (see modular-go-backend commits 87c1b7e/6682734), so this
# stays local-only unless an operator explicitly points CATCH_RADAR_CORPUS_URL at a
# service they control (e.g. a local `wrangler dev` instance during development).
CORPUS_API_URL = os.environ.get("CATCH_RADAR_CORPUS_URL", "")
CORPUS_API_KEY = os.environ.get("CATCH_RADAR_CORPUS_KEY", "")
_REMOTE_TIMEOUT = 6.0  # seconds; best-effort — a slow/absent backend never blocks a scan


class KeywordCorpusService:
    """Owns the keyword pool that enriches coverage scans, over two best-effort layers:

      • LOCAL  — the ``keyword_corpus`` SQLite table (offline cache + write buffer).
      • REMOTE — a shared Cloudflare Worker + D1 pool (``CORPUS_API_URL``), so
        discoveries pool across the whole user base.

    Reads merge the shared pool over local; writes go to both. Any failure here — a DB
    hiccup or the network — must NEVER break a coverage scan, so everything is swallowed
    (logged) and degrades to "no corpus contribution".
    """

    def __init__(self, database):
        self.database = database
        self.repo = KeywordCorpusRepository()

    # --- remote backend (best-effort) ---------------------------------------

    def _remote(self, method: str, path: str, params=None, payload=None):
        """Call the shared corpus Worker. Returns parsed JSON, or None on any failure
        (or when no backend is configured)."""
        if not CORPUS_API_URL:
            return None
        url = CORPUS_API_URL.rstrip("/") + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("content-type", "application/json")
        # Cloudflare 403s the default "Python-urllib/x" UA as a bot — present a normal
        # one so the corpus calls get through (curl/browsers are fine, urllib isn't).
        req.add_header("user-agent", "CatchRadar-corpus/1.0")
        if CORPUS_API_KEY:
            req.add_header("x-api-key", CORPUS_API_KEY)
        try:
            with urllib.request.urlopen(req, timeout=_REMOTE_TIMEOUT) as resp:
                return json.loads(resp.read() or b"{}")
        except Exception:  # noqa: BLE001 - remote corpus is optional, never fatal
            return None

    # --- write --------------------------------------------------------------

    def record(
        self,
        platform: str,
        country: str,
        lang: str,
        items: list[tuple[str, str, bool]],
    ) -> int:
        """Sediment a batch of ``(keyword, source, confirmed)`` into the local pool and
        (best-effort) the shared remote pool. Returns the NEW-locally-added count."""
        if not items:
            return 0
        added = 0
        try:
            with self.database.session() as session:
                added = self.repo.upsert_many(session, platform, country, lang, items)
        except Exception:  # noqa: BLE001
            logger.warning("keyword corpus record failed", exc_info=True)

        # Contribute to the shared pool — but SKIP unconfirmed alphabet-soup: it's noisy
        # speculation only useful as a LOCAL reflux seed. Keeping it out keeps the shared
        # pool high-signal (confirmed hits + real autocomplete / competitor / seed words).
        if CORPUS_API_URL:
            remote_items = [
                {"keyword": k, "source": s, "confirmed": bool(c)}
                for k, s, c in items
                if c or s != "soup"
            ]
            if remote_items:
                self._remote(
                    "POST",
                    "/contribute",
                    payload={
                        "platform": platform,
                        "country": country,
                        "lang": lang,
                        "items": remote_items,
                    },
                )
        return added

    # --- read ---------------------------------------------------------------

    def candidates(
        self,
        platform: str,
        country: str,
        lang: str,
        seed_tokens: set[str],
        limit: int = 80,
    ) -> list[str]:
        """Relevant pool keywords (those sharing a token with the app's seeds), the
        shared pool first then local, deduped and capped at ``limit``. Token overlap is
        the relevance gate. Returns [] on total failure."""
        if not seed_tokens:
            return []
        merged: list[str] = []
        seen: set[str] = set()
        for kw in (
            *self._remote_candidates(platform, country, lang, seed_tokens, limit),
            *self._local_candidates(platform, country, lang, seed_tokens, limit),
        ):
            if kw and kw not in seen:
                seen.add(kw)
                merged.append(kw)
                if len(merged) >= limit:
                    break
        return merged

    def _remote_candidates(self, platform, country, lang, seed_tokens, limit) -> list[str]:
        if not CORPUS_API_URL:
            return []
        resp = self._remote(
            "GET",
            "/candidates",
            params={
                "platform": platform,
                "country": country,
                "lang": lang,
                "tokens": ",".join(sorted(seed_tokens)),
                "limit": limit,
            },
        )
        kws = resp.get("keywords") if isinstance(resp, dict) else None
        return [k for k in kws if isinstance(k, str)] if isinstance(kws, list) else []

    def _local_candidates(self, platform, country, lang, seed_tokens, limit) -> list[str]:
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
