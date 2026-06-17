-- Crowd-sourced keyword corpus (shared across all 点点数据 Mini clients).
-- Stores ONLY keywords per locale — never app ids or any user identifier — so the
-- pool is "what search terms exist in this locale", not "who scanned what".
CREATE TABLE IF NOT EXISTS keyword_corpus (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  platform      TEXT NOT NULL DEFAULT 'google_play',
  country       TEXT NOT NULL DEFAULT 'us',
  lang          TEXT NOT NULL DEFAULT 'en',
  keyword       TEXT NOT NULL,
  source        TEXT,                         -- seed / autocomplete / similar / covered
  confirmed     INTEGER NOT NULL DEFAULT 0,   -- 1 = a client verified it as a real coverage hit
  hit_count     INTEGER NOT NULL DEFAULT 1,   -- how many contributions have surfaced it
  first_seen_at TEXT NOT NULL,
  last_seen_at  TEXT NOT NULL,
  UNIQUE (platform, country, lang, keyword)
);

-- Covers the candidates() read: WHERE (platform,country,lang) + full ORDER BY
-- (confirmed, hit_count, last_seen_at) → reverse index walk + LIMIT, no sort.
CREATE INDEX IF NOT EXISTS ix_corpus_fetch
  ON keyword_corpus (platform, country, lang, confirmed, hit_count, last_seen_at);
