# Agent Gateway Usage Template

This file is the intended integration shape. It is documentation only; no
`agent-gateway` files are changed from this repository.

## Composition Root

In `agent-gateway`, the only production decision should be which DB/upstream
implementations to inject. The business API stays behind `module.Service`.

```go
import (
    "database/sql"

    storeintel "github.com/diandian-mini/storeintel"
    storeintelrepo "github.com/diandian-mini/storeintel/repo"
    googleplay "github.com/diandian-mini/storeintel/upstream/googleplay"
)

func NewStoreIntelModule(db *sql.DB) (*storeintel.Module, error) {
    return storeintel.NewModule(storeintel.Dependencies{
        Repo:     storeintelrepo.NewSQLRepo(db),
        Upstream: googleplay.NewClient(),
    })
}
```

If `agent-gateway` wants to keep Ent as the only DB entrypoint, add an Ent-backed
repo inside this module later and still keep the call site as `storeIntel.Module`.

## Handler Shape

Handlers should stay thin and follow the existing gateway pattern:

```go
func (h *GatewayHandler) storeIntelSearchApps(c *gin.Context) {
    result, err := h.storeIntel.Service.SearchApps(c.Request.Context(), dto.SearchAppsRequest{
        Query:   c.Query("query"),
        Country: c.DefaultQuery("country", "us"),
        Lang:    c.DefaultQuery("lang", "en"),
        Limit:   parseLimit(c.Query("limit")),
    })
    if err != nil {
        httpStatus, code, message, errorCode := gateway.MapServiceError(err)
        ctx := middleware.GetRequestContext(c)
        c.JSON(httpStatus, gateway.FailureWithContext(code, message, errorCode, dto.RequestContext{
            RequestID: ctx.RequestID,
            TraceID:   ctx.TraceID,
            AppID:     ctx.AppID,
            Platform:  ctx.Platform,
            UserID:    ctx.UserID,
            DeviceID:  ctx.DeviceID,
            CallerID:  ctx.CallerID,
            AuthType:  ctx.AuthType,
        }))
        return
    }
    c.JSON(http.StatusOK, gateway.Success(result))
}
```

## Route Contract

The module-owned route template is in `gateway.Routes`:

- `GET /api/store-intel/apps/search`
- `GET /api/store-intel/apps/{app_id}`
- `POST /api/store-intel/keyword-rank`
- `GET /api/store-intel/tracking/apps`
- `POST /api/store-intel/tracking/apps`
- `POST /api/store-intel/tracking/apps/sync`
- `POST /api/store-intel/tracking/sync-all`
- `GET /api/store-intel/alerts`
- `POST /api/store-intel/alerts/read`

## MySQL Schema

Copy `schema/mysql.sql` into the gateway migration flow when embedding the module.
Do not create these tables from business code.
