package gateway

type Route struct {
	Method string
	Path   string
}

var Routes = []Route{
	{Method: "GET", Path: "/api/store-intel/apps/search"},
	{Method: "GET", Path: "/api/store-intel/apps/{app_id}"},
	{Method: "POST", Path: "/api/store-intel/keyword-rank"},
	{Method: "GET", Path: "/api/store-intel/tracking/apps"},
	{Method: "POST", Path: "/api/store-intel/tracking/apps"},
	{Method: "POST", Path: "/api/store-intel/tracking/apps/sync"},
	{Method: "POST", Path: "/api/store-intel/tracking/sync-all"},
	{Method: "GET", Path: "/api/store-intel/alerts"},
	{Method: "POST", Path: "/api/store-intel/alerts/read"},
}
