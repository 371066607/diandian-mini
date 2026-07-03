# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project

catch-radar (CatchRadar) — a PySide6/QML desktop client for viewing and tracking app-store
intelligence (Google Play + App Store): app details, reviews, ranking charts, keyword ranks,
keyword-coverage analysis, and tracked-app/keyword monitoring with alerts. UI strings, log
messages, and error text are in Chinese.

**Two modes, decided once at startup** (`app/composition.py:_store_intel_api_url()`):
- **API mode (default).** The desktop client is a thin client: `app/services/store_intel_api_client.py`
  is the *only* data path, talking REST to the Go backend's CatchRadar module
  (`internal/project/catchradar/` in the sibling repo `/Volumes/DevSpace/services/modular-go-backend`).
  The backend owns MySQL (source of truth), scraping, scheduling, and the Redis-backed refresh-job
  queue. Contract: `FRONTEND_AGENT_API.md`. Source-run (not a packaged/frozen build) with no env vars
  set defaults to the local dev backend `http://127.0.0.1:8081`, never production — set
  `CATCH_RADAR_STOREINTEL_API_URL` explicitly to point elsewhere (packaged builds default to
  production `https://catchradar.meshub.ai`).
- **Legacy/offline mode**, explicit opt-in only (`CATCH_RADAR_LEGACY_LOCAL_MODE=true` or
  `CATCH_RADAR_OFFLINE_MODE=true`), only reachable via the `--widgets` (legacy Qt Widgets UI)
  flag. **This path is frozen AND its live-network write capability has been retired** (P1-5
  Phase 2): it can still fetch app details/reviews/charts via `google_play_scraper`/`gplay_scraper`
  library calls and display already-synced local SQLite history, but every action that used to
  scrape-then-persist (save a snapshot, save reviews, sync a tracked app/keyword/chart-rank now,
  search, fetch similar apps) now raises a clean `ServiceError` the moment it's invoked — see
  "Scraping layer" and "Sync, scheduling & alerts" below for exactly what still works vs. what's a
  stub now.

## Commands

```bash
# Setup (Python 3.12)
python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

python main.py                 # run the GUI app (QML by default, API mode)
python main.py --smoke-test    # init DB + services, print "smoke-ok", exit (no GUI — use for CI / headless checks)
python main.py --widgets       # legacy Qt Widgets UI — only starts in legacy/offline mode

pytest                                                         # all tests
pytest -m "not legacy"                                         # skip the frozen legacy-path tests
pytest tests/test_tracking_service.py                          # one file
pytest tests/test_tracking_service.py::test_sync_keyword_now_persists_history_and_sync_time  # one test

ruff check .        # lint (line-length 100, target py312)
ruff format .       # format

pyinstaller --noconfirm --windowed --name CatchRadar main.py   # package desktop binary (see CatchRadar.spec for the real build)
```

`pyproject.toml` sets `pythonpath = ["."]` so tests import `app.*` without installation. The
`legacy` pytest marker (also in `pyproject.toml`) tags tests that only exercise the frozen
legacy/offline path (`google_play_service.py` scraping, full local SQLite migrations).

## Architecture

```
UI: app/qml/*.qml + app/ui/qml_bridge.py bridge (default)  /  app/ui/main_window.py + app/ui/pages/* (legacy --widgets only)
  → Services (app/services — domain services: tracking/chart/keyword/review/alert/settings/...)
    → StoreIntelApiClient → Go backend REST API   (API mode, the default data path)
      — or, legacy/offline mode only —
    → Repositories (app/db/repositories.py) + GooglePlayService (scraping)
      → Models (app/db/models.py — SQLAlchemy ORM)
```

**Composition root — `app/composition.py:build_services()`** (the thin `main.py` launcher just
imports and calls it — this name/signature is a hard constraint, see "Runtime data & migrations").
Internally it dispatches to `build_api_services(database)` (settings/store-intel-client/
monetization/update — always constructed) and, only when `not store_intel_api_client.enabled`,
additionally `build_legacy_services(database, shared)` (google_play/app_store scrapers, and every
service that wraps one — `keyword_service`, `keyword_coverage_service`, `chart_rank_service`,
`review_service`, `chart_service`, `tracking_service`, `history_retention_service`, `alert_service`,
`export_service`). **API mode no longer constructs any of the legacy-only services at all** — the
`services` dict simply won't have those keys, so any code path that unconditionally indexes
`services["tracking_service"]` (etc.) outside an `if api is not None: return ... else: <legacy>`
guard will now raise `KeyError` in API mode by design (a real bug if it ever fires — every such
access in `qml_bridge.py`/controllers is gated; only the legacy `--widgets` pages index these
directly, and `main.py` refuses to start `--widgets` when API mode is enabled). `scheduler` is
constructed last in `build_services()` (`RemoteSchedulerProxy` for API mode, `AppScheduler` for
legacy) since it needs to know which branch ran. Every service is constructed once, collaborators
injected via constructors; the resulting `services` dict is handed to the QML bridge (or
`MainWindow` in `--widgets` mode). There is no global/singleton service locator; add new services
in `build_api_services`/`build_legacy_services` as appropriate and thread them through. Composition
lives under `app/` (NOT `main.py`) on purpose: the hot-patch overlays a downloaded `app/` onto
`sys.path` but never re-runs the bundled `main.py`, so a newly-added service only reaches existing
users via a code patch if it's registered here.

**QML bridge (`app/ui/qml_bridge.py`, ~1800 lines, down from 3781).** A single `QObject`
aggregating `@Slot`/`@Property` members across every domain (search/detail/reviews/charts/
keywords/coverage/tracking/dashboard/alerts/settings), plus shared infrastructure used across
domains (`_run` async dispatch, `_store_intel_api`, `_request_api_refresh`, `_monitor_target` input
validation). Each slot delegates to the matching domain service from `composition.py` — API mode
vs. legacy mode is decided once, centrally, when `build_services()` constructs those services, not
by per-slot branching (`_api_mode_enabled()` is checked in exactly one place).

The decomposition into `app/ui/controllers/*` is **complete** (aggregate-root pattern: QmlBridge
keeps every Signal/Slot/Property QML binds to, unchanged; slot bodies became thin shims into plain
Python controller classes that hold the actual domain logic). Extracted: `ApiLogController`,
`SettingsController`, `AlertController`, `ReviewController`, `ChartController`,
`KeywordController`, `DetailController`, `SearchController`, `CoverageController`,
`TrackingController` (all mutation CRUD: add/toggle/remove/sync/set-frequency/set-tag for tracked
apps/keywords/chart-apps), and `DashboardController` (read/aggregation side: `monitorTree`,
`monitorSeries`, dashboard summary, tracking list, history — the last domain extracted; needs a
`bridge` reference for `_store_intel_api`, `services`, `database`/repositories, and the
`_history_selection` state it mutates directly as `self.bridge._history_selection`) — plus
`app/ui/formatting.py`, a module of pure display-formatting functions (`fmt_count`, `short_time`,
`review_row`, `alert_row`, etc.) that were previously duplicated-by-sharing across domains as
private QmlBridge methods (e.g. `fmt_count` is used by both search results and the detail page).
Some controllers (`DetailController`, `SearchController`, `CoverageController`,
`TrackingController`) additionally export domain-local pure functions (`dev_links`,
`has_search_display_data`, `has_coverage_cache_data`, `split_monitor_chart_key`, `is_valid_app_id`,
etc.) that stayed with the domain rather than moving to `formatting.py`, since — unlike
`fmt_count` — nothing outside that one domain uses them. Two collaborator shapes exist — pick based
on what the logic needs:
- **`services`-only** (`SettingsController`, `AlertController`, `KeywordController` for its
  legacy-mode path): construct with `self.services`, no bridge reference needed.
- **`bridge`-reference** (`ReviewController`, `ChartController`, `KeywordController`'s API-mode
  path, `DetailController`, `SearchController`, `CoverageController`, `TrackingController`,
  `DashboardController`): construct with `self` (the bridge), used when the logic needs the shared
  `_store_intel_api`/`_request_api_refresh`/`_active_store` helpers many domains call into (or, for
  `CoverageController`, the `coverageProgress` signal — the only domain with inline scan-progress
  reporting; or, for `DashboardController`, direct read/write of bridge state like
  `_history_selection` and the `database`/repository attributes).

What's left in `qml_bridge.py` is genuinely bridge-owned: the Slot/Property surface itself, `_run`
async dispatch, per-domain UI state (`_dashboard`, `_tracking`, `_history`, etc.) and its
`_set_*`/`*Changed` setters, cross-domain broadcast (`_after_mutation` refreshing five pages at
once), and `_monitor_target` (shared input validation that emits `errorMessage`, used by five
different mutation slots). Read the whole file, not just the slot you're touching, before assuming
a helper is domain-local; grep every helper's call sites before moving it (several "domain" helpers
turned out to be shared and belonged in `formatting.py` instead of a single controller — that was
true for roughly half of what looked domain-specific at first glance). Follow
`app/ui/controllers/tracking_controller.py` or `dashboard_controller.py` as the reference example
for any future controller work, and add tests before extracting — most slots (`saveSettings`,
`apiLogs`, `saveReviews`, `saveChartSnapshot`) had zero direct test coverage before being
extracted, and legacy/offline-mode branches across several domains had none either despite heavy
API-mode coverage; check coverage exists for whatever you're about to move, and add it if it
doesn't. If a controller method has a real wait loop (`CoverageController.refresh_api_cache`'s 30s
polling), its test must monkeypatch `time.sleep`/`time.monotonic` rather than actually waiting —
caught late once, cost a slow test.

**Auth & token refresh (API mode).** `StoreIntelApiClient` starts unauthenticated; a 401 triggers
guest login (`POST /api/auth/guest`) on first use. Once a session exists, a later 401 prefers
refreshing it (`POST /api/auth/refresh`) over a fresh guest login, falling back to guest login only
if refresh fails or no refresh token is held (`_reauthenticate`, epoch-counter + lock so concurrent
401s from parallel requests only trigger one real re-auth call).

**DB session ownership (legacy mode).** `Database` (`app/db/database.py`) exposes
`with database.session() as session:` — a contextmanager that commits on success, rolls back on
exception, always closes (`expire_on_commit=False`). **Services open sessions; repositories never
do.** In API mode the local SQLite DB is still opened and migrated at startup, but business data
mostly bypasses it — it's used for settings/device-id storage and the legacy diagnostic path only.

**Identity tuple.** Almost every entity is keyed by `(platform, app_id, country, lang)`. `platform`
is `"google_play"` or `"app_store"`.

### Async UI pattern (critical)

QML (default): bridge slots that do network/blocking work run it off the Qt UI thread and emit
signals (`*Changed`, `statusMessage`, `errorMessage`) back on the UI thread when done — never
block directly in a `@Slot`. Legacy `--widgets` mode: `BasePage.run_task(loading_text, fn,
on_success)` wraps `fn` in a `Worker` (`QRunnable`, `app/utils/worker.py`) dispatched to
`QThreadPool.globalInstance()`; the sibling `BasePage.run_background(fn, on_success)` is the same
pattern without the loading overlay, for cheap frequent local-DB refreshes. This whole class of
pages/widgets is exercised only via `--widgets` in legacy/offline mode.

### Scraping layer (`app/services/google_play_service.py`) — FROZEN, legacy mode only, write path retired

Only reached in legacy/offline mode. The Go backend
(`internal/project/catchradar/upstream/googleplay`) is the real, maintained scraper for the
product path. As of P1-5 Phase 2, this file's custom raw-scraping code (the Google `batchexecute`
RPC for charts, the `curl` subprocess fallback in `_request_text`, and every raw-DOM-HTML regex
parser) has been deleted outright — not just deprioritized. What's left:
- `search()`, `similar()`, `chart()` are now thin stubs: `raise ServiceError(_FEATURE_RETIRED_MESSAGE)`
  unconditionally. Neither had a working non-DOM implementation (search/similar never did; a code
  comment on the old `search()` documented that the `google_play_scraper` library path was known
  broken against current Play Store responses, DOM was never a "fallback"), so retiring the DOM
  code meant retiring the feature, not just narrowing it — deliberate, see git history for the
  P1-5 Phase 2 decision.
- `app_detail()`, `reviews()`, `permissions()`, `list_analyze()`, `suggest()`, `configure()` are
  untouched and still fully functional — they're real `google_play_scraper`/`gplay_scraper`
  library calls, not custom scraping code. `app_detail()` lost only its optional DOM-enrichment
  step for extra fields when the library response was incomplete.
- `suggest_nested()` was deleted outright (confirmed zero production callers).
- If you need to add scraping capability back for local diagnostics, this is the file — but check
  first whether the Go backend can serve it instead; this file's whole reason to exist is that the
  backend is the source of truth.

**Do not treat "raises ServiceError" as "needs fixing."** Every caller of the retired methods
(`KeywordService.search`/`rank`, `ChartRankService._fetch_chart`'s fallback, `search_controller.py`,
`app_search_page.py`, `app_detail_page.py`) already has error-handling for `ServiceError` — that's
the intended UX: a clean "该功能已下线，请使用在线（API）模式。" message, not a silent no-op or a
raw crash.

### Sync, scheduling & alerts

**API mode:** `RemoteSchedulerProxy` (`app/jobs/scheduler.py`) replaces the local scheduler — the
backend owns cron scheduling and scraping entirely. The desktop client only triggers
`sync_all`/`request_refresh` calls and polls refresh-job status
(`StoreIntelApiClient.wait_refresh_job`, terminal states: `completed`, `failed`, `dead`).

**Legacy mode — sync is retired (P1-5 Phase 2).** `TrackingService.sync_app_now()`,
`sync_keyword_now()`, `sync_chart_now()` are now stubs that immediately
`raise ServiceError(_FEATURE_RETIRED_MESSAGE)` — the old fetch-then-persist-then-alert-diff
routine (and `AlertService.create_snapshot_alerts`/`create_keyword_alerts`/`create_chart_alerts`/
`record_fetch_failure`/`record_fetch_recovered`/`create_review_alerts`, all deleted along with the
`NewAlert` dataclass) only existed to persist freshly-scraped content, and the write path it fed is
gone (`SnapshotRepository`/`KeywordRankRepository`/`ChartRankRepository`'s `upsert_for_day`,
`AlertRepository.create`, `ReviewRepository.save_reviews`, the whole `ChartRepository` class, and
`TrackingRepository`'s sync-bookkeeping writes are all deleted from `app/db/repositories.py`).
`sync_all_apps`/`sync_all_keywords`/`sync_all_charts`/`sync_all` are unchanged and still callable —
each already wrapped its per-item `sync_*_now` call in try/except-log-and-skip, so they now
correctly report 0 synced with a logged failure per item instead of crashing; this is intended, not
a regression to chase. `AppScheduler` still runs `sync_tracked_job` on its daily `CronTrigger`
(gated by `scheduler_enabled`) — it will keep firing and logging a no-op failure daily; disabling
the scheduler entirely for legacy installs was out of scope for this pass. `AlertService` keeps
only its read/mark-read-state surface (`unread_count`, `mark_all_read`, `recent_alerts`,
`list_alerts`, `distinct_alert_apps`, `mark_read`) — no new alerts are ever created going forward,
but previously-synced ones remain viewable. `HistoryRetentionService.cleanup()` is now an
unconditional no-op returning an all-zero dict (nothing writes new rows, so nothing needs pruning).
`TrackingService.monitor_overview()`/`get_history()`/`history_with_diffs()` are untouched — pure
reads over already-synced local data. `ReviewService.save()`/`monitor_reviews()`,
`ChartService.save()`, `KeywordService.save_result()`, `ChartRankService.save_result()` are all
stubs too (same reasoning, same `ServiceError` pattern) — their sibling read/fetch methods
(`ReviewService.fetch`/`list_cached`, `ChartService.fetch`, `KeywordService.search`/`rank`'s
fetch step, `ChartRankService._fetch_chart`) are untouched.

### Settings

Both modes read/write through `SettingsService`; `DEFAULT_SETTINGS` (`app/constants.py`) is the
fallback. `StoreIntelApiClient` exposes `enabled` (bool) and `api_url` (str, the configured base
URL) properties — useful for a "connected to: ..." UI indicator so it's visible which environment
is active. In legacy mode, `SettingsFormWidget` is also the path that applies `proxy` settings
(`network.apply_proxy_env`) and retunes `GooglePlayService.configure`.

## Runtime data & migrations

- SQLite DB at `data/catch_radar.sqlite3`; logs in `data/logs/`. `config.ensure_runtime_dirs()`
  creates these at startup. Opened and migrated in both modes, but only meaningfully written to in
  legacy mode.
- `app/db/migrations.py:migrate()` (run at startup from `main.py`) calls `create_all()` for missing
  tables, then **additively** adds any missing columns via `ALTER TABLE ... ADD COLUMN`. Best-effort
  per column; only ever *adds* — renames/retypes/drops need manual handling.
- `main.py`'s imports of `app.composition`, `app.db.database`, `app.db.migrations` are a hard
  constraint of the hot-patch mechanism (`bootstrap.py` overlays a downloaded `app/` onto
  `sys.path` but never re-runs the bundled `main.py`) — their module paths and top-level function
  signatures must stay stable across releases.

## Testing conventions

- API-mode HTTP tests spin up a real local `http.server` fixture (`api_server` in
  `tests/test_store_intel_api_client.py`) rather than mocking `urllib` — see that file for the
  request/response fixture pattern, including the guest-login/token-refresh 401 flows.
- Legacy-mode DB tests isolate with `Database(str(tmp_path / "x.sqlite3"))` + `create_all()`
  (pytest `tmp_path` fixture); no shared DB, no network. Tagged `@pytest.mark.legacy` — see
  `tests/test_migrations.py`, `tests/test_chart_migration.py`,
  `tests/test_google_play_service.py`, `tests/test_google_play_config.py`.
- The scraper's raw-DOM/RPC parsers (`_parse_search_dom`, `_parse_similar_cards`,
  `_parse_chart_response`, etc.) were deleted along with the write path they fed (P1-5 Phase 2) —
  don't reintroduce `object.__new__(GooglePlayService)`-style direct-parser tests for them; test
  `search()`/`similar()`/`chart()` by asserting they raise `ServiceError`
  (`app.services.google_play_service._FEATURE_RETIRED_MESSAGE`) instead.
- When a test's fixture used to seed rows via a now-deleted repository write method (e.g.
  `AlertRepository.create`, `SnapshotRepository.upsert_for_day`), seed the ORM model directly
  instead (`app/db/models.py`) — see `_add_alert`/`_seed_keyword_rank`/`_seed_chart_rank`-style
  helpers across `tests/test_alert_service.py`, `tests/test_alerts_page.py`,
  `tests/test_gui_smoke.py` for the established pattern.
