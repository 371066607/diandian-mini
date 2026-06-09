# StoreIntel Go Module

This is the Go facade for 点点数据 Mini's Google Play intelligence domain. It is
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
- `gateway`: route and response templates matching `agent-gateway` style.
- `schema/mysql.sql`: table DDL to copy into the host migration flow.

## Current Status

The facade, contracts, and the first Go-native Google Play Web upstream client
are in Go. The upstream boundary remains injectable:

```go
type UpstreamClient interface {
    SearchApps(ctx context.Context, req dto.SearchAppsRequest) ([]dto.AppSummary, error)
    GetAppDetail(ctx context.Context, req dto.GetAppDetailRequest) (dto.AppDetail, error)
}
```

For local module wiring:

```go
storeIntelRepo := repo.NewMemoryRepo() // replace with Ent/MySQL repo in agent-gateway.
googlePlayClient := googleplay.NewClient()
storeIntelSvc := service.NewStoreIntelService(storeIntelRepo, googlePlayClient)
```

For the minimal `agent-gateway` composition-root shape, see `AGENT_GATEWAY_USAGE.md`.

That keeps `agent-gateway` integration stable while richer scraper fields are
ported from the current desktop implementation.
