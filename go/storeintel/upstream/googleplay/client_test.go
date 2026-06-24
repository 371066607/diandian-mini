package googleplay

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/catch-radar/storeintel/dto"
)

func TestSearchAppsExtractsUniqueAppIDs(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/store/search" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		_, _ = w.Write([]byte(`
			<a href="/store/apps/details?id=com.one"></a>
			<a href="/store/apps/details?id=com.two&hl=en"></a>
			<a href="/store/apps/details?id=com.one"></a>
		`))
	}))
	defer server.Close()

	client := NewClient(WithBaseURL(server.URL), WithHTTPClient(server.Client()))
	items, err := client.SearchApps(context.Background(), dto.SearchAppsRequest{Query: "notes", Limit: 10})
	if err != nil {
		t.Fatalf("SearchApps returned error: %v", err)
	}
	if len(items) != 2 || items[0].AppID != "com.one" || items[1].AppID != "com.two" {
		t.Fatalf("unexpected items: %+v", items)
	}
}

func TestSearchAppsUsesProxyTransport(t *testing.T) {
	targetHit := false
	target := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		targetHit = true
		t.Fatalf("target server should not be reached directly when proxy is set: %s", r.URL.String())
	}))
	defer target.Close()

	proxyHit := false
	proxy := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		proxyHit = true
		if !strings.Contains(r.URL.String(), "/store/search") {
			t.Fatalf("proxy saw unexpected request URL: %s", r.URL.String())
		}
		_, _ = w.Write([]byte(`<a href="/store/apps/details?id=com.via.proxy"></a>`))
	}))
	defer proxy.Close()

	client := NewClient(
		WithBaseURL(target.URL),
		WithHTTPClient(&http.Client{Timeout: 5 * time.Second}),
	)
	items, err := client.SearchApps(context.Background(), dto.SearchAppsRequest{
		Query: "notes",
		Limit: 10,
		Proxy: proxy.URL,
	})
	if err != nil {
		t.Fatalf("SearchApps returned error: %v", err)
	}
	if !proxyHit || targetHit {
		t.Fatalf("proxyHit=%v targetHit=%v", proxyHit, targetHit)
	}
	if len(items) != 1 || items[0].AppID != "com.via.proxy" {
		t.Fatalf("unexpected proxy search items: %+v", items)
	}
}

func TestSuggestParsesBatchexecuteResponse(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/_/PlayStoreUi/data/batchexecute" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		if r.URL.Query().Get("rpcids") != "IJ4APc" || r.URL.Query().Get("gl") != "JP" {
			t.Fatalf("unexpected suggest query: %s", r.URL.RawQuery)
		}
		if err := r.ParseForm(); err != nil {
			t.Fatalf("ParseForm returned error: %v", err)
		}
		if !strings.Contains(r.Form.Get("f.req"), "IJ4APc") ||
			!strings.Contains(r.Form.Get("f.req"), "photo editor") {
			t.Fatalf("suggest rpc body missing fields: %s", r.Form.Get("f.req"))
		}
		payloadJSON, _ := json.Marshal([]any{[]any{
			[]any{
				[]any{"photos"},
				[]any{"photo editor"},
				[]any{"photos"},
				[]any{"photography"},
			},
		}})
		outerJSON, _ := json.Marshal([]any{[]any{"wrb.fr", "IJ4APc", string(payloadJSON)}})
		_, _ = w.Write([]byte(")]}'\n\n" + string(outerJSON)))
	}))
	defer server.Close()

	client := NewClient(WithBaseURL(server.URL), WithHTTPClient(server.Client()))
	items, err := client.Suggest(context.Background(), dto.SuggestRequest{
		Term:    "photo editor",
		Country: "jp",
		Lang:    "ja",
		Count:   2,
	})
	if err != nil {
		t.Fatalf("Suggest returned error: %v", err)
	}
	if len(items) != 2 || items[0] != "photos" || items[1] != "photo editor" {
		t.Fatalf("unexpected suggestions: %+v", items)
	}
}

func TestFetchChartExtractsRankedAppIDs(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/store/apps/top" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		if r.URL.Query().Get("chart") != "top_paid" || r.URL.Query().Get("gl") != "JP" {
			t.Fatalf("unexpected chart query: %s", r.URL.RawQuery)
		}
		_, _ = w.Write([]byte(`
			<a href="/store/apps/details?id=com.one"></a>
			<a href="/store/apps/details?id=com.two&hl=en"></a>
			<a href="/store/apps/details?id=com.three"></a>
		`))
	}))
	defer server.Close()

	client := NewClient(WithBaseURL(server.URL), WithHTTPClient(server.Client()))
	result, err := client.FetchChart(context.Background(), dto.FetchChartRequest{
		ChartType: "top_paid",
		Country:   "jp",
		Lang:      "ja",
		Limit:     2,
	})
	if err != nil {
		t.Fatalf("FetchChart returned error: %v", err)
	}
	if result.Total != 2 || result.Items[0].AppID != "com.one" || result.Items[1].Rank != 2 {
		t.Fatalf("unexpected chart result: %+v", result)
	}
	if result.Items[0].StoreURL == "" || result.Items[0].Raw["source"] != "google_play_web_chart" {
		t.Fatalf("chart item metadata missing: %+v", result.Items[0])
	}
}

func TestGetAppDetailParsesJSONLD(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/store/apps/details" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		_, _ = w.Write([]byte(`
			<html><head>
			<script type="application/ld+json">
			{
			  "@type": "SoftwareApplication",
			  "name": "Demo App",
			  "description": "A compact demo",
			  "applicationCategory": "TOOLS",
			  "operatingSystem": "Android",
			  "image": "https://example.test/icon.png",
			  "offers": {"price": "0", "priceCurrency": "USD"},
			  "aggregateRating": {"ratingValue": "4.6", "ratingCount": "1234", "reviewCount": "321"}
			}
			</script>
			</head></html>
		`))
	}))
	defer server.Close()

	client := NewClient(WithBaseURL(server.URL), WithHTTPClient(server.Client()))
	detail, err := client.GetAppDetail(context.Background(), dto.GetAppDetailRequest{AppID: "com.demo"})
	if err != nil {
		t.Fatalf("GetAppDetail returned error: %v", err)
	}
	if detail.AppID != "com.demo" || detail.Title != "Demo App" || detail.Category != "TOOLS" {
		t.Fatalf("unexpected detail: %+v", detail)
	}
	if detail.Rating == nil || *detail.Rating != 4.6 {
		t.Fatalf("rating not parsed: %+v", detail.Rating)
	}
	if detail.RatingsCount == nil || *detail.RatingsCount != 1234 {
		t.Fatalf("ratings count not parsed: %+v", detail.RatingsCount)
	}
	if detail.Free == nil || !*detail.Free {
		t.Fatalf("free flag not parsed: %+v", detail.Free)
	}
}

func TestGetAppDetailParsesJSONLDOfferArray(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/store/apps/details" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		_, _ = w.Write([]byte(`
			<html><head>
			<script type="application/ld+json">
			{
			  "@type": "SoftwareApplication",
			  "name": "Demo App",
			  "description": "A compact demo",
			  "offers": [{"@type": "Offer", "price": "0", "priceCurrency": "USD"}],
			  "aggregateRating": {"ratingValue": "4.6", "ratingCount": "1234"}
			}
			</script>
			</head></html>
		`))
	}))
	defer server.Close()

	client := NewClient(WithBaseURL(server.URL), WithHTTPClient(server.Client()))
	detail, err := client.GetAppDetail(context.Background(), dto.GetAppDetailRequest{AppID: "com.demo"})
	if err != nil {
		t.Fatalf("GetAppDetail returned error: %v", err)
	}
	if detail.Currency != "USD" || detail.Free == nil || !*detail.Free {
		t.Fatalf("offer array not parsed: %+v", detail)
	}
}

func TestSimilarAppsExtractsRelatedAppIDs(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/store/apps/details" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		if r.URL.Query().Get("id") != "com.demo" || r.URL.Query().Get("gl") != "DE" {
			t.Fatalf("unexpected similar query: %s", r.URL.RawQuery)
		}
		_, _ = w.Write([]byte(`
			<a href="/store/apps/details?id=com.demo"></a>
			<a href="/store/apps/details?id=com.related.one"></a>
			<a href="/store/apps/details?id=com.related.two&hl=en"></a>
			<a href="/store/apps/details?id=com.related.one"></a>
		`))
	}))
	defer server.Close()

	client := NewClient(WithBaseURL(server.URL), WithHTTPClient(server.Client()))
	items, err := client.SimilarApps(context.Background(), dto.SimilarAppsRequest{
		AppID:   "com.demo",
		Country: "de",
		Lang:    "de",
		Limit:   5,
	})
	if err != nil {
		t.Fatalf("SimilarApps returned error: %v", err)
	}
	if len(items) != 2 || items[0].AppID != "com.related.one" || items[1].AppID != "com.related.two" {
		t.Fatalf("unexpected similar items: %+v", items)
	}
	if items[0].StoreURL == "" || items[0].Raw["source"] != "google_play_web_similar" {
		t.Fatalf("similar item metadata missing: %+v", items[0])
	}
}

func TestFetchReviewsParsesBatchexecuteResponse(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/_/PlayStoreUi/data/batchexecute" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		if err := r.ParseForm(); err != nil {
			t.Fatalf("ParseForm returned error: %v", err)
		}
		if !strings.Contains(r.Form.Get("f.req"), "oCPfdb") {
			t.Fatalf("reviews rpc id missing from body: %s", r.Form.Get("f.req"))
		}
		review := []any{
			"review-1",
			[]any{"Ana"},
			2,
			nil,
			"Needs work",
			[]any{1718697600},
			7,
			nil,
			nil,
			nil,
			"1.2.3",
		}
		payloadJSON, _ := json.Marshal([]any{
			[]any{review},
			[]any{"page", "next-token"},
			[]any{},
		})
		outerJSON, _ := json.Marshal([]any{[]any{"wrb.fr", "oCPfdb", string(payloadJSON)}})
		_, _ = w.Write([]byte(")]}'\n\n" + string(outerJSON)))
	}))
	defer server.Close()

	client := NewClient(WithBaseURL(server.URL), WithHTTPClient(server.Client()))
	result, err := client.FetchReviews(context.Background(), dto.FetchReviewsRequest{
		AppID:   "com.demo",
		Country: "us",
		Lang:    "en",
		Sort:    "newest",
		Limit:   20,
	})
	if err != nil {
		t.Fatalf("FetchReviews returned error: %v", err)
	}
	if result.Total != 1 || result.NextToken != "next-token" {
		t.Fatalf("unexpected review result: %+v", result)
	}
	item := result.Items[0]
	if item.ReviewID != "review-1" || item.UserName != "Ana" || item.Content != "Needs work" {
		t.Fatalf("review fields not parsed: %+v", item)
	}
	if item.Rating == nil || *item.Rating != 2 {
		t.Fatalf("rating not parsed: %+v", item.Rating)
	}
	if item.HelpfulCount == nil || *item.HelpfulCount != 7 {
		t.Fatalf("helpful count not parsed: %+v", item.HelpfulCount)
	}
	if item.AppVersion != "1.2.3" || item.ReviewCreatedAt != "2024-06-18T08:00:00Z" {
		t.Fatalf("version/time not parsed: %+v", item)
	}
}

func TestGetAppPermissionsParsesBatchexecuteResponse(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/_/PlayStoreUi/data/batchexecute" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		if err := r.ParseForm(); err != nil {
			t.Fatalf("ParseForm returned error: %v", err)
		}
		if !strings.Contains(r.Form.Get("f.req"), "xdSrCf") {
			t.Fatalf("permissions rpc id missing from body: %s", r.Form.Get("f.req"))
		}
		containerJSON, _ := json.Marshal([]any{
			[]any{
				[]any{"Location", nil, []any{
					[]any{nil, "precise location"},
					[]any{nil, "approximate location"},
				}, nil},
			},
			[]any{
				[]any{nil, "view network connections"},
				[]any{nil, "full network access"},
			},
		})
		outerJSON, _ := json.Marshal([]any{[]any{"wrb.fr", "xdSrCf", string(containerJSON)}})
		_, _ = w.Write([]byte(")]}'\n\n" + string(outerJSON)))
	}))
	defer server.Close()

	client := NewClient(WithBaseURL(server.URL), WithHTTPClient(server.Client()))
	groups, err := client.GetAppPermissions(context.Background(), dto.AppPermissionsRequest{
		AppID:   "com.demo",
		Country: "us",
		Lang:    "en",
	})
	if err != nil {
		t.Fatalf("GetAppPermissions returned error: %v", err)
	}
	if got := groups["Location"]; len(got) != 2 || got[0] != "approximate location" || got[1] != "precise location" {
		t.Fatalf("location permissions not parsed/sorted: %+v", got)
	}
	if got := groups["Uncategorized"]; len(got) != 2 || got[0] != "full network access" || got[1] != "view network connections" {
		t.Fatalf("uncategorized permissions not parsed/sorted: %+v", got)
	}
}
