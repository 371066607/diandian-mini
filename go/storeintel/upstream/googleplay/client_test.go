package googleplay

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/diandian-mini/storeintel/dto"
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
