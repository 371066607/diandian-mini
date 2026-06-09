---
name: run-app
description: Launch, smoke-test, lint, and headlessly verify the 点点数据 Mini (DiandianMini) PySide6 desktop app. Use whenever asked to run / start / 运行 the app, verify a change works in the real GUI, run the test suite, or render the detail/charts pages headlessly. Encodes the non-ASCII-path gotchas that break bare `python`/`pip`/glob commands in this repo.
---

# Running 点点数据 Mini (DiandianMini)

PySide6 + SQLite desktop app. Entry point: `main.py` → `main()` builds services
(`build_services()`), runs DB migration, starts the APScheduler, shows `MainWindow`.

## ⚠️ Critical: the project path contains non-ASCII em-dashes

The repo lives at `/Volumes/DevSpace/myData——destop` (note `——`, U+2014). This breaks
two things, every time:

1. **zsh globbing** — `something/*` expands to `no matches found` and aborts the command.
2. **The venv's `pip` / `python` shebangs** — `.venv/bin/pip` and `.venv/bin/python`
   carry a hard-coded shebang that the shell mangles (`bad interpreter ... no such file`).
   Bare `python` / `python3.12` are **not** on PATH either.

**Always** do both of these:
- `cd "/Volumes/DevSpace/myData——destop"` first (quote the path), then run.
- Invoke Python as **`.venv/bin/python3.12`** and reach tools via **`-m`**
  (`.venv/bin/python3.12 -m pip`, `... -m pytest`, `... -m ruff`). Never bare
  `pip` / `pytest` / `ruff` / `python`.

## Launch the real GUI (macOS display)

```bash
cd "/Volumes/DevSpace/myData——destop" && .venv/bin/python3.12 main.py
```

Run it in the background (it blocks on the Qt event loop). A clean launch logs:

```
Scheduler started
Added job "sync_tracked_job" to job store "default"
```

A `Python[...] error messaging the mach port for IMKCFRunLoopWakeUpReliable` line is a
**benign** macOS input-method warning that appears once the window gains focus — it
confirms the window actually displayed, not an error. Verify the process is alive with
`pgrep -fl main.py`.

Because every page (incl. `AppDetailPage`) is constructed at startup inside `MainWindow`,
a clean launch already proves all widgets build without layout/reference errors.

## Headless smoke test (CI / no display)

```bash
cd "/Volumes/DevSpace/myData——destop" && .venv/bin/python3.12 main.py --smoke-test
```

Inits DB + services, prints `smoke-ok`, exits. No GUI. Use this for a fast "does it boot".

## Lint + full test suite

```bash
cd "/Volumes/DevSpace/myData——destop" && .venv/bin/python3.12 -m ruff check .
cd "/Volumes/DevSpace/myData——destop" && QT_QPA_PLATFORM=offscreen .venv/bin/python3.12 -m pytest -q
```

`QT_QPA_PLATFORM=offscreen` is **required** for pytest (the GUI smoke tests construct
real Qt widgets with no display). Without it, Qt aborts. Same env var lets you render any
page headlessly.

## Drive a page headlessly (verify a change without clicking)

Network scraping is slow/flaky and can't be clicked in a headless env. To prove the
**rendering** wiring of `AppDetailPage` (e.g. new metric chips / 更多信息 card), feed it a
hand-built `AppDetail` offscreen and read the resulting widget text — no network:

```bash
cd "/Volumes/DevSpace/myData——destop" && QT_QPA_PLATFORM=offscreen .venv/bin/python3.12 - <<'PY'
from PySide6.QtWidgets import QApplication
app = QApplication([])
from app.ui.pages.app_detail_page import AppDetailPage
from app.schemas.app_schema import AppDetail

class FakeMon:    # monetization_service.score(detail) -> dict
    def score(self, d): return {"score": 42, "signals": ["x"], "note": "n"}
class FakeTrack:  # tracking_service.get_history(...) -> []
    def get_history(self, *a, **k): return []

services = {
    "google_play_service": object(),
    "tracking_service": FakeTrack(),
    "monetization_service": FakeMon(),
    "settings_service": None,
}
page = AppDetailPage(services, None, None)
detail = AppDetail(app_id="com.demo", title="Demo", rating=4.3, min_installs=1000000,
                   min_android_api=26, max_android_api=34, original_price=4.99, sale=True,
                   available=True, app_bundle="com.demo.b", genre_id="TOOLS",
                   developer_id="d1", currency="USD", content_rating_description="x",
                   data_safety=[{"data": "位置"}], histogram=[1,2,3,4,5], screenshots=[])
page._on_detail_finished({"detail": detail, "history": [], "country": "us", "lang": "en"},
                         page._detail_gen)
print("android_api ->", page.metric_values["android_api"].text())
print("更多信息.app_bundle ->", page.info_labels["app_bundle"].text())
print("OK")
PY
```

Mirror this shape for other pages: construct `QApplication([])`, instantiate the page with
the small set of services it pulls from `services[...]`, call its `_on_*_finished` handler
with a fake payload, then assert on widget `.text()`.

## Data & dependency notes

- Runtime data: `data/diandian_mini.sqlite3`, logs in `data/logs/` (auto-created at startup).
- Two scraper libs are installed: `google-play-scraper` (1.2.7) and `gplay-scraper` (1.0.6).
  `GooglePlayService` prefers `gplay-scraper` for `app_detail` / charts and falls back to
  `google-play-scraper` + DOM scraping. If imports fail, re-install with
  `cd "/Volumes/DevSpace/myData——destop" && .venv/bin/python3.12 -m pip install -r requirements.txt`.

## Stopping the app

Kill the background process (`pkill -f "main.py"` or stop the background shell task). On
exit `main()` shuts the scheduler down and drains the `QThreadPool` (bounded 3s wait), so
a clean quit is expected; if it hangs, a long network call is draining.
