# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
  `CATCH_RADAR_OFFLINE_MODE=true`): bypasses the backend entirely, using local SQLite +
  `app/services/google_play_service.py` for scraping, and only reachable via the `--widgets`
  (legacy Qt Widgets UI) flag. **This path is frozen** — kept for local diagnostics, not the
  product path, not maintained for new stores/features (see "Scraping layer" below).

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
imports and calls it). Every service is constructed once here and collaborators are injected via
constructors. The resulting `services` dict is handed to the QML bridge (or `MainWindow` in
`--widgets` mode), which passes it down to every page/slot. There is no global/singleton service
locator; add new services here and thread them through. It lives under `app/` (NOT `main.py`) on
purpose: the hot-patch overlays a downloaded `app/` onto `sys.path` but never re-runs the bundled
`main.py`, so a newly-added service only reaches existing users via a code patch if it's
registered here.

**QML bridge (`app/ui/qml_bridge.py`, ~3400 lines and shrinking).** A single `QObject`
aggregating `@Slot`/`@Property` members across every domain (search/detail/reviews/charts/
keywords/coverage/tracking/alerts/settings), plus private helpers — some domain-specific, some
shared infrastructure used across domains (`_run` async dispatch, `_store_intel_api`,
`_request_api_refresh`, `_monitor_*` tree/series helpers spanning tracking+keyword+chart). Each
slot delegates to the matching domain service from `composition.py` — API mode vs. legacy mode is
decided once, centrally, when `build_services()` constructs those services, not by per-slot
branching (`_api_mode_enabled()` is checked in exactly one place).

A decomposition into `app/ui/controllers/*` is underway (aggregate-root pattern: QmlBridge keeps
every Signal/Slot/Property QML binds to, unchanged; slot bodies become thin shims into plain
Python controller classes that hold the actual domain logic). Extracted so far:
`ApiLogController`, `SettingsController`, `AlertController`, `ReviewController`,
`ChartController`, `KeywordController` — plus `app/ui/formatting.py`, a module of pure
display-formatting functions (`fmt_count`, `short_time`, `review_row`, `alert_row`, etc.) that
were previously duplicated-by-sharing across domains as private QmlBridge methods (e.g.
`fmt_count` is used by both search results and the detail page). Two collaborator shapes exist —
pick based on what the logic needs:
- **`services`-only** (`SettingsController`, `AlertController`, `KeywordController` for its
  legacy-mode path): construct with `self.services`, no bridge reference needed.
- **`bridge`-reference** (`ReviewController`, `ChartController`, `KeywordController`'s API-mode
  path): construct with `self` (the bridge), used when the logic needs the shared
  `_store_intel_api`/`_request_api_refresh` helpers that many domains call into.

Remaining on `QmlBridge` directly: search, detail, coverage, and tracking/monitor. These are the
hardest slice — `_monitor_tree`/`_monitor_series` alone span tracking+keyword+chart formatting,
and detail page assembly pulls in reviews, alerts, and coverage data. Read the whole file, not
just the slot you're touching, before assuming a helper is domain-local; grep every helper's call
sites before moving it (several "domain" helpers turned out to be shared and belonged in
`formatting.py` instead of a single controller). Follow `app/ui/controllers/chart_controller.py`
or `review_controller.py` as the reference example for bridge-coupled domains, and add tests
before extracting — most of these slots (`saveSettings`, `apiLogs`, `saveReviews`,
`saveChartSnapshot`) had zero direct test coverage before being extracted; check coverage exists
for whatever you're about to move, and add it if it doesn't.

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

### Scraping layer (`app/services/google_play_service.py`) — FROZEN, legacy mode only

Only reached in legacy/offline mode. The Go backend
(`internal/project/catchradar/upstream/googleplay`) is the real, maintained scraper for the
product path — **fix Google Play page-structure regressions there, not here.** This file is kept
for local diagnostics; only patch it for diagnostic-mode-breaking regressions, not new features.
Implementation notes if you do touch it:
- Charts use Google's `batchexecute` RPC with a gzipped+base64 request-body template
  (`_CHART_BODY_TEMPLATE_B64`), then walk deeply-nested JSON via `_get_in(data, [path])`.
- Search / similar-apps / detail-enrichment have raw-DOM-HTML regex fallbacks when the library
  path fails.
- `_request_text` falls back to a `curl` subprocess when `urllib` fails; `_run_with_retry` adds
  backoff.
- All failures raise `ServiceError` carrying a user-facing Chinese message from `app/constants.py`.

### Sync, scheduling & alerts

**API mode:** `RemoteSchedulerProxy` (`app/jobs/scheduler.py`) replaces the local scheduler — the
backend owns cron scheduling and scraping entirely. The desktop client only triggers
`sync_all`/`request_refresh` calls and polls refresh-job status
(`StoreIntelApiClient.wait_refresh_job`, terminal states: `completed`, `failed`, `dead`).

**Legacy mode:** `TrackingService.sync_app_now()` is the core routine: fetch detail → load
previous snapshot → upsert tracked app → save new snapshot → update sync time →
`AlertService.create_snapshot_alerts(previous, current)` diffs old vs new to emit alerts.
`AppScheduler` (APScheduler `BackgroundScheduler`) runs `sync_tracked_job` on a daily
`CronTrigger`, gated by `scheduler_enabled`. `daily_sync_time` parsing never raises — a malformed
value falls back to `09:00`.

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
- To unit-test the scraper's pure parsers, build the instance with
  `object.__new__(GooglePlayService)` — this bypasses `__init__`, which imports
  `google-play-scraper` — then call `_parse_*` methods directly.
