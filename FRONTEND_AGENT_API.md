# CatchRadar Frontend API Contract

Production API base:

```bash
CATCH_RADAR_STOREINTEL_API_URL=https://catchradar.meshub.ai
```

The desktop now starts in API mode by default, using `https://catchradar.meshub.ai`
when no API base env var is provided. API mode must keep `RemoteSchedulerProxy`;
the backend owns scheduled sync, background refresh execution, persistence, and
scraping.

Localhost API overrides are ignored unless the developer explicitly sets
`CATCH_RADAR_ALLOW_LOCAL_API=true`; remote API mode remains the product path.

## Frontend Rule

Regular pages should read DB/cache endpoints first. Do not synchronously trigger
upstream scraping from search, detail, charts, keyword rank, coverage, or reviews
pages unless the user explicitly requests a refresh.

When a DB/cache read misses, the frontend should submit a refresh job, poll the
job until it reaches a terminal state, then read the same DB/cache endpoint again.
The data rendered on screen must still come from MySQL-backed cache, not from a
direct upstream fetch response.

Explicit refresh actions should call `POST /api/store-intel/refresh-jobs`, then
poll `GET /api/store-intel/refresh-jobs/{job_id}`. MySQL is authoritative; Redis
is only the backend queue transport.

The desktop must not call the synchronous tracking sync endpoints in normal API
mode. Use refresh jobs for `sync all`, `sync due`, and `sync selected`.

## DB/Cache Reads

- `GET /api/store-intel/apps/search/cache`
- `GET /api/store-intel/apps/{app_id}/cache`
- `GET /api/store-intel/apps/{app_id}/reviews/cache`
- `GET /api/store-intel/charts/cache`
- `GET /api/store-intel/app-snapshots/history`
- `GET /api/store-intel/app-snapshots/recent`
- `GET /api/store-intel/app-snapshots/count`
- `GET /api/store-intel/chart-rank/history`
- `GET /api/store-intel/keyword-rank/history`
- `GET /api/store-intel/keyword-rank/recent`
- `GET /api/store-intel/keyword-coverage/cache`
- `GET /api/store-intel/tracking/apps`
- `GET /api/store-intel/tracking/keywords`
- `GET /api/store-intel/tracking/chart-apps`
- `GET /api/store-intel/alerts`
- `GET /api/store-intel/settings`

Cache miss handling:

- Detail/search/reviews/keyword-rank may return an empty result or a cache miss
  error depending on the endpoint. Submit the matching refresh job, wait for a
  terminal job status, then read the same cache endpoint again.
- `GET /api/store-intel/apps/search/cache` rows must be render-ready for the
  search table. Each item should include `app_id`, `title`, `developer`,
  `category`, `summary`, `rating`, `ratings_count`, `reviews_count`, `installs`,
  `min_installs`, `price`, `currency`, `free`, `has_iap`, `icon_url`, and
  `store_url` when available. If cached search rows are missing these display
  fields, treat the cache as incomplete, enqueue a `search` refresh job, then
  re-read the cache.
- A `search` refresh job should persist the search result rows and refresh app
  detail snapshots for returned apps, so later search/cache reads can hydrate
  UI fields from the latest DB snapshot.
- `GET /api/store-intel/charts/cache` returns `200` with `cached=false`,
  `items=[]`, and `total=0` when no chart snapshot exists.
- `GET /api/store-intel/keyword-coverage/cache` returns `200` with empty
  `candidates` and `covered` when no coverage result exists.
- Empty chart or coverage cache payloads should be treated as cache misses by
  the UI, not as final successful data.

## Explicit Fetch/Compute

- `GET /api/store-intel/apps/search`
- `GET /api/store-intel/apps/{app_id}`
- `GET /api/store-intel/apps/{app_id}/reviews`
- `GET /api/store-intel/apps/{app_id}/similar`
- `GET /api/store-intel/apps/{app_id}/permissions`
- `GET /api/store-intel/charts`
- `POST /api/store-intel/chart-rank`
- `POST /api/store-intel/keyword-rank`
- `POST /api/store-intel/keyword-coverage`
- `POST /api/store-intel/keyword-coverage/stream`

## Mutations

- `POST /api/store-intel/apps/{app_id}/reviews`
- `POST /api/store-intel/charts/snapshot`
- `POST /api/store-intel/tracking/apps`
- `POST /api/store-intel/tracking/apps/remove`
- `POST /api/store-intel/tracking/apps/enabled`
- `POST /api/store-intel/tracking/apps/frequency`
- `POST /api/store-intel/tracking/apps/tag`
- `POST /api/store-intel/tracking/keywords`
- `POST /api/store-intel/tracking/keywords/remove`
- `POST /api/store-intel/tracking/keywords/enabled`
- `POST /api/store-intel/tracking/keywords/frequency`
- `POST /api/store-intel/tracking/chart-apps`
- `POST /api/store-intel/tracking/chart-apps/remove`
- `POST /api/store-intel/tracking/chart-apps/enabled`
- `POST /api/store-intel/alerts/read`
- `POST /api/store-intel/history/cleanup`
- `POST /api/store-intel/settings`

## Refresh Jobs

- `POST /api/store-intel/refresh-jobs`
- `GET /api/store-intel/refresh-jobs/{job_id}`

Supported job kinds: `all`, `sync_all`, `due`, `sync_due`, `search`, `app`,
`keyword`, `chart`, `coverage`, `reviews`.

Status values: `queued`, `running`, `completed`, `failed`.

Typical request bodies:

```json
{"kind":"app","app_id":"com.whatsapp","country":"us","lang":"en"}
```

```json
{"kind":"chart","collection":"top_free","category":"APPLICATION","country":"us","lang":"en"}
```

```json
{"kind":"keyword","keyword":"whatsapp","app_id":"com.whatsapp","country":"us","lang":"en"}
```

```json
{"kind":"coverage","app_id":"com.whatsapp","country":"us","lang":"en","limit":50}
```

```json
{"kind":"reviews","app_id":"com.whatsapp","country":"us","lang":"en","limit":50}
```

```json
{"kind":"all","due_only":false}
```
