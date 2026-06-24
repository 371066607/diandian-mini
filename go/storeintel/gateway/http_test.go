package gateway_test

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	storeintel "github.com/catch-radar/storeintel"
	"github.com/catch-radar/storeintel/dto"
	"github.com/catch-radar/storeintel/gateway"
)

type httpFakeUpstream struct {
	search      []dto.AppSummary
	suggest     []string
	similar     []dto.AppSummary
	permissions map[string][]string
	detail      dto.AppDetail
	chart       dto.FetchChartResponse
	review      dto.FetchReviewsResponse
}

func (f httpFakeUpstream) SearchApps(context.Context, dto.SearchAppsRequest) ([]dto.AppSummary, error) {
	return f.search, nil
}

func (f httpFakeUpstream) Suggest(context.Context, dto.SuggestRequest) ([]string, error) {
	return f.suggest, nil
}

func (f httpFakeUpstream) GetAppDetail(_ context.Context, req dto.GetAppDetailRequest) (dto.AppDetail, error) {
	detail := f.detail
	if detail.AppID == "" {
		detail.AppID = req.AppID
	}
	if detail.Platform == "" {
		detail.Platform = dto.PlatformGooglePlay
	}
	return detail, nil
}

func (f httpFakeUpstream) SimilarApps(context.Context, dto.SimilarAppsRequest) ([]dto.AppSummary, error) {
	return f.similar, nil
}

func (f httpFakeUpstream) GetAppPermissions(context.Context, dto.AppPermissionsRequest) (map[string][]string, error) {
	return f.permissions, nil
}

func (f httpFakeUpstream) FetchChart(context.Context, dto.FetchChartRequest) (dto.FetchChartResponse, error) {
	return f.chart, nil
}

func (f httpFakeUpstream) FetchReviews(context.Context, dto.FetchReviewsRequest) (dto.FetchReviewsResponse, error) {
	return f.review, nil
}

func containsString(items []string, target string) bool {
	for _, item := range items {
		if item == target {
			return true
		}
	}
	return false
}

func TestHTTPHandlerSearchApps(t *testing.T) {
	module := storeintel.NewInMemoryModule(storeintel.Dependencies{
		Upstream: httpFakeUpstream{search: []dto.AppSummary{{
			Platform: dto.PlatformGooglePlay,
			AppID:    "com.demo",
			Title:    "Demo",
		}}},
	})
	handler := gateway.NewHandler(module.Service)

	req := httptest.NewRequest(http.MethodGet, "/api/store-intel/apps/search?q=demo&limit=5&country=ca&lang=fr", nil)
	req.Header.Set("X-Request-ID", "req-1")
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", rec.Code, rec.Body.String())
	}
	var resp gateway.Response[dto.SearchAppsResponse]
	decodeResponse(t, rec, &resp)
	if resp.Code != gateway.ErrorCodeOK || resp.RequestID != "req-1" {
		t.Fatalf("unexpected envelope: %+v", resp)
	}
	if resp.Data.Total != 1 || resp.Data.Items[0].AppID != "com.demo" {
		t.Fatalf("unexpected search payload: %+v", resp.Data)
	}
}

func TestHTTPHandlerKeywordCoverage(t *testing.T) {
	module := storeintel.NewInMemoryModule(storeintel.Dependencies{
		Upstream: httpFakeUpstream{
			search: []dto.AppSummary{
				{Platform: dto.PlatformGooglePlay, AppID: "com.other"},
				{Platform: dto.PlatformGooglePlay, AppID: "com.demo"},
			},
			suggest: []string{"demo notes"},
			detail: dto.AppDetail{AppSummary: dto.AppSummary{
				AppID: "com.demo",
				Title: "Demo Notes",
			}},
		},
	})
	handler := gateway.NewHandler(module.Service)

	req := httptest.NewRequest(
		http.MethodPost,
		"/api/store-intel/keyword-coverage",
		bytes.NewBufferString(`{"app_id":"com.demo","country":"us","lang":"en","limit":10}`),
	)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", rec.Code, rec.Body.String())
	}
	var resp gateway.Response[dto.KeywordCoverageResponse]
	decodeResponse(t, rec, &resp)
	if resp.Data.AppID != "com.demo" || resp.Data.CandidateCount == 0 ||
		len(resp.Data.Covered) == 0 || resp.Data.Covered[0].Rank != 2 {
		t.Fatalf("unexpected coverage payload: %+v", resp.Data)
	}
	if !containsString(resp.Data.Candidates, "demo notes") {
		t.Fatalf("autocomplete candidate missing from coverage payload: %+v", resp.Data.Candidates)
	}
}

func TestHTTPHandlerKeywordCoverageStream(t *testing.T) {
	module := storeintel.NewInMemoryModule(storeintel.Dependencies{
		Upstream: httpFakeUpstream{
			search: []dto.AppSummary{
				{Platform: dto.PlatformGooglePlay, AppID: "com.demo"},
			},
		},
	})
	handler := gateway.NewHandler(module.Service)

	req := httptest.NewRequest(
		http.MethodPost,
		"/api/store-intel/keyword-coverage/stream",
		bytes.NewBufferString(`{"app_id":"com.demo","canonical_app_id":"com.demo","country":"us","lang":"en","limit":10,"candidates":["demo notes"]}`),
	)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", rec.Code, rec.Body.String())
	}
	if !strings.Contains(rec.Header().Get("Content-Type"), "application/x-ndjson") {
		t.Fatalf("unexpected content type: %s", rec.Header().Get("Content-Type"))
	}
	lines := strings.Split(strings.TrimSpace(rec.Body.String()), "\n")
	if len(lines) < 2 {
		t.Fatalf("expected progress and result stream events, got %q", rec.Body.String())
	}
	var progress struct {
		Type     string  `json:"type"`
		Message  string  `json:"message"`
		Fraction float64 `json:"fraction"`
	}
	if err := json.Unmarshal([]byte(lines[0]), &progress); err != nil {
		t.Fatalf("decode progress event: %v", err)
	}
	if progress.Type != "progress" || progress.Message != "覆盖检测 1/1：demo notes" || progress.Fraction != 1 {
		t.Fatalf("unexpected progress event: %+v", progress)
	}
	var result struct {
		Type string                      `json:"type"`
		Data dto.KeywordCoverageResponse `json:"data"`
	}
	if err := json.Unmarshal([]byte(lines[len(lines)-1]), &result); err != nil {
		t.Fatalf("decode result event: %v", err)
	}
	if result.Type != "result" || len(result.Data.Covered) != 1 ||
		result.Data.Covered[0].Keyword != "demo notes" {
		t.Fatalf("unexpected result event: %+v", result)
	}
}

func TestHTTPHandlerSimilarApps(t *testing.T) {
	module := storeintel.NewInMemoryModule(storeintel.Dependencies{
		Upstream: httpFakeUpstream{similar: []dto.AppSummary{{
			Platform: dto.PlatformGooglePlay,
			AppID:    "com.related",
			Title:    "Related",
		}}},
	})
	handler := gateway.NewHandler(module.Service)

	req := httptest.NewRequest(http.MethodGet, "/api/store-intel/apps/com.demo/similar?country=us&lang=en&limit=5", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", rec.Code, rec.Body.String())
	}
	var resp gateway.Response[dto.SimilarAppsResponse]
	decodeResponse(t, rec, &resp)
	if resp.Data.Total != 1 || resp.Data.Items[0].AppID != "com.related" {
		t.Fatalf("unexpected similar payload: %+v", resp.Data)
	}
}

func TestHTTPHandlerAppPermissions(t *testing.T) {
	module := storeintel.NewInMemoryModule(storeintel.Dependencies{
		Upstream: httpFakeUpstream{permissions: map[string][]string{
			"Location": {"approximate location"},
		}},
	})
	handler := gateway.NewHandler(module.Service)

	req := httptest.NewRequest(http.MethodGet, "/api/store-intel/apps/com.demo/permissions?country=us&lang=en", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", rec.Code, rec.Body.String())
	}
	var resp gateway.Response[dto.AppPermissionsResponse]
	decodeResponse(t, rec, &resp)
	if len(resp.Data.Groups["Location"]) != 1 || resp.Data.Groups["Location"][0] != "approximate location" {
		t.Fatalf("unexpected permissions payload: %+v", resp.Data)
	}
}

func TestHTTPHandlerAddAndListTrackedApps(t *testing.T) {
	module := storeintel.NewInMemoryModule(storeintel.Dependencies{})
	handler := gateway.NewHandler(module.Service)

	addBody := bytes.NewBufferString(`{"app_id":"com.demo","country":"us","lang":"en","frequency":"daily","tag":"core"}`)
	addReq := httptest.NewRequest(http.MethodPost, "/api/store-intel/tracking/apps", addBody)
	addRec := httptest.NewRecorder()
	handler.ServeHTTP(addRec, addReq)
	if addRec.Code != http.StatusOK {
		t.Fatalf("add status = %d, body = %s", addRec.Code, addRec.Body.String())
	}
	var addResp gateway.Response[dto.TrackedApp]
	decodeResponse(t, addRec, &addResp)
	if addResp.Data.AppID != "com.demo" || addResp.Data.Tag != "core" {
		t.Fatalf("unexpected add response: %+v", addResp.Data)
	}

	listReq := httptest.NewRequest(http.MethodGet, "/api/store-intel/tracking/apps?enabled=true", nil)
	listRec := httptest.NewRecorder()
	handler.ServeHTTP(listRec, listReq)
	if listRec.Code != http.StatusOK {
		t.Fatalf("list status = %d, body = %s", listRec.Code, listRec.Body.String())
	}
	var listResp gateway.Response[dto.ListTrackedAppsResponse]
	decodeResponse(t, listRec, &listResp)
	if listResp.Data.Total != 1 || listResp.Data.Items[0].AppID != "com.demo" {
		t.Fatalf("unexpected list response: %+v", listResp.Data)
	}
}

func TestHTTPHandlerTrackingManagementMutations(t *testing.T) {
	module := storeintel.NewInMemoryModule(storeintel.Dependencies{})
	handler := gateway.NewHandler(module.Service)
	post := func(path, body string) *httptest.ResponseRecorder {
		t.Helper()
		req := httptest.NewRequest(http.MethodPost, path, bytes.NewBufferString(body))
		rec := httptest.NewRecorder()
		handler.ServeHTTP(rec, req)
		if rec.Code != http.StatusOK {
			t.Fatalf("POST %s status = %d, body = %s", path, rec.Code, rec.Body.String())
		}
		return rec
	}

	post("/api/store-intel/tracking/apps", `{"app_id":"com.demo","country":"us","lang":"en","frequency":"daily","tag":"core"}`)
	var appEnabled gateway.Response[dto.TrackingMutationResponse]
	decodeResponse(t, post("/api/store-intel/tracking/apps/enabled", `{"app_id":"com.demo","country":"us","lang":"en","enabled":false}`), &appEnabled)
	if appEnabled.Data.Updated != 1 || appEnabled.Data.Enabled == nil || *appEnabled.Data.Enabled {
		t.Fatalf("unexpected app enabled response: %+v", appEnabled.Data)
	}
	var appFrequency gateway.Response[dto.TrackingMutationResponse]
	decodeResponse(t, post("/api/store-intel/tracking/apps/frequency", `{"app_id":"com.demo","country":"us","lang":"en","frequency":"manual"}`), &appFrequency)
	if appFrequency.Data.Updated != 1 || appFrequency.Data.Frequency != "manual" {
		t.Fatalf("unexpected app frequency response: %+v", appFrequency.Data)
	}
	var appTag gateway.Response[dto.TrackingMutationResponse]
	decodeResponse(t, post("/api/store-intel/tracking/apps/tag", `{"app_id":"com.demo","country":"us","lang":"en","tag":" ops "}`), &appTag)
	if appTag.Data.Updated != 1 || appTag.Data.Tag != "ops" {
		t.Fatalf("unexpected app tag response: %+v", appTag.Data)
	}
	var removedApp gateway.Response[dto.TrackingMutationResponse]
	decodeResponse(t, post("/api/store-intel/tracking/apps/remove", `{"app_id":"com.demo","country":"us","lang":"en"}`), &removedApp)
	if removedApp.Data.Updated != 1 {
		t.Fatalf("unexpected app remove response: %+v", removedApp.Data)
	}

	post("/api/store-intel/tracking/keywords", `{"keyword":"notes","app_id":"com.target","country":"us","lang":"en","platform":"google_play"}`)
	post("/api/store-intel/tracking/keywords", `{"keyword":"notes","app_id":"com.target","country":"us","lang":"en","platform":"app_store"}`)
	var keywordEnabled gateway.Response[dto.TrackingMutationResponse]
	decodeResponse(t, post("/api/store-intel/tracking/keywords/enabled", `{"keyword":"notes","app_id":"com.target","country":"us","lang":"en","platform":"app_store","enabled":false}`), &keywordEnabled)
	if keywordEnabled.Data.Updated != 1 || keywordEnabled.Data.Enabled == nil || *keywordEnabled.Data.Enabled {
		t.Fatalf("unexpected keyword enabled response: %+v", keywordEnabled.Data)
	}
	var keywordFrequency gateway.Response[dto.TrackingMutationResponse]
	decodeResponse(t, post("/api/store-intel/tracking/keywords/frequency", `{"keyword":"notes","app_id":"com.target","country":"us","lang":"en","platform":"app_store","frequency":"weekly"}`), &keywordFrequency)
	if keywordFrequency.Data.Updated != 1 || keywordFrequency.Data.Frequency != "weekly" {
		t.Fatalf("unexpected keyword frequency response: %+v", keywordFrequency.Data)
	}
	var removedKeyword gateway.Response[dto.TrackingMutationResponse]
	decodeResponse(t, post("/api/store-intel/tracking/keywords/remove", `{"keyword":"notes","app_id":"com.target","country":"us","lang":"en","platform":"google_play"}`), &removedKeyword)
	if removedKeyword.Data.Updated != 1 {
		t.Fatalf("unexpected keyword remove response: %+v", removedKeyword.Data)
	}
	listKeywordReq := httptest.NewRequest(http.MethodGet, "/api/store-intel/tracking/keywords", nil)
	listKeywordRec := httptest.NewRecorder()
	handler.ServeHTTP(listKeywordRec, listKeywordReq)
	var listKeywordResp gateway.Response[dto.ListTrackedKeywordsResponse]
	decodeResponse(t, listKeywordRec, &listKeywordResp)
	if listKeywordResp.Data.Total != 1 || listKeywordResp.Data.Items[0].Platform != "app_store" ||
		listKeywordResp.Data.Items[0].Enabled || listKeywordResp.Data.Items[0].Frequency != "weekly" {
		t.Fatalf("unexpected keyword list after mutations: %+v", listKeywordResp.Data)
	}

	post("/api/store-intel/tracking/chart-apps", `{"app_id":"com.target","collection":"top_free","category":"GAME","country":"us","lang":"en"}`)
	var chartEnabled gateway.Response[dto.TrackingMutationResponse]
	decodeResponse(t, post("/api/store-intel/tracking/chart-apps/enabled", `{"app_id":"com.target","collection":"top_free","category":"GAME","country":"us","lang":"en","enabled":false}`), &chartEnabled)
	if chartEnabled.Data.Updated != 1 || chartEnabled.Data.Enabled == nil || *chartEnabled.Data.Enabled {
		t.Fatalf("unexpected chart enabled response: %+v", chartEnabled.Data)
	}
	var removedChart gateway.Response[dto.TrackingMutationResponse]
	decodeResponse(t, post("/api/store-intel/tracking/chart-apps/remove", `{"app_id":"com.target","collection":"top_free","category":"GAME","country":"us","lang":"en"}`), &removedChart)
	if removedChart.Data.Updated != 1 {
		t.Fatalf("unexpected chart remove response: %+v", removedChart.Data)
	}
	listChartReq := httptest.NewRequest(http.MethodGet, "/api/store-intel/tracking/chart-apps", nil)
	listChartRec := httptest.NewRecorder()
	handler.ServeHTTP(listChartRec, listChartReq)
	var listChartResp gateway.Response[dto.ListTrackedChartAppsResponse]
	decodeResponse(t, listChartRec, &listChartResp)
	if listChartResp.Data.Total != 0 {
		t.Fatalf("unexpected chart list after remove: %+v", listChartResp.Data)
	}
}

func TestHTTPHandlerSettingsRoundTrip(t *testing.T) {
	module := storeintel.NewInMemoryModule(storeintel.Dependencies{})
	if err := module.Service.EnsureSettingsDefaults(context.Background()); err != nil {
		t.Fatalf("EnsureSettingsDefaults returned error: %v", err)
	}
	handler := gateway.NewHandler(module.Service)

	saveReq := httptest.NewRequest(
		http.MethodPost,
		"/api/store-intel/settings",
		bytes.NewBufferString(`{"default_country":"de","theme":"teal"}`),
	)
	saveRec := httptest.NewRecorder()
	handler.ServeHTTP(saveRec, saveReq)
	if saveRec.Code != http.StatusOK {
		t.Fatalf("save status = %d, body = %s", saveRec.Code, saveRec.Body.String())
	}
	var saveResp gateway.Response[map[string]string]
	decodeResponse(t, saveRec, &saveResp)
	if saveResp.Data["default_country"] != "de" || saveResp.Data["default_lang"] != "en" {
		t.Fatalf("unexpected settings save response: %+v", saveResp.Data)
	}

	getReq := httptest.NewRequest(http.MethodGet, "/api/store-intel/settings", nil)
	getRec := httptest.NewRecorder()
	handler.ServeHTTP(getRec, getReq)
	if getRec.Code != http.StatusOK {
		t.Fatalf("get status = %d, body = %s", getRec.Code, getRec.Body.String())
	}
	var getResp gateway.Response[map[string]string]
	decodeResponse(t, getRec, &getResp)
	if getResp.Data["default_country"] != "de" || getResp.Data["daily_sync_time"] != "09:00" {
		t.Fatalf("unexpected settings get response: %+v", getResp.Data)
	}
}

func TestHTTPHandlerKeywordRankPersistsHistory(t *testing.T) {
	module := storeintel.NewInMemoryModule(storeintel.Dependencies{
		Upstream: httpFakeUpstream{search: []dto.AppSummary{
			{Platform: dto.PlatformGooglePlay, AppID: "com.other"},
			{Platform: dto.PlatformGooglePlay, AppID: "com.target"},
		}},
	})
	handler := gateway.NewHandler(module.Service)

	rankReq := httptest.NewRequest(
		http.MethodPost,
		"/api/store-intel/keyword-rank",
		bytes.NewBufferString(`{"keyword":"notes","app_id":"com.target","country":"us","lang":"en","limit":10}`),
	)
	rankRec := httptest.NewRecorder()
	handler.ServeHTTP(rankRec, rankReq)
	if rankRec.Code != http.StatusOK {
		t.Fatalf("rank status = %d, body = %s", rankRec.Code, rankRec.Body.String())
	}
	var rankResp gateway.Response[dto.KeywordRankResponse]
	decodeResponse(t, rankRec, &rankResp)
	if !rankResp.Data.Found || rankResp.Data.Rank == nil || *rankResp.Data.Rank != 2 {
		t.Fatalf("unexpected rank response: %+v", rankResp.Data)
	}

	historyReq := httptest.NewRequest(
		http.MethodGet,
		"/api/store-intel/keyword-rank/history?keyword=notes&app_id=com.target&country=us&lang=en",
		nil,
	)
	historyRec := httptest.NewRecorder()
	handler.ServeHTTP(historyRec, historyReq)
	if historyRec.Code != http.StatusOK {
		t.Fatalf("history status = %d, body = %s", historyRec.Code, historyRec.Body.String())
	}
	var historyResp gateway.Response[dto.KeywordRankHistoryResponse]
	decodeResponse(t, historyRec, &historyResp)
	if historyResp.Data.Total != 1 || historyResp.Data.Items[0].Rank == nil || *historyResp.Data.Items[0].Rank != 2 {
		t.Fatalf("unexpected history response: %+v", historyResp.Data)
	}

	recentReq := httptest.NewRequest(
		http.MethodGet,
		"/api/store-intel/keyword-rank/recent?app_id=com.target&country=us&lang=en&limit=5",
		nil,
	)
	recentRec := httptest.NewRecorder()
	handler.ServeHTTP(recentRec, recentReq)
	if recentRec.Code != http.StatusOK {
		t.Fatalf("recent status = %d, body = %s", recentRec.Code, recentRec.Body.String())
	}
	var recentResp gateway.Response[dto.KeywordRankHistoryResponse]
	decodeResponse(t, recentRec, &recentResp)
	if recentResp.Data.Total != 1 || recentResp.Data.Items[0].Keyword != "notes" {
		t.Fatalf("unexpected recent keyword ranks response: %+v", recentResp.Data)
	}
}

func TestHTTPHandlerAppSnapshotHistoryRecentAndCount(t *testing.T) {
	rating := 4.7
	ratingsCount := int64(1200)
	reviewsCount := int64(340)
	realInstalls := int64(5000)
	module := storeintel.NewInMemoryModule(storeintel.Dependencies{
		Upstream: httpFakeUpstream{detail: dto.AppDetail{
			AppSummary: dto.AppSummary{
				Platform:     dto.PlatformGooglePlay,
				AppID:        "com.demo",
				Title:        "Demo",
				Rating:       &rating,
				RatingsCount: &ratingsCount,
				ReviewsCount: &reviewsCount,
				Installs:     "5,000+",
				MinInstalls:  &realInstalls,
			},
			RealInstalls: &realInstalls,
			Version:      "1.2.3",
		}},
	})
	handler := gateway.NewHandler(module.Service)

	syncReq := httptest.NewRequest(
		http.MethodPost,
		"/api/store-intel/tracking/apps/sync",
		bytes.NewBufferString(`{"app_id":"com.demo","country":"us","lang":"en"}`),
	)
	syncRec := httptest.NewRecorder()
	handler.ServeHTTP(syncRec, syncReq)
	if syncRec.Code != http.StatusOK {
		t.Fatalf("sync status = %d, body = %s", syncRec.Code, syncRec.Body.String())
	}

	countReq := httptest.NewRequest(http.MethodGet, "/api/store-intel/app-snapshots/count", nil)
	countRec := httptest.NewRecorder()
	handler.ServeHTTP(countRec, countReq)
	if countRec.Code != http.StatusOK {
		t.Fatalf("count status = %d, body = %s", countRec.Code, countRec.Body.String())
	}
	var countResp gateway.Response[dto.AppSnapshotCountResponse]
	decodeResponse(t, countRec, &countResp)
	if countResp.Data.Total != 1 {
		t.Fatalf("unexpected snapshot count response: %+v", countResp.Data)
	}

	historyReq := httptest.NewRequest(
		http.MethodGet,
		"/api/store-intel/app-snapshots/history?app_id=com.demo&country=us&lang=en&limit=80",
		nil,
	)
	historyRec := httptest.NewRecorder()
	handler.ServeHTTP(historyRec, historyReq)
	if historyRec.Code != http.StatusOK {
		t.Fatalf("history status = %d, body = %s", historyRec.Code, historyRec.Body.String())
	}
	var historyResp gateway.Response[dto.ListAppSnapshotsResponse]
	decodeResponse(t, historyRec, &historyResp)
	if historyResp.Data.Total != 1 || historyResp.Data.Items[0].Version != "1.2.3" ||
		historyResp.Data.Items[0].RatingsCount == nil || *historyResp.Data.Items[0].RatingsCount != ratingsCount {
		t.Fatalf("unexpected snapshot history response: %+v", historyResp.Data)
	}

	recentReq := httptest.NewRequest(http.MethodGet, "/api/store-intel/app-snapshots/recent?limit=1", nil)
	recentRec := httptest.NewRecorder()
	handler.ServeHTTP(recentRec, recentReq)
	if recentRec.Code != http.StatusOK {
		t.Fatalf("recent status = %d, body = %s", recentRec.Code, recentRec.Body.String())
	}
	var recentResp gateway.Response[dto.ListAppSnapshotsResponse]
	decodeResponse(t, recentRec, &recentResp)
	if recentResp.Data.Total != 1 || recentResp.Data.Items[0].AppID != "com.demo" {
		t.Fatalf("unexpected recent snapshot response: %+v", recentResp.Data)
	}
}

func TestHTTPHandlerCachedAppDetailMissReturnsSuccess(t *testing.T) {
	module := storeintel.NewInMemoryModule(storeintel.Dependencies{})
	handler := gateway.NewHandler(module.Service)

	req := httptest.NewRequest(http.MethodGet, "/api/store-intel/apps/com.missing/cache?country=US&lang=EN", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("cache miss status = %d, body = %s", rec.Code, rec.Body.String())
	}
	var resp gateway.Response[dto.CachedAppDetailResponse]
	decodeResponse(t, rec, &resp)
	if resp.Data.Cached {
		t.Fatalf("cache miss should return cached=false: %+v", resp.Data)
	}
	if resp.Data.Detail.AppID != "com.missing" || resp.Data.Detail.Platform != dto.PlatformGooglePlay {
		t.Fatalf("cache miss should preserve identity: %+v", resp.Data.Detail)
	}
}

func TestHTTPHandlerChartsFetchSaveAndRankHistory(t *testing.T) {
	module := storeintel.NewInMemoryModule(storeintel.Dependencies{
		Upstream: httpFakeUpstream{chart: dto.FetchChartResponse{Items: []dto.ChartItem{
			{AppSummary: dto.AppSummary{AppID: "com.other"}, Rank: 1},
			{AppSummary: dto.AppSummary{AppID: "com.target"}, Rank: 2},
		}}},
	})
	handler := gateway.NewHandler(module.Service)

	fetchReq := httptest.NewRequest(http.MethodGet, "/api/store-intel/charts?chart_type=top_free&country=us&lang=en&limit=10", nil)
	fetchRec := httptest.NewRecorder()
	handler.ServeHTTP(fetchRec, fetchReq)
	if fetchRec.Code != http.StatusOK {
		t.Fatalf("fetch status = %d, body = %s", fetchRec.Code, fetchRec.Body.String())
	}
	var fetchResp gateway.Response[dto.FetchChartResponse]
	decodeResponse(t, fetchRec, &fetchResp)
	if fetchResp.Data.Total != 2 || fetchResp.Data.Items[1].AppID != "com.target" {
		t.Fatalf("unexpected chart fetch response: %+v", fetchResp.Data)
	}

	saveReq := httptest.NewRequest(
		http.MethodPost,
		"/api/store-intel/charts/snapshot",
		bytes.NewBufferString(`{"chart_type":"top_free","country":"us","lang":"en","items":[{"app_id":"com.target","rank":2}]}`),
	)
	saveRec := httptest.NewRecorder()
	handler.ServeHTTP(saveRec, saveReq)
	if saveRec.Code != http.StatusOK {
		t.Fatalf("save status = %d, body = %s", saveRec.Code, saveRec.Body.String())
	}
	var saveResp gateway.Response[dto.SaveChartSnapshotResponse]
	decodeResponse(t, saveRec, &saveResp)
	if saveResp.Data.Saved != 1 || saveResp.Data.CapturedAt == "" {
		t.Fatalf("unexpected chart save response: %+v", saveResp.Data)
	}

	rankReq := httptest.NewRequest(
		http.MethodPost,
		"/api/store-intel/chart-rank",
		bytes.NewBufferString(`{"app_id":"com.target","collection":"top_free","country":"us","lang":"en","limit":10}`),
	)
	rankRec := httptest.NewRecorder()
	handler.ServeHTTP(rankRec, rankReq)
	if rankRec.Code != http.StatusOK {
		t.Fatalf("rank status = %d, body = %s", rankRec.Code, rankRec.Body.String())
	}
	var rankResp gateway.Response[dto.ChartRankResponse]
	decodeResponse(t, rankRec, &rankResp)
	if !rankResp.Data.Found || rankResp.Data.Rank == nil || *rankResp.Data.Rank != 2 {
		t.Fatalf("unexpected chart rank response: %+v", rankResp.Data)
	}

	historyReq := httptest.NewRequest(
		http.MethodGet,
		"/api/store-intel/chart-rank/history?app_id=com.target&collection=top_free&country=us&lang=en",
		nil,
	)
	historyRec := httptest.NewRecorder()
	handler.ServeHTTP(historyRec, historyReq)
	if historyRec.Code != http.StatusOK {
		t.Fatalf("history status = %d, body = %s", historyRec.Code, historyRec.Body.String())
	}
	var historyResp gateway.Response[dto.ChartRankHistoryResponse]
	decodeResponse(t, historyRec, &historyResp)
	if historyResp.Data.Total != 1 || historyResp.Data.Items[0].Rank == nil || *historyResp.Data.Items[0].Rank != 2 {
		t.Fatalf("unexpected chart history response: %+v", historyResp.Data)
	}
}

func TestHTTPHandlerTrackedKeywordAndChartAppSync(t *testing.T) {
	module := storeintel.NewInMemoryModule(storeintel.Dependencies{
		Upstream: httpFakeUpstream{
			search: []dto.AppSummary{
				{Platform: dto.PlatformGooglePlay, AppID: "com.other"},
				{Platform: dto.PlatformGooglePlay, AppID: "com.target"},
			},
			chart: dto.FetchChartResponse{Items: []dto.ChartItem{
				{AppSummary: dto.AppSummary{AppID: "com.target"}, Rank: 1},
			}},
		},
	})
	handler := gateway.NewHandler(module.Service)

	addKeywordReq := httptest.NewRequest(
		http.MethodPost,
		"/api/store-intel/tracking/keywords",
		bytes.NewBufferString(`{"keyword":"notes","app_id":"com.target","country":"us","lang":"en"}`),
	)
	addKeywordRec := httptest.NewRecorder()
	handler.ServeHTTP(addKeywordRec, addKeywordReq)
	if addKeywordRec.Code != http.StatusOK {
		t.Fatalf("add keyword status = %d, body = %s", addKeywordRec.Code, addKeywordRec.Body.String())
	}
	var addKeywordResp gateway.Response[dto.TrackedKeyword]
	decodeResponse(t, addKeywordRec, &addKeywordResp)
	if addKeywordResp.Data.Keyword != "notes" || !addKeywordResp.Data.Enabled {
		t.Fatalf("unexpected add keyword response: %+v", addKeywordResp.Data)
	}

	syncKeywordReq := httptest.NewRequest(
		http.MethodPost,
		"/api/store-intel/tracking/keywords/sync",
		bytes.NewBufferString(`{"keyword":"notes","app_id":"com.target","country":"us","lang":"en","limit":10}`),
	)
	syncKeywordRec := httptest.NewRecorder()
	handler.ServeHTTP(syncKeywordRec, syncKeywordReq)
	if syncKeywordRec.Code != http.StatusOK {
		t.Fatalf("sync keyword status = %d, body = %s", syncKeywordRec.Code, syncKeywordRec.Body.String())
	}
	var syncKeywordResp gateway.Response[dto.SyncTrackedKeywordResponse]
	decodeResponse(t, syncKeywordRec, &syncKeywordResp)
	if syncKeywordResp.Data.Rank.Rank == nil || *syncKeywordResp.Data.Rank.Rank != 2 {
		t.Fatalf("unexpected sync keyword response: %+v", syncKeywordResp.Data)
	}

	addChartReq := httptest.NewRequest(
		http.MethodPost,
		"/api/store-intel/tracking/chart-apps",
		bytes.NewBufferString(`{"app_id":"com.target","collection":"top_free","country":"us","lang":"en"}`),
	)
	addChartRec := httptest.NewRecorder()
	handler.ServeHTTP(addChartRec, addChartReq)
	if addChartRec.Code != http.StatusOK {
		t.Fatalf("add chart status = %d, body = %s", addChartRec.Code, addChartRec.Body.String())
	}
	var addChartResp gateway.Response[dto.TrackedChartApp]
	decodeResponse(t, addChartRec, &addChartResp)
	if addChartResp.Data.Collection != "top_free" || !addChartResp.Data.Enabled {
		t.Fatalf("unexpected add chart response: %+v", addChartResp.Data)
	}

	syncChartReq := httptest.NewRequest(
		http.MethodPost,
		"/api/store-intel/tracking/chart-apps/sync",
		bytes.NewBufferString(`{"app_id":"com.target","collection":"top_free","country":"us","lang":"en","limit":10}`),
	)
	syncChartRec := httptest.NewRecorder()
	handler.ServeHTTP(syncChartRec, syncChartReq)
	if syncChartRec.Code != http.StatusOK {
		t.Fatalf("sync chart status = %d, body = %s", syncChartRec.Code, syncChartRec.Body.String())
	}
	var syncChartResp gateway.Response[dto.SyncTrackedChartAppResponse]
	decodeResponse(t, syncChartRec, &syncChartResp)
	if syncChartResp.Data.Rank.Rank == nil || *syncChartResp.Data.Rank.Rank != 1 {
		t.Fatalf("unexpected sync chart response: %+v", syncChartResp.Data)
	}

	listKeywordReq := httptest.NewRequest(http.MethodGet, "/api/store-intel/tracking/keywords", nil)
	listKeywordRec := httptest.NewRecorder()
	handler.ServeHTTP(listKeywordRec, listKeywordReq)
	var listKeywordResp gateway.Response[dto.ListTrackedKeywordsResponse]
	decodeResponse(t, listKeywordRec, &listKeywordResp)
	if listKeywordResp.Data.Total != 1 || listKeywordResp.Data.Items[0].LastSyncedAt == "" {
		t.Fatalf("unexpected keyword list response: %+v", listKeywordResp.Data)
	}

	listChartReq := httptest.NewRequest(http.MethodGet, "/api/store-intel/tracking/chart-apps", nil)
	listChartRec := httptest.NewRecorder()
	handler.ServeHTTP(listChartRec, listChartReq)
	var listChartResp gateway.Response[dto.ListTrackedChartAppsResponse]
	decodeResponse(t, listChartRec, &listChartResp)
	if listChartResp.Data.Total != 1 || listChartResp.Data.Items[0].LastSyncedAt == "" {
		t.Fatalf("unexpected chart list response: %+v", listChartResp.Data)
	}
}

func TestHTTPHandlerReviewsFetchSaveAndCache(t *testing.T) {
	rating := 2
	module := storeintel.NewInMemoryModule(storeintel.Dependencies{
		Upstream: httpFakeUpstream{review: dto.FetchReviewsResponse{
			Items: []dto.ReviewItem{{
				ReviewID:        "r1",
				UserName:        "Ana",
				Rating:          &rating,
				Content:         "rough",
				ReviewCreatedAt: "2026-06-18T01:00:00Z",
			}},
			NextToken: "next",
		}},
	})
	handler := gateway.NewHandler(module.Service)

	fetchReq := httptest.NewRequest(http.MethodGet, "/api/store-intel/apps/com.demo/reviews?country=us&lang=en&sort=newest", nil)
	fetchRec := httptest.NewRecorder()
	handler.ServeHTTP(fetchRec, fetchReq)
	if fetchRec.Code != http.StatusOK {
		t.Fatalf("fetch status = %d, body = %s", fetchRec.Code, fetchRec.Body.String())
	}
	var fetchResp gateway.Response[dto.FetchReviewsResponse]
	decodeResponse(t, fetchRec, &fetchResp)
	if fetchResp.Data.Total != 1 || fetchResp.Data.NextToken != "next" {
		t.Fatalf("unexpected fetch response: %+v", fetchResp.Data)
	}

	saveBody := bytes.NewBufferString(`{"country":"us","lang":"en","items":[{"review_id":"r1","user_name":"Ana","rating":2,"content":"rough","review_created_at":"2026-06-18T01:00:00Z"}]}`)
	saveReq := httptest.NewRequest(http.MethodPost, "/api/store-intel/apps/com.demo/reviews", saveBody)
	saveRec := httptest.NewRecorder()
	handler.ServeHTTP(saveRec, saveReq)
	if saveRec.Code != http.StatusOK {
		t.Fatalf("save status = %d, body = %s", saveRec.Code, saveRec.Body.String())
	}
	var saveResp gateway.Response[dto.SaveReviewsResponse]
	decodeResponse(t, saveRec, &saveResp)
	if saveResp.Data.Saved != 1 {
		t.Fatalf("unexpected save response: %+v", saveResp.Data)
	}

	cacheReq := httptest.NewRequest(http.MethodGet, "/api/store-intel/apps/com.demo/reviews/cache?limit=5", nil)
	cacheRec := httptest.NewRecorder()
	handler.ServeHTTP(cacheRec, cacheReq)
	if cacheRec.Code != http.StatusOK {
		t.Fatalf("cache status = %d, body = %s", cacheRec.Code, cacheRec.Body.String())
	}
	var cacheResp gateway.Response[dto.ListCachedReviewsResponse]
	decodeResponse(t, cacheRec, &cacheResp)
	if cacheResp.Data.Total != 1 || cacheResp.Data.Items[0].ReviewID != "r1" {
		t.Fatalf("unexpected cache response: %+v", cacheResp.Data)
	}
}

func TestHTTPHandlerCleanupHistory(t *testing.T) {
	module := storeintel.NewInMemoryModule(storeintel.Dependencies{})
	handler := gateway.NewHandler(module.Service)

	req := httptest.NewRequest(http.MethodPost, "/api/store-intel/history/cleanup", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("cleanup status = %d, body = %s", rec.Code, rec.Body.String())
	}
	var resp gateway.Response[dto.HistoryRetentionCleanupResponse]
	decodeResponse(t, rec, &resp)
	if resp.Data != (dto.HistoryRetentionCleanupResponse{}) {
		t.Fatalf("empty memory repo cleanup should be zero: %+v", resp.Data)
	}
}

func TestHTTPHandlerRefreshJobPersistsStatus(t *testing.T) {
	module := storeintel.NewInMemoryModule(storeintel.Dependencies{
		Upstream: httpFakeUpstream{search: []dto.AppSummary{{
			Platform: dto.PlatformGooglePlay,
			AppID:    "com.demo",
			Title:    "Demo",
		}}},
	})
	handler := gateway.NewHandler(module.Service)

	req := httptest.NewRequest(
		http.MethodPost,
		"/api/store-intel/refresh-jobs",
		bytes.NewBufferString(`{"kind":"search","query":"demo","country":"us","lang":"en","limit":5}`),
	)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)
	if rec.Code != http.StatusOK {
		t.Fatalf("enqueue status = %d, body = %s", rec.Code, rec.Body.String())
	}
	var enqueueResp gateway.Response[dto.RefreshJobResponse]
	decodeResponse(t, rec, &enqueueResp)
	if enqueueResp.Data.JobID == "" || enqueueResp.Data.Status != "queued" {
		t.Fatalf("unexpected enqueue response: %+v", enqueueResp.Data)
	}

	var fetched gateway.Response[dto.RefreshJobResponse]
	for attempt := 0; attempt < 50; attempt++ {
		getReq := httptest.NewRequest(http.MethodGet, "/api/store-intel/refresh-jobs/"+enqueueResp.Data.JobID, nil)
		getRec := httptest.NewRecorder()
		handler.ServeHTTP(getRec, getReq)
		if getRec.Code != http.StatusOK {
			t.Fatalf("get status = %d, body = %s", getRec.Code, getRec.Body.String())
		}
		decodeResponse(t, getRec, &fetched)
		if fetched.Data.Status == "completed" {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}
	if fetched.Data.JobID != enqueueResp.Data.JobID || fetched.Data.Kind != "search" ||
		fetched.Data.Status != "completed" || fetched.Data.FinishedAt == "" {
		t.Fatalf("unexpected persisted job response: %+v", fetched.Data)
	}
}

func TestHTTPHandlerRecoversUnfinishedRefreshJobsOnStartup(t *testing.T) {
	for _, status := range []string{"queued", "running"} {
		t.Run(status, func(t *testing.T) {
			module := storeintel.NewInMemoryModule(storeintel.Dependencies{
				Upstream: httpFakeUpstream{search: []dto.AppSummary{{
					Platform: dto.PlatformGooglePlay,
					AppID:    "com.demo",
					Title:    "Demo",
				}}},
			})
			jobID := "job-recover-" + status
			_, err := module.Service.CreateRefreshJob(
				context.Background(),
				dto.RefreshJobRequest{
					Kind:    "search",
					Query:   "demo",
					Country: "us",
					Lang:    "en",
					Limit:   5,
				},
				dto.RefreshJobResponse{
					JobID:       jobID,
					Kind:        "search",
					Status:      status,
					Message:     "left from prior process",
					RequestedAt: "2026-06-18T00:00:00Z",
					StartedAt:   "2026-06-18T00:00:01Z",
					UpdatedAt:   "2026-06-18T00:00:01Z",
				},
			)
			if err != nil {
				t.Fatalf("seed refresh job: %v", err)
			}
			handler := gateway.NewHandler(module.Service)

			var fetched gateway.Response[dto.RefreshJobResponse]
			for attempt := 0; attempt < 50; attempt++ {
				getReq := httptest.NewRequest(http.MethodGet, "/api/store-intel/refresh-jobs/"+jobID, nil)
				getRec := httptest.NewRecorder()
				handler.ServeHTTP(getRec, getReq)
				if getRec.Code != http.StatusOK {
					t.Fatalf("get status = %d, body = %s", getRec.Code, getRec.Body.String())
				}
				decodeResponse(t, getRec, &fetched)
				if fetched.Data.Status == "completed" {
					break
				}
				time.Sleep(10 * time.Millisecond)
			}
			if fetched.Data.JobID != jobID || fetched.Data.Status != "completed" ||
				fetched.Data.FinishedAt == "" {
				t.Fatalf("unexpected recovered job response: %+v", fetched.Data)
			}
		})
	}
}

func TestHTTPHandlerRejectsInvalidJSON(t *testing.T) {
	module := storeintel.NewInMemoryModule(storeintel.Dependencies{})
	handler := gateway.NewHandler(module.Service)

	req := httptest.NewRequest(http.MethodPost, "/api/store-intel/tracking/apps", bytes.NewBufferString(`{"app_id":`))
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, body = %s", rec.Code, rec.Body.String())
	}
	var resp gateway.Response[map[string]any]
	decodeResponse(t, rec, &resp)
	if resp.Code != gateway.ErrorCodeBadRequest || resp.Data["error_code"] != "STORE_INTEL_REQUEST_INVALID" {
		t.Fatalf("unexpected error envelope: %+v", resp)
	}
}

func decodeResponse[T any](t *testing.T, rec *httptest.ResponseRecorder, dst *gateway.Response[T]) {
	t.Helper()
	if err := json.Unmarshal(rec.Body.Bytes(), dst); err != nil {
		t.Fatalf("decode response %q: %v", rec.Body.String(), err)
	}
}
