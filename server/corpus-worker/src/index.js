// Crowd-sourced keyword corpus for catch-radar (Cloudflare Worker + D1).
//
// Privacy by design: clients send ONLY keywords (+ locale, source, confirmed).
// No app ids, no user ids. The pool is "what search terms exist in this locale",
// never "who scanned what". For abuse control the client IP is SHA-256 hashed
// (salted with the API key) into a short, transient rate-limit counter — the raw
// IP is never stored, and counter rows expire and are swept opportunistically.
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

// --- Rate limiting (per hashed IP) ---
// The shared key is baked into the client, so per-IP throttling is the real abuse
// defense. Limits are generous for honest use but a hard ceiling against floods and
// slow-drip corpus pollution. Counting lives in D1 so it is globally consistent
// (the native binding only counts per-colo). For hard DoS, also add a Cloudflare
// edge Rate Limiting rule in the dashboard — that rejects before the Worker runs.
const RL_BURST_LIMIT = 60; // max requests / minute / IP (every endpoint)
const RL_BURST_PERIOD = 60;
const RL_WRITE_LIMIT = 20000; // max contributed keywords / day / IP
const RL_WRITE_PERIOD = 86400;

function norm(s) {
  return (s == null ? "" : String(s)).trim().toLowerCase().replace(/\s+/g, " ");
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json" },
  });
}

// SHA-256(salt|ip), first 96 bits as hex. One-way + salted so stored buckets can't
// be reversed to an IP; never persist the raw address.
async function ipHash(ip, salt) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(salt + "|" + ip));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 24);
}

// Lazily create the counter table once per isolate (module flag persists across the
// isolate's requests), so a fresh deploy needs no separate migration step.
let rlReady = false;
async function ensureRl(env) {
  if (rlReady) return;
  await env.DB.prepare(
    `CREATE TABLE IF NOT EXISTS rate_limit (
       bucket TEXT PRIMARY KEY, count INTEGER NOT NULL, reset_at INTEGER NOT NULL
     )`
  ).run();
  rlReady = true;
}

// Fixed-window counter: add `inc` to this IP+scope's current window, return the
// running total. Over the limit => caller rejects with 429.
async function rlHit(env, scope, periodSec, inc) {
  const now = Math.floor(Date.now() / 1000);
  const windowId = Math.floor(now / periodSec);
  const resetAt = (windowId + 1) * periodSec;
  const row = await env.DB.prepare(
    `INSERT INTO rate_limit (bucket, count, reset_at) VALUES (?, ?, ?)
     ON CONFLICT(bucket) DO UPDATE SET count = count + excluded.count
     RETURNING count`
  )
    .bind(`${scope}|${windowId}`, inc, resetAt)
    .first();
  return (row && row.count) || inc;
}

export default {
  async fetch(request, env, ctx) {
    // Shared-secret gate (keyless traffic is rejected here, never touching D1).
    if (env.API_KEY && request.headers.get("x-api-key") !== env.API_KEY) {
      return json({ error: "unauthorized" }, 401);
    }
    const url = new URL(request.url);
    try {
      const idh = await ipHash(
        request.headers.get("CF-Connecting-IP") || "0.0.0.0",
        env.API_KEY || "catch_radar"
      );
      await ensureRl(env);
      // Opportunistic sweep of expired windows (non-blocking, ~2% of requests).
      if (Math.random() < 0.02) {
        const now = Math.floor(Date.now() / 1000);
        ctx.waitUntil(env.DB.prepare(`DELETE FROM rate_limit WHERE reset_at < ?`).bind(now).run());
      }
      // Per-IP burst ceiling on every endpoint — short-circuits before any heavy query.
      if ((await rlHit(env, `${idh}|b`, RL_BURST_PERIOD, 1)) > RL_BURST_LIMIT) {
        return json({ error: "rate limited" }, 429);
      }

      if (request.method === "POST" && url.pathname === "/contribute") {
        return await contribute(request, env, idh);
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

async function contribute(request, env, idh) {
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

  // Per-IP daily volume cap — blunts slow-drip corpus pollution.
  if ((await rlHit(env, `${idh}|w`, RL_WRITE_PERIOD, batch.size)) > RL_WRITE_LIMIT) {
    return json({ error: "daily write limit" }, 429);
  }

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
