# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

点点数据 Mini (DiandianMini) — a local desktop client (PySide6 + SQLite) that scrapes and displays Google Play app intelligence: app details, reviews, ranking charts, keyword ranks, and tracked-app monitoring with alerts. UI strings, log messages, and error text are in Chinese.

## Commands

```bash
# Setup (Python 3.12)
python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

python main.py                 # run the GUI app
python main.py --smoke-test    # init DB + services, print "smoke-ok", exit (no GUI — use for CI / headless checks)

pytest                                                         # all tests
pytest tests/test_tracking_service.py                          # one file
pytest tests/test_tracking_service.py::test_sync_keyword_now_persists_history_and_sync_time  # one test

ruff check .        # lint (line-length 100, target py312)
ruff format .       # format

pyinstaller --noconfirm --windowed --name DiandianMini main.py   # package desktop binary
```

`pyproject.toml` sets `pythonpath = ["."]` so tests import `app.*` without installation.

## Architecture

Strictly layered, one-directional dependencies. Respect these boundaries when adding code:

```
UI (app/ui — PySide6 pages/widgets)
  → Services (app/services — business logic, own the DB-session boundary)
    → Repositories (app/db/repositories.py — stateless SQLAlchemy queries)   +   GooglePlayService (scraping)
      → Models (app/db/models.py — ORM)   /   Schemas (app/schemas — pydantic DTOs)
```

**Composition root — `app/composition.py:build_services()`** (the thin `main.py` launcher just imports and calls it). Every service is constructed once here and collaborators are injected via constructors (database, other services). The resulting `services` dict is handed to `MainWindow` / the QML bridge, which passes it down to every page. There is no global/singleton service locator; add new services here and thread them through. It lives under `app/` (NOT `main.py`) on purpose: the hot-patch overlays a downloaded `app/` onto `sys.path` but never re-runs the bundled `main.py`, so a newly-added service only reaches existing users via a code patch if it's registered here.

**DB session ownership.** `Database` (`app/db/database.py`) exposes `with database.session() as session:` — a contextmanager that commits on success, rolls back on exception, always closes (`expire_on_commit=False`). **Services open sessions; repositories never do.** Every repository method takes `session` as its first argument and is otherwise stateless (repos are instantiated once in a service's `__init__` and hold no data).

**Schemas vs models.** pydantic schemas (`app/schemas/*`) are the DTOs flowing out of scraping; SQLAlchemy models (`app/db/models.py`) are persistence. `app/utils/normalize.py` maps raw scraper dicts → schemas; repositories map schemas → models. `AppDetail` extends `AppSummary`. `GooglePlayService` always returns schemas, never raw dicts.

**Identity tuple.** Almost every entity is keyed by `(platform, app_id, country, lang)`. This 4-tuple recurs across models' unique constraints, repository `where` clauses, and service method signatures. `platform` is always `"google_play"` today but is modeled for future stores — keep it in new signatures.

**Time-series snapshots.** `app_snapshots`, `chart_snapshots`, `keyword_ranks` are append-only rows stamped with `captured_at`. History and charts are built by querying these ordered by `captured_at` — never mutate a prior snapshot. Timestamps are ISO **strings** via `app/utils/time_utils.now_iso()` (columns are `String`, not native datetime).

### Async UI pattern (critical)

Blocking work (all network scraping) must run off the Qt UI thread. `BasePage.run_task(loading_text, fn, on_success)` wraps `fn` in a `Worker` (`QRunnable`, `app/utils/worker.py`) dispatched to `QThreadPool.globalInstance()`; Qt signals (started/finished/error) toggle the shared `LoadingOverlay` and invoke `on_success` back on the UI thread. **Never call a service directly from a UI event handler** — always go through `run_task`, or the window freezes. For cheap, frequent local-DB work (e.g. `DashboardPage`/`TrackingPage` refresh on navigation), use the sibling `BasePage.run_background(fn, on_success)` — same off-thread pattern but **without** the overlay (so navigation doesn't flash a spinner); collect data in `fn`, return plain values, and set widgets in `on_success`. Pages subclass `BasePage` and implement `on_activated()` (called by `MainWindow.navigate_to` on each navigation). Cross-page jumps use `MainWindow.open_app_detail(app_id)` / `open_reviews(...)`.

### Scraping layer (`app/services/google_play_service.py`)

Wraps the `google-play-scraper` library but adds heavy custom logic — read this file before touching scraping:
- Charts use Google's `batchexecute` RPC with a gzipped+base64 request-body template (`_CHART_BODY_TEMPLATE_B64`), then walk deeply-nested JSON via `_get_in(data, [path])`.
- Search / similar-apps / detail-enrichment have raw-DOM-HTML regex fallbacks when the library path fails.
- `_request_text` falls back to a `curl` subprocess when `urllib` fails; `_run_with_retry` adds backoff.
- All failures raise `ServiceError` carrying a user-facing Chinese message from `app/constants.py` (`NETWORK_ERROR_MESSAGE`, `NOT_FOUND_MESSAGE`, etc.).

### Sync, scheduling & alerts

`TrackingService.sync_app_now()` is the core routine: fetch detail → load previous snapshot → upsert tracked app → save new snapshot → update sync time → `AlertService.create_snapshot_alerts(previous, current)` diffs old vs new to emit alerts. Fetch failures are logged and recorded as `fetch_failed` alerts. `AppScheduler` (APScheduler `BackgroundScheduler`, `app/jobs/scheduler.py`) runs `sync_tracked_job` (which calls `TrackingService.sync_all()` — **both** apps and keywords) on a daily `CronTrigger` at the `daily_sync_time` setting, gated by `scheduler_enabled`; started in `main.py`, shut down on exit. Call `scheduler.reload_jobs()` after changing schedule settings. `daily_sync_time` is parsed defensively (`time_utils.parse_time_of_day` never raises — a malformed value falls back to `09:00` so it can't block startup).

### Settings

Key-value `settings` table. `DEFAULT_SETTINGS` (`app/constants.py`) is the fallback; `SettingsService.get_all()` merges stored values over defaults; `ensure_defaults()` seeds missing keys at startup (called in `main.py`). Both the Settings and Tracking pages embed the **shared** `app/ui/widgets/settings_form.py:SettingsFormWidget` — the single save path that validates `daily_sync_time`, persists, applies `proxy` (via `network.apply_proxy_env`, which sets `HTTP(S)_PROXY` env vars so urllib **and** curl pick it up everywhere), retunes the scraper's `request_delay_seconds` (`GooglePlayService.configure`), and reloads the scheduler. Note: the `database_path` setting is **not** currently applied — `main.py` constructs `Database()` with the default path (the setting lives inside that DB, so wiring it needs restart semantics).

## Runtime data & migrations

- SQLite DB at `data/diandian_mini.sqlite3`; logs in `data/logs/`. `config.ensure_runtime_dirs()` creates these at startup.
- `app/db/migrations.py:migrate()` (run at startup from `main.py`) calls `create_all()` for missing tables, then **additively** adds any missing columns via `ALTER TABLE ... ADD COLUMN`, inferring the SQLite affinity from the model column type. It is best-effort per column (each in its own transaction, failures logged not raised) and only ever *adds* — column **renames/retypes/drops** still need manual handling. Type affinity is coarse (INTEGER/REAL/TEXT); constraints and defaults are not reproduced on added columns.

## Testing conventions

- Isolate with `Database(str(tmp_path / "x.sqlite3"))` + `create_all()` (pytest `tmp_path` fixture); no shared DB.
- No network in tests. Services are tested against small hand-written fake `GooglePlayService` classes that return schema objects.
- To unit-test the scraper's pure parsers, build the instance with `object.__new__(GooglePlayService)` — this bypasses `__init__`, which imports `google-play-scraper` — then call `_parse_*` methods directly.
