# StoreIntel Go Module

This is the Go facade for catch-radar's Google Play intelligence domain. It is
kept in this repository so `agent-gateway` does not need to be modified while the
module is being shaped.

## Boundary

`agent-gateway` should call `service.StoreIntelService`. Handlers stay thin:
bind request, extract request context, call the service, then wrap the result with
the same `code/message/data/trace_id/request_id` response envelope used by
`agent-gateway`.

```go
storeIntelSvc := service.NewStoreIntelService(storeIntelRepo, googlePlayClient)

result, err := storeIntelSvc.SearchApps(ctx, dto.SearchAppsRequest{
    Query: "ai notes",
    Country: "us",
    Lang: "en",
    Limit: 20,
})
```

## Packages

- `dto`: request/response/value objects with snake_case JSON fields.
- `repo`: persistence interface plus an in-memory implementation for tests and local smoke.
- `repo.NewSQLRepo(*sql.DB)`: MySQL-oriented persistence implementation for production wiring.
- `service`: the callable business facade.
- `upstream/googleplay`: standard-library Google Play Web client implementing
  `service.UpstreamClient` for the first Go-native scraper path.
- `gateway`: HTTP handlers plus response envelope matching `agent-gateway` style.
- `schema/mysql.sql`: table DDL used by the standalone server migration step.
- `cmd/storeintel-server`: standalone HTTP server for the frontend/API migration path.

## Run

Local smoke without MySQL:

```bash
go run ./cmd/storeintel-server --memory --smoke-test
```

Run with MySQL:

```bash
export STOREINTEL_MYSQL_DSN='user:pass@tcp(127.0.0.1:3306)/catch_radar?charset=utf8mb4&parseTime=false'
go run ./cmd/storeintel-server -addr 127.0.0.1:18080
```

The server applies `schema/mysql.sql` on startup unless `-skip-migrate` or
`STOREINTEL_SKIP_MIGRATE=true` is set.

The server also runs the backend scheduler by default. It reads the existing
`scheduler_enabled` and `daily_sync_time` settings, then runs
`SyncAll(due_only=true)` followed by history cleanup once per scheduled day. To
avoid duplicate scheduled runs after a backend restart or across multiple
backend instances, it atomically acquires the existing settings KV key
`scheduler_last_run_day` for the scheduled day before syncing. To disable the
scheduler for rollback or one-off API testing:

```bash
STOREINTEL_RUN_SCHEDULER=false go run ./cmd/storeintel-server -addr 127.0.0.1:18080
```

Desktop API adapter opt-in:

```bash
export CATCH_RADAR_STOREINTEL_API_URL='http://127.0.0.1:18080'
python main.py
```

Without `CATCH_RADAR_STOREINTEL_API_URL` (or `STOREINTEL_API_URL`) the PySide6/QML
client keeps using the existing local Python services and SQLite path. With an
API URL configured, the desktop injects a no-op scheduler proxy so the Python
APScheduler does not duplicate the Go backend's scheduled sync.

## Current Status

The facade, contracts, and the first Go-native Google Play Web upstream client
are in Go. The upstream boundary remains injectable:

```go
type UpstreamClient interface {
    SearchApps(ctx context.Context, req dto.SearchAppsRequest) ([]dto.AppSummary, error)
    Suggest(ctx context.Context, req dto.SuggestRequest) ([]string, error)
    GetAppDetail(ctx context.Context, req dto.GetAppDetailRequest) (dto.AppDetail, error)
    SimilarApps(ctx context.Context, req dto.SimilarAppsRequest) ([]dto.AppSummary, error)
    GetAppPermissions(ctx context.Context, req dto.AppPermissionsRequest) (map[string][]string, error)
    FetchChart(ctx context.Context, req dto.FetchChartRequest) (dto.FetchChartResponse, error)
    FetchReviews(ctx context.Context, req dto.FetchReviewsRequest) (dto.FetchReviewsResponse, error)
}
```

Routes currently mirror the desktop chart, keyword rank, review, settings,
tracking, and alert actions:

```text
GET  /api/store-intel/charts
POST /api/store-intel/charts/snapshot
GET  /api/store-intel/app-snapshots/history
GET  /api/store-intel/app-snapshots/recent
GET  /api/store-intel/app-snapshots/count
POST /api/store-intel/chart-rank
GET  /api/store-intel/chart-rank/history
POST /api/store-intel/keyword-rank
GET  /api/store-intel/keyword-rank/history
GET  /api/store-intel/keyword-rank/recent
POST /api/store-intel/keyword-coverage
POST /api/store-intel/keyword-coverage/stream
GET  /api/store-intel/apps/{app_id}/reviews
POST /api/store-intel/apps/{app_id}/reviews
GET  /api/store-intel/apps/{app_id}/reviews/cache
GET  /api/store-intel/apps/{app_id}/similar
GET  /api/store-intel/apps/{app_id}/permissions
POST /api/store-intel/history/cleanup
GET  /api/store-intel/tracking/apps
POST /api/store-intel/tracking/apps
POST /api/store-intel/tracking/apps/remove
POST /api/store-intel/tracking/apps/enabled
POST /api/store-intel/tracking/apps/frequency
POST /api/store-intel/tracking/apps/tag
POST /api/store-intel/tracking/apps/sync
GET  /api/store-intel/tracking/keywords
POST /api/store-intel/tracking/keywords
POST /api/store-intel/tracking/keywords/remove
POST /api/store-intel/tracking/keywords/enabled
POST /api/store-intel/tracking/keywords/frequency
POST /api/store-intel/tracking/keywords/sync
GET  /api/store-intel/tracking/chart-apps
POST /api/store-intel/tracking/chart-apps
POST /api/store-intel/tracking/chart-apps/remove
POST /api/store-intel/tracking/chart-apps/enabled
POST /api/store-intel/tracking/chart-apps/sync
POST /api/store-intel/tracking/sync-all
GET  /api/store-intel/alerts
POST /api/store-intel/alerts/read
GET  /api/store-intel/settings
POST /api/store-intel/settings
```

Tracked app, keyword, and chart sync failures persist `fetch_failed` /
`fetch_failed_persistent` alerts using `alert_fetch_escalate_after`; a later
successful sync after escalation persists `fetch_recovered`.
Tracked app sync also mirrors the desktop review monitor on the first sync of a
day: newest reviews are persisted with de-duplication and newly fetched low-star
bursts emit `review_negative_spike`.

Keyword coverage candidate discovery uses app metadata seeds plus Google Play
autocomplete (`IJ4APc` batchexecute). Deep scans expand autocomplete one level
further and still include similar-app title terms. A local/MySQL keyword corpus
refluxes prior locale keywords into later scans and sediments each candidate
pool plus confirmed hits back into `store_intel_keyword_corpus`. The optional
shared corpus Worker uses the existing `CATCH_RADAR_CORPUS_URL` /
`CATCH_RADAR_CORPUS_KEY` contract: `/candidates` is merged before local corpus and
`/contribute` receives non-soup candidates plus confirmed hits. Deep scans also
harvest alphabet-soup autocomplete into the local corpus for future reflux
without spending the current scan's search budget, and unconfirmed soup keywords
stay local-only. Coverage search now also honors the existing
`coverage_proxies` and `coverage_concurrency` settings: with proxies configured,
keyword searches run in parallel and each request leases a proxy; without proxies,
the scan remains serial to avoid multiplying same-IP rate-limit risk. API-mode
coverage can use `/keyword-coverage/stream` to receive NDJSON progress events
matching the desktop `coverageProgress` callback before the final result event.

For local module wiring:

```go
storeIntelRepo := repo.NewMemoryRepo() // replace with Ent/MySQL repo in agent-gateway.
googlePlayClient := googleplay.NewClient()
storeIntelSvc := service.NewStoreIntelService(storeIntelRepo, googlePlayClient)
```

For the minimal `agent-gateway` composition-root shape, see `AGENT_GATEWAY_USAGE.md`.

That keeps `agent-gateway` integration stable while richer scraper fields are
ported from the current desktop implementation.
