// Crowd-sourced keyword corpus for 点点数据 Mini (Cloudflare Worker + D1).
//
// Privacy by design: clients send ONLY keywords (+ locale, source, confirmed).
// No app ids, no user ids, no IP storage — the pool is "what search terms exist in
// this locale", never "who scanned what".
//
// Endpoints (all require header `x-api-key` when the API_KEY secret is set):
//   POST /contribute  {platform,country,lang,items:[{keyword,source,confirmed}]}
//   GET  /candidates?platform=&country=&lang=&tokens=a,b,c&limit=80  -> {keywords:[...]}
//   GET  /stats?platform=&country=&lang=                              -> {count:N}

const MAX_ITEMS = 500; // per /contribute request
const KW_MIN = 2;
const KW_MAX = 50;
const FETCH_CAP = 3000; // rows scanned for token-overlap per /candidates call
const DEFAULT_LIMIT = 80;
const MAX_LIMIT = 300;

function norm(s) {
  return (s == null ? "" : String(s)).trim().toLowerCase().replace(/\s+/g, " ");
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json" },
  });
}

export default {
  async fetch(request, env) {
    // Shared-secret gate. Baked into the client — raises the bar against drive-by
    // abuse; not Fort Knox. Pair with a Cloudflare Rate Limiting rule in production.
    if (env.API_KEY && request.headers.get("x-api-key") !== env.API_KEY) {
      return json({ error: "unauthorized" }, 401);
    }
    const url = new URL(request.url);
    try {
      if (request.method === "POST" && url.pathname === "/contribute") {
        return await contribute(request, env);
      }
      if (request.method === "GET" && url.pathname === "/candidates") {
        return await candidates(url, env);
      }
      if (request.method === "GET" && url.pathname === "/stats") {
        return await stats(url, env);
      }
      return json({ error: "not found" }, 404);
    } catch (e) {
      return json({ error: String((e && e.message) || e) }, 500);
    }
  },
};

async function contribute(request, env) {
  const body = await request.json().catch(() => null);
  if (!body || typeof body !== "object") return json({ error: "bad json" }, 400);

  const platform = norm(body.platform) || "google_play";
  const country = norm(body.country) || "us";
  const lang = norm(body.lang) || "en";
  const items = Array.isArray(body.items) ? body.items.slice(0, MAX_ITEMS) : [];

  // Collapse + validate: dedupe by keyword, keep the strongest confirmed flag.
  const batch = new Map();
  for (const it of items) {
    const kw = norm(it && it.keyword);
    if (kw.length < KW_MIN || kw.length > KW_MAX) continue;
    const prev = batch.get(kw);
    batch.set(kw, {
      source: (prev && prev.source) || norm(it && it.source) || "client",
      confirmed: (it && it.confirmed ? 1 : 0) || (prev ? prev.confirmed : 0),
    });
  }
  if (batch.size === 0) return json({ accepted: 0 });

  const now = new Date().toISOString();
  const stmt = env.DB.prepare(
    `INSERT INTO keyword_corpus
       (platform, country, lang, keyword, source, confirmed, hit_count, first_seen_at, last_seen_at)
     VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
     ON CONFLICT(platform, country, lang, keyword) DO UPDATE SET
       hit_count    = hit_count + 1,
       last_seen_at = excluded.last_seen_at,
       confirmed    = MAX(confirmed, excluded.confirmed)`
  );
  const ops = [];
  for (const [kw, v] of batch) {
    ops.push(stmt.bind(platform, country, lang, kw, v.source, v.confirmed, now, now));
  }
  await env.DB.batch(ops);
  return json({ accepted: batch.size });
}

async function candidates(url, env) {
  const p = url.searchParams;
  const platform = norm(p.get("platform")) || "google_play";
  const country = norm(p.get("country")) || "us";
  const lang = norm(p.get("lang")) || "en";
  const tokens = new Set(norm(p.get("tokens")).split(/[ ,]+/).filter(Boolean));
  let limit = parseInt(p.get("limit") || String(DEFAULT_LIMIT), 10);
  if (!Number.isFinite(limit) || limit <= 0) limit = DEFAULT_LIMIT;
  limit = Math.min(limit, MAX_LIMIT);
  if (tokens.size === 0) return json({ keywords: [] });

  // Index-ordered top slice (confirmed, then recurrence), then token-overlap filter
  // in JS — mirrors the client's relevance gate so the shared pool surfaces the
  // locale's vocabulary AROUND this app's themes without dragging in unrelated terms.
  const rows = await env.DB.prepare(
    `SELECT keyword FROM keyword_corpus
     WHERE platform = ? AND country = ? AND lang = ?
     ORDER BY confirmed DESC, hit_count DESC, last_seen_at DESC
     LIMIT ?`
  )
    .bind(platform, country, lang, FETCH_CAP)
    .all();

  const out = [];
  for (const r of rows.results || []) {
    const kw = r.keyword || "";
    if (kw.split(" ").some((t) => tokens.has(t))) {
      out.push(kw);
      if (out.length >= limit) break;
    }
  }
  return json({ keywords: out });
}

async function stats(url, env) {
  const p = url.searchParams;
  const platform = norm(p.get("platform")) || "google_play";
  const country = norm(p.get("country")) || "us";
  const lang = norm(p.get("lang")) || "en";
  const row = await env.DB.prepare(
    `SELECT COUNT(*) AS n FROM keyword_corpus WHERE platform = ? AND country = ? AND lang = ?`
  )
    .bind(platform, country, lang)
    .first();
  return json({ count: (row && row.n) || 0 });
}
