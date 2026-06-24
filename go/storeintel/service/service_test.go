package service_test

import (
	"context"
	"errors"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/catch-radar/storeintel/dto"
	"github.com/catch-radar/storeintel/repo"
	"github.com/catch-radar/storeintel/service"
)

type fakeUpstream struct {
	mu               sync.Mutex
	searchItems      []dto.AppSummary
	searchByQuery    map[string][]dto.AppSummary
	searchErr        error
	searchErrByProxy map[string]error
	searchReqs       []dto.SearchAppsRequest
	suggestByTerm    map[string][]string
	suggestErr       error
	suggestReqs      []dto.SuggestRequest
	similar          []dto.AppSummary
	similarErr       error
	similarReqs      []dto.SimilarAppsRequest
	permissions      map[string][]string
	permissionsErr   error
	permissionsReqs  []dto.AppPermissionsRequest
	details          []dto.AppDetail
	detailErr        error
	detailIndex      int
	charts           dto.FetchChartResponse
	chartErr         error
	chartReqs        []dto.FetchChartRequest
	reviews          dto.FetchReviewsResponse
	reviewErr        error
	reviewReqs       []dto.FetchReviewsRequest
}

type fakeKeywordCorpusClient struct {
	candidates     []string
	candidateErr   error
	candidateReqs  []service.KeywordCorpusCandidateRequest
	contributeErr  error
	contributeReqs []service.KeywordCorpusContributeRequest
}

func (f *fakeKeywordCorpusClient) Candidates(_ context.Context, req service.KeywordCorpusCandidateRequest) ([]string, error) {
	f.candidateReqs = append(f.candidateReqs, req)
	if f.candidateErr != nil {
		return nil, f.candidateErr
	}
	return append([]string(nil), f.candidates...), nil
}

func (f *fakeKeywordCorpusClient) Contribute(_ context.Context, req service.KeywordCorpusContributeRequest) error {
	f.contributeReqs = append(f.contributeReqs, req)
	return f.contributeErr
}

func (f *fakeUpstream) SearchApps(_ context.Context, req dto.SearchAppsRequest) ([]dto.AppSummary, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.searchReqs = append(f.searchReqs, req)
	if f.searchErr != nil {
		return nil, f.searchErr
	}
	if f.searchErrByProxy != nil {
		if err, ok := f.searchErrByProxy[req.Proxy]; ok {
			return nil, err
		}
	}
	if f.searchByQuery != nil {
		if items, ok := f.searchByQuery[strings.ToLower(strings.TrimSpace(req.Query))]; ok {
			return append([]dto.AppSummary(nil), items...), nil
		}
	}
	return append([]dto.AppSummary(nil), f.searchItems...), nil
}

func (f *fakeUpstream) Suggest(_ context.Context, req dto.SuggestRequest) ([]string, error) {
	f.suggestReqs = append(f.suggestReqs, req)
	if f.suggestErr != nil {
		return nil, f.suggestErr
	}
	if f.suggestByTerm != nil {
		return f.suggestByTerm[strings.ToLower(strings.TrimSpace(req.Term))], nil
	}
	return nil, nil
}

func (f *fakeUpstream) GetAppDetail(context.Context, dto.GetAppDetailRequest) (dto.AppDetail, error) {
	if f.detailErr != nil {
		return dto.AppDetail{}, f.detailErr
	}
	if len(f.details) == 0 {
		return dto.AppDetail{}, nil
	}
	index := f.detailIndex
	if index >= len(f.details) {
		index = len(f.details) - 1
	}
	f.detailIndex++
	return f.details[index], nil
}

func (f *fakeUpstream) SimilarApps(_ context.Context, req dto.SimilarAppsRequest) ([]dto.AppSummary, error) {
	f.similarReqs = append(f.similarReqs, req)
	if f.similarErr != nil {
		return nil, f.similarErr
	}
	return f.similar, nil
}

func (f *fakeUpstream) GetAppPermissions(_ context.Context, req dto.AppPermissionsRequest) (map[string][]string, error) {
	f.permissionsReqs = append(f.permissionsReqs, req)
	if f.permissionsErr != nil {
		return nil, f.permissionsErr
	}
	return f.permissions, nil
}

func (f *fakeUpstream) FetchChart(_ context.Context, req dto.FetchChartRequest) (dto.FetchChartResponse, error) {
	f.chartReqs = append(f.chartReqs, req)
	if f.chartErr != nil {
		return dto.FetchChartResponse{}, f.chartErr
	}
	return f.charts, nil
}

func (f *fakeUpstream) FetchReviews(_ context.Context, req dto.FetchReviewsRequest) (dto.FetchReviewsResponse, error) {
	f.reviewReqs = append(f.reviewReqs, req)
	if f.reviewErr != nil {
		return dto.FetchReviewsResponse{}, f.reviewErr
	}
	return f.reviews, nil
}

func containsString(items []string, target string) bool {
	for _, item := range items {
		if item == target {
			return true
		}
	}
	return false
}

func indexOfString(items []string, target string) int {
	for index, item := range items {
		if item == target {
			return index
		}
	}
	return len(items)
}

func corpusContainsKeyword(items []repo.KeywordCorpusItem, target string) bool {
	for _, item := range items {
		if item.Keyword == target {
			return true
		}
	}
	return false
}

func TestSearchCachedAppsHydratesRowsFromLatestSnapshot(t *testing.T) {
	rating := 4.7
	ratingsCount := int64(1200)
	minInstalls := int64(100000)
	free := true
	upstream := &fakeUpstream{
		searchItems: []dto.AppSummary{{
			Platform: dto.PlatformGooglePlay,
			AppID:    "com.hotshotai",
			StoreURL: "https://play.google.com/store/apps/details?id=com.hotshotai",
		}},
		details: []dto.AppDetail{{
			AppSummary: dto.AppSummary{
				Platform:     dto.PlatformGooglePlay,
				AppID:        "com.hotshotai",
				Title:        "Hotshot AI: Photo Generator",
				Developer:    "Hotshot Studio",
				Category:     "PHOTOGRAPHY",
				Summary:      "Create AI meme photos.",
				Rating:       &rating,
				RatingsCount: &ratingsCount,
				Installs:     "100K+",
				MinInstalls:  &minInstalls,
				Price:        "0",
				Currency:     "USD",
				Free:         &free,
				IconURL:      "https://example.test/icon.png",
				StoreURL:     "https://play.google.com/store/apps/details?id=com.hotshotai",
			},
		}},
	}
	svc := service.NewStoreIntelService(repo.NewMemoryRepo(), upstream)
	ctx := context.Background()

	if _, err := svc.SearchApps(ctx, dto.SearchAppsRequest{Query: "hotshotai", Country: "US", Lang: "EN", Limit: 10}); err != nil {
		t.Fatalf("SearchApps returned error: %v", err)
	}
	if _, err := svc.SyncAppNow(ctx, dto.SyncAppNowRequest{AppID: "com.hotshotai", Country: "US", Lang: "EN"}); err != nil {
		t.Fatalf("SyncAppNow returned error: %v", err)
	}

	cached, err := svc.SearchCachedApps(ctx, dto.SearchAppsRequest{Query: "hotshotai", Country: "US", Lang: "EN", Limit: 10})
	if err != nil {
		t.Fatalf("SearchCachedApps returned error: %v", err)
	}
	if cached.Total != 1 {
		t.Fatalf("cached total = %d, want 1: %+v", cached.Total, cached)
	}
	row := cached.Items[0]
	if row.Title != "Hotshot AI: Photo Generator" || row.Developer != "Hotshot Studio" ||
		row.Category != "PHOTOGRAPHY" || row.Summary == "" {
		t.Fatalf("summary fields not hydrated: %+v", row)
	}
	if row.Rating == nil || *row.Rating != rating || row.RatingsCount == nil ||
		*row.RatingsCount != ratingsCount || row.Installs != "100K+" {
		t.Fatalf("metric fields not hydrated: %+v", row)
	}
	if row.Price != "0" || row.Currency != "USD" || row.Free == nil || !*row.Free ||
		row.IconURL == "" || row.StoreURL == "" {
		t.Fatalf("commercial/media fields not hydrated: %+v", row)
	}
}

func TestRankKeywordUsesSearchOrder(t *testing.T) {
	upstream := &fakeUpstream{searchItems: []dto.AppSummary{
		{Platform: dto.PlatformGooglePlay, AppID: "com.one"},
		{Platform: dto.PlatformGooglePlay, AppID: "com.Target"},
	}}
	svc := service.NewStoreIntelService(repo.NewMemoryRepo(), upstream)

	result, err := svc.RankKeyword(context.Background(), dto.KeywordRankRequest{
		Keyword: "notes",
		AppID:   "com.target",
		Limit:   10,
	})
	if err != nil {
		t.Fatalf("RankKeyword returned error: %v", err)
	}
	if !result.Found || result.Rank == nil || *result.Rank != 2 {
		t.Fatalf("unexpected rank result: %+v", result)
	}
	if result.Country != "us" || result.Lang != "en" {
		t.Fatalf("default locale not applied: %+v", result)
	}
}

func TestAnalyzeKeywordCoverageUsesDetailSeedsAndSearchOrder(t *testing.T) {
	upstream := &fakeUpstream{
		details: []dto.AppDetail{{
			AppSummary: dto.AppSummary{
				AppID:    "com.target",
				Title:    "Photo Editor: Collage Maker",
				Category: "Photography",
				Summary:  "Edit photos quickly with filters and collage tools",
			},
			Description: "Photo editor for quick filters, collage layouts, and image editing.",
		}},
		searchByQuery: map[string][]dto.AppSummary{
			"photo editor": {
				{Platform: dto.PlatformGooglePlay, AppID: "com.other"},
				{Platform: dto.PlatformGooglePlay, AppID: "com.target"},
			},
		},
	}
	svc := service.NewStoreIntelService(repo.NewMemoryRepo(), upstream)

	result, err := svc.AnalyzeKeywordCoverage(context.Background(), dto.KeywordCoverageRequest{
		AppID:   " com.target ",
		Country: "US",
		Lang:    "EN",
		Limit:   10,
	})
	if err != nil {
		t.Fatalf("AnalyzeKeywordCoverage returned error: %v", err)
	}
	if result.Platform != dto.PlatformGooglePlay || result.AppID != "com.target" ||
		result.CanonicalAppID != "com.target" || result.Country != "us" || result.Lang != "en" {
		t.Fatalf("coverage identity not normalized: %+v", result)
	}
	if result.CandidateCount == 0 || result.Candidates[0] != "photo editor" {
		t.Fatalf("expected title head as first candidate: %+v", result.Candidates)
	}
	if len(result.Covered) != 1 || result.Covered[0].Keyword != "photo editor" ||
		result.Covered[0].Rank != 2 || result.CheckedLimit != 10 {
		t.Fatalf("unexpected coverage hits: %+v", result)
	}
	if len(upstream.searchReqs) == 0 || upstream.searchReqs[0].Query != "photo editor" ||
		upstream.searchReqs[0].Country != "us" || upstream.searchReqs[0].Lang != "en" {
		t.Fatalf("coverage search request not normalized: %+v", upstream.searchReqs)
	}
}

func TestAnalyzeKeywordCoverageMergesAutocompleteCandidates(t *testing.T) {
	upstream := &fakeUpstream{
		details: []dto.AppDetail{{
			AppSummary: dto.AppSummary{
				AppID:   "com.target",
				Title:   "Photo Editor",
				Summary: "Edit photos quickly",
			},
		}},
		suggestByTerm: map[string][]string{
			"editor": {"video editor"},
		},
		searchByQuery: map[string][]dto.AppSummary{
			"video editor": {
				{Platform: dto.PlatformGooglePlay, AppID: "com.other"},
				{Platform: dto.PlatformGooglePlay, AppID: "com.target"},
			},
		},
	}
	svc := service.NewStoreIntelService(repo.NewMemoryRepo(), upstream)

	result, err := svc.AnalyzeKeywordCoverage(context.Background(), dto.KeywordCoverageRequest{
		AppID: "com.target",
		Limit: 10,
	})
	if err != nil {
		t.Fatalf("AnalyzeKeywordCoverage returned error: %v", err)
	}
	if !containsString(result.Candidates, "video editor") {
		t.Fatalf("autocomplete candidate missing: %+v", result.Candidates)
	}
	if len(result.Covered) != 1 || result.Covered[0].Keyword != "video editor" || result.Covered[0].Rank != 2 {
		t.Fatalf("unexpected coverage hits: %+v", result.Covered)
	}
	if len(upstream.suggestReqs) == 0 {
		t.Fatal("expected coverage discovery to call upstream Suggest")
	}
}

func TestAnalyzeKeywordCoverageDeepExpandsNestedAutocomplete(t *testing.T) {
	upstream := &fakeUpstream{
		details: []dto.AppDetail{{
			AppSummary: dto.AppSummary{
				AppID: "com.target",
				Title: "Photo Editor",
			},
		}},
		suggestByTerm: map[string][]string{
			"photo editor":            {"photo editor background"},
			"photo editor background": {"photo editor background changer"},
		},
		searchByQuery: map[string][]dto.AppSummary{
			"photo editor background changer": {
				{Platform: dto.PlatformGooglePlay, AppID: "com.target"},
			},
		},
	}
	svc := service.NewStoreIntelService(repo.NewMemoryRepo(), upstream)

	result, err := svc.AnalyzeKeywordCoverage(context.Background(), dto.KeywordCoverageRequest{
		AppID: "com.target",
		Limit: 10,
		Deep:  true,
	})
	if err != nil {
		t.Fatalf("AnalyzeKeywordCoverage returned error: %v", err)
	}
	if !containsString(result.Candidates, "photo editor background changer") {
		t.Fatalf("nested autocomplete candidate missing: %+v", result.Candidates)
	}
	if len(result.Covered) != 1 || result.Covered[0].Keyword != "photo editor background changer" || result.Covered[0].Rank != 1 {
		t.Fatalf("unexpected deep coverage hits: %+v", result.Covered)
	}
	if len(upstream.suggestReqs) < 2 || upstream.suggestReqs[0].Count != 6 {
		t.Fatalf("nested suggest requests not issued as expected: %+v", upstream.suggestReqs)
	}
}

func TestAnalyzeKeywordCoverageRefluxesAndConfirmsCorpusKeywords(t *testing.T) {
	ctx := context.Background()
	store := repo.NewMemoryRepo()
	if added, err := store.RecordKeywordCorpus(ctx, repo.KeywordCorpusRecordInput{
		Platform: dto.PlatformGooglePlay,
		Country:  "us",
		Lang:     "en",
		SeenAt:   "2026-06-18T00:00:00Z",
		Items: []repo.KeywordCorpusItem{{
			Keyword: "photo enhancer",
			Source:  "covered",
		}},
	}); err != nil || added != 1 {
		t.Fatalf("preseed corpus added=%d err=%v", added, err)
	}
	upstream := &fakeUpstream{
		details: []dto.AppDetail{{
			AppSummary: dto.AppSummary{
				AppID:   "com.target",
				Title:   "Photo Editor",
				Summary: "Edit photos quickly",
			},
		}},
		searchByQuery: map[string][]dto.AppSummary{
			"photo enhancer": {
				{Platform: dto.PlatformGooglePlay, AppID: "com.target"},
			},
		},
	}
	svc := service.NewStoreIntelService(store, upstream, service.WithConfig(service.Config{
		Now: func() time.Time {
			return time.Date(2026, 6, 18, 1, 2, 3, 0, time.UTC)
		},
	}))

	result, err := svc.AnalyzeKeywordCoverage(ctx, dto.KeywordCoverageRequest{
		AppID: "com.target",
		Limit: 10,
	})
	if err != nil {
		t.Fatalf("AnalyzeKeywordCoverage returned error: %v", err)
	}
	if !containsString(result.Candidates, "photo enhancer") {
		t.Fatalf("corpus candidate missing: %+v", result.Candidates)
	}
	if len(result.Covered) != 1 || result.Covered[0].Keyword != "photo enhancer" ||
		result.Covered[0].Rank != 1 {
		t.Fatalf("unexpected corpus coverage hits: %+v", result.Covered)
	}
	corpus, err := store.ListKeywordCorpus(ctx, repo.KeywordCorpusFilter{
		Platform: dto.PlatformGooglePlay,
		Country:  "us",
		Lang:     "en",
	})
	if err != nil {
		t.Fatalf("ListKeywordCorpus returned error: %v", err)
	}
	var found repo.KeywordCorpusItem
	for _, item := range corpus {
		if item.Keyword == "photo enhancer" {
			found = item
			break
		}
	}
	if found.Keyword == "" || !found.Confirmed || found.HitCount < 3 ||
		found.LastSeenAt != "2026-06-18T01:02:03Z" {
		t.Fatalf("covered corpus keyword not confirmed/sedimented: %+v", found)
	}
}

func TestAnalyzeKeywordCoverageRefluxesRemoteCorpusBeforeLocal(t *testing.T) {
	ctx := context.Background()
	store := repo.NewMemoryRepo()
	if added, err := store.RecordKeywordCorpus(ctx, repo.KeywordCorpusRecordInput{
		Platform: dto.PlatformGooglePlay,
		Country:  "us",
		Lang:     "en",
		SeenAt:   "2026-06-18T00:00:00Z",
		Items: []repo.KeywordCorpusItem{{
			Keyword: "photo local",
			Source:  "covered",
		}},
	}); err != nil || added != 1 {
		t.Fatalf("preseed corpus added=%d err=%v", added, err)
	}
	remote := &fakeKeywordCorpusClient{candidates: []string{"photo remote", "photo local"}}
	upstream := &fakeUpstream{
		details: []dto.AppDetail{{
			AppSummary: dto.AppSummary{
				AppID: "com.target",
				Title: "Photo Editor",
			},
		}},
		searchByQuery: map[string][]dto.AppSummary{
			"photo remote": {
				{Platform: dto.PlatformGooglePlay, AppID: "com.target"},
			},
		},
	}
	svc := service.NewStoreIntelService(
		store,
		upstream,
		service.WithKeywordCorpusClient(remote),
	)

	result, err := svc.AnalyzeKeywordCoverage(ctx, dto.KeywordCoverageRequest{
		AppID: "com.target",
		Limit: 10,
	})
	if err != nil {
		t.Fatalf("AnalyzeKeywordCoverage returned error: %v", err)
	}
	if !containsString(result.Candidates, "photo remote") || !containsString(result.Candidates, "photo local") {
		t.Fatalf("remote/local corpus candidates not merged: %+v", result.Candidates)
	}
	if indexOfString(result.Candidates, "photo remote") > indexOfString(result.Candidates, "photo local") {
		t.Fatalf("remote corpus should be merged before local corpus: %+v", result.Candidates)
	}
	if len(remote.candidateReqs) != 1 || remote.candidateReqs[0].Country != "us" ||
		remote.candidateReqs[0].Lang != "en" || remote.candidateReqs[0].Limit != 120 {
		t.Fatalf("unexpected remote corpus candidate request: %+v", remote.candidateReqs)
	}
	if _, ok := remote.candidateReqs[0].SeedTokens["photo"]; !ok {
		t.Fatalf("remote corpus request missing seed token: %+v", remote.candidateReqs[0].SeedTokens)
	}
	if len(result.Covered) != 1 || result.Covered[0].Keyword != "photo remote" {
		t.Fatalf("remote corpus hit not scanned/covered: %+v", result.Covered)
	}
}

func TestAnalyzeKeywordCoverageRoutesProxyPoolSearchesThroughProxies(t *testing.T) {
	ctx := context.Background()
	store := repo.NewMemoryRepo()
	upstream := &fakeUpstream{
		searchByQuery: map[string][]dto.AppSummary{
			"photo editor": {
				{Platform: dto.PlatformGooglePlay, AppID: "com.target"},
			},
			"video editor": {
				{Platform: dto.PlatformGooglePlay, AppID: "com.other"},
				{Platform: dto.PlatformGooglePlay, AppID: "com.target"},
			},
		},
	}
	svc := service.NewStoreIntelService(store, upstream)
	if _, err := svc.SetSettings(ctx, map[string]string{
		"coverage_proxies":     "http://p1:8080\np2:3128\nhttp://p1:8080",
		"coverage_concurrency": "3",
	}); err != nil {
		t.Fatalf("SetSettings returned error: %v", err)
	}

	result, err := svc.AnalyzeKeywordCoverage(ctx, dto.KeywordCoverageRequest{
		AppID:          "com.target",
		CanonicalAppID: "com.target",
		Limit:          10,
		Candidates:     []string{"photo editor", "video editor", "nope"},
	})
	if err != nil {
		t.Fatalf("AnalyzeKeywordCoverage returned error: %v", err)
	}
	if len(result.Covered) != 2 {
		t.Fatalf("unexpected proxy-backed coverage hits: %+v", result.Covered)
	}
	if len(upstream.searchReqs) != 3 {
		t.Fatalf("expected all candidates searched, got %+v", upstream.searchReqs)
	}
	for _, req := range upstream.searchReqs {
		if req.Proxy == "" {
			t.Fatalf("proxy-backed coverage search should not go direct: %+v", upstream.searchReqs)
		}
		if req.Proxy != "http://p1:8080" && req.Proxy != "http://p2:3128" {
			t.Fatalf("unexpected proxy URL normalization: %+v", upstream.searchReqs)
		}
	}
}

func TestAnalyzeKeywordCoverageRetriesNextProxyAfterFailure(t *testing.T) {
	ctx := context.Background()
	store := repo.NewMemoryRepo()
	upstream := &fakeUpstream{
		searchByQuery: map[string][]dto.AppSummary{
			"photo editor": {
				{Platform: dto.PlatformGooglePlay, AppID: "com.target"},
			},
		},
		searchErrByProxy: map[string]error{
			"http://dead:8080": errors.New("proxy dead"),
		},
	}
	svc := service.NewStoreIntelService(store, upstream)
	if _, err := svc.SetSettings(ctx, map[string]string{
		"coverage_proxies":     "http://dead:8080 http://good:8080",
		"coverage_concurrency": "1",
	}); err != nil {
		t.Fatalf("SetSettings returned error: %v", err)
	}

	result, err := svc.AnalyzeKeywordCoverage(ctx, dto.KeywordCoverageRequest{
		AppID:          "com.target",
		CanonicalAppID: "com.target",
		Limit:          10,
		Candidates:     []string{"photo editor"},
	})
	if err != nil {
		t.Fatalf("AnalyzeKeywordCoverage returned error: %v", err)
	}
	if len(result.Covered) != 1 || result.Covered[0].Keyword != "photo editor" {
		t.Fatalf("proxy retry should recover the keyword search: %+v", result.Covered)
	}
	if len(upstream.searchReqs) != 2 ||
		upstream.searchReqs[0].Proxy != "http://dead:8080" ||
		upstream.searchReqs[1].Proxy != "http://good:8080" {
		t.Fatalf("proxy retry order not preserved: %+v", upstream.searchReqs)
	}
}

func TestAnalyzeKeywordCoverageWithProgressReportsEachKeyword(t *testing.T) {
	ctx := context.Background()
	upstream := &fakeUpstream{
		searchByQuery: map[string][]dto.AppSummary{
			"photo editor": {
				{Platform: dto.PlatformGooglePlay, AppID: "com.target"},
			},
			"video editor": {
				{Platform: dto.PlatformGooglePlay, AppID: "com.other"},
				{Platform: dto.PlatformGooglePlay, AppID: "com.target"},
			},
		},
	}
	svc := service.NewStoreIntelService(repo.NewMemoryRepo(), upstream)
	var progress []string

	result, err := svc.AnalyzeKeywordCoverageWithProgress(
		ctx,
		dto.KeywordCoverageRequest{
			AppID:          "com.target",
			CanonicalAppID: "com.target",
			Limit:          10,
			Candidates:     []string{"photo editor", "video editor"},
		},
		func(message string, fraction float64) {
			progress = append(progress, message)
			if fraction <= 0 || fraction > 1 {
				t.Fatalf("progress fraction out of range: %v", fraction)
			}
		},
	)
	if err != nil {
		t.Fatalf("AnalyzeKeywordCoverageWithProgress returned error: %v", err)
	}
	if len(result.Covered) != 2 {
		t.Fatalf("unexpected coverage result: %+v", result.Covered)
	}
	if len(progress) != 2 ||
		progress[0] != "覆盖检测 1/2：photo editor" ||
		progress[1] != "覆盖检测 2/2：video editor" {
		t.Fatalf("unexpected progress messages: %+v", progress)
	}
}

func TestAnalyzeKeywordCoverageDeepSedimentsAlphabetSoupOnlyToCorpus(t *testing.T) {
	ctx := context.Background()
	store := repo.NewMemoryRepo()
	upstream := &fakeUpstream{
		details: []dto.AppDetail{{
			AppSummary: dto.AppSummary{
				AppID: "com.target",
				Title: "Photo Editor",
			},
		}},
		suggestByTerm: map[string][]string{
			"photo editor a": {"photo ai editor"},
		},
	}
	svc := service.NewStoreIntelService(store, upstream, service.WithConfig(service.Config{
		Now: func() time.Time {
			return time.Date(2026, 6, 18, 2, 3, 4, 0, time.UTC)
		},
	}))

	result, err := svc.AnalyzeKeywordCoverage(ctx, dto.KeywordCoverageRequest{
		AppID: "com.target",
		Limit: 10,
		Deep:  true,
	})
	if err != nil {
		t.Fatalf("AnalyzeKeywordCoverage returned error: %v", err)
	}
	if containsString(result.Candidates, "photo ai editor") {
		t.Fatalf("alphabet-soup keyword should not spend this scan's search budget: %+v", result.Candidates)
	}
	if len(upstream.searchReqs) == 0 {
		t.Fatal("expected coverage scan to search non-soup candidates")
	}
	for _, req := range upstream.searchReqs {
		if req.Query == "photo ai editor" {
			t.Fatalf("alphabet-soup keyword should not be searched in the same scan: %+v", upstream.searchReqs)
		}
	}
	corpus, err := store.ListKeywordCorpus(ctx, repo.KeywordCorpusFilter{
		Platform: dto.PlatformGooglePlay,
		Country:  "us",
		Lang:     "en",
	})
	if err != nil {
		t.Fatalf("ListKeywordCorpus returned error: %v", err)
	}
	var soup repo.KeywordCorpusItem
	for _, item := range corpus {
		if item.Keyword == "photo ai editor" {
			soup = item
			break
		}
	}
	if soup.Keyword == "" || soup.Source != "soup" || soup.Confirmed ||
		soup.LastSeenAt != "2026-06-18T02:03:04Z" {
		t.Fatalf("alphabet-soup keyword not sedimented as corpus-only: %+v", soup)
	}
}

func TestAnalyzeKeywordCoverageRemoteContributionSkipsUnconfirmedSoup(t *testing.T) {
	ctx := context.Background()
	store := repo.NewMemoryRepo()
	remote := &fakeKeywordCorpusClient{}
	upstream := &fakeUpstream{
		details: []dto.AppDetail{{
			AppSummary: dto.AppSummary{
				AppID: "com.target",
				Title: "Photo Editor",
			},
		}},
		suggestByTerm: map[string][]string{
			"photo editor a": {"photo ai editor"},
		},
	}
	svc := service.NewStoreIntelService(
		store,
		upstream,
		service.WithKeywordCorpusClient(remote),
	)

	if _, err := svc.AnalyzeKeywordCoverage(ctx, dto.KeywordCoverageRequest{
		AppID: "com.target",
		Limit: 10,
		Deep:  true,
	}); err != nil {
		t.Fatalf("AnalyzeKeywordCoverage returned error: %v", err)
	}
	if len(remote.contributeReqs) == 0 {
		t.Fatal("expected non-soup corpus candidates to be contributed remotely")
	}
	for _, req := range remote.contributeReqs {
		for _, item := range req.Items {
			if item.Keyword == "photo ai editor" {
				t.Fatalf("unconfirmed soup keyword should stay local-only: %+v", remote.contributeReqs)
			}
		}
	}
	corpus, err := store.ListKeywordCorpus(ctx, repo.KeywordCorpusFilter{
		Platform: dto.PlatformGooglePlay,
		Country:  "us",
		Lang:     "en",
	})
	if err != nil {
		t.Fatalf("ListKeywordCorpus returned error: %v", err)
	}
	if !corpusContainsKeyword(corpus, "photo ai editor") {
		t.Fatalf("soup keyword should still be stored locally: %+v", corpus)
	}
}

func TestSimilarAppsNormalizesLocaleLimitAndItems(t *testing.T) {
	upstream := &fakeUpstream{similar: []dto.AppSummary{
		{AppID: "com.related", Title: "Related"},
	}}
	svc := service.NewStoreIntelService(repo.NewMemoryRepo(), upstream)

	result, err := svc.SimilarApps(context.Background(), dto.SimilarAppsRequest{
		AppID:   " com.demo ",
		Country: "JP",
		Lang:    "JA",
		Limit:   500,
	})
	if err != nil {
		t.Fatalf("SimilarApps returned error: %v", err)
	}
	if result.Total != 1 || result.Items[0].Platform != dto.PlatformGooglePlay ||
		result.Items[0].StoreURL == "" || result.Items[0].AppID != "com.related" {
		t.Fatalf("similar app items not normalized: %+v", result)
	}
	if len(upstream.similarReqs) != 1 || upstream.similarReqs[0].Country != "jp" ||
		upstream.similarReqs[0].Lang != "ja" || upstream.similarReqs[0].Limit != 100 {
		t.Fatalf("similar request not normalized: %+v", upstream.similarReqs)
	}
}

func TestGetAppPermissionsNormalizesLocaleAndReturnsGroups(t *testing.T) {
	upstream := &fakeUpstream{permissions: map[string][]string{
		"Location": {"approximate location"},
	}}
	svc := service.NewStoreIntelService(repo.NewMemoryRepo(), upstream)

	result, err := svc.GetAppPermissions(context.Background(), dto.AppPermissionsRequest{
		AppID:   " com.demo ",
		Country: "JP",
		Lang:    "JA",
	})
	if err != nil {
		t.Fatalf("GetAppPermissions returned error: %v", err)
	}
	if len(result.Groups["Location"]) != 1 || result.Groups["Location"][0] != "approximate location" {
		t.Fatalf("unexpected permissions response: %+v", result)
	}
	if len(upstream.permissionsReqs) != 1 || upstream.permissionsReqs[0].Country != "jp" ||
		upstream.permissionsReqs[0].Lang != "ja" || upstream.permissionsReqs[0].AppID != "com.demo" {
		t.Fatalf("permissions request not normalized: %+v", upstream.permissionsReqs)
	}
}

func TestRankKeywordPersistsOneRowPerDayAndHistory(t *testing.T) {
	now := time.Date(2026, 6, 18, 9, 30, 0, 0, time.UTC)
	upstream := &fakeUpstream{searchItems: []dto.AppSummary{
		{Platform: dto.PlatformGooglePlay, AppID: "com.first"},
		{Platform: dto.PlatformGooglePlay, AppID: "com.target"},
	}}
	store := repo.NewMemoryRepo()
	svc := service.NewStoreIntelService(store, upstream, service.WithConfig(service.Config{
		Now: func() time.Time { return now },
	}))

	first, err := svc.RankKeyword(context.Background(), dto.KeywordRankRequest{
		Keyword: "notes",
		AppID:   "com.target",
		Limit:   10,
	})
	if err != nil {
		t.Fatalf("first RankKeyword returned error: %v", err)
	}
	if first.Rank == nil || *first.Rank != 2 {
		t.Fatalf("unexpected first rank: %+v", first)
	}

	upstream.searchItems = []dto.AppSummary{{Platform: dto.PlatformGooglePlay, AppID: "com.target"}}
	second, err := svc.RankKeyword(context.Background(), dto.KeywordRankRequest{
		Keyword: "notes",
		AppID:   "com.target",
		Limit:   10,
	})
	if err != nil {
		t.Fatalf("second RankKeyword returned error: %v", err)
	}
	if second.Rank == nil || *second.Rank != 1 {
		t.Fatalf("unexpected second rank: %+v", second)
	}

	history, err := svc.ListKeywordRankHistory(context.Background(), dto.KeywordRankHistoryRequest{
		Keyword: "notes",
		AppID:   "com.target",
		Country: "us",
		Lang:    "en",
	})
	if err != nil {
		t.Fatalf("ListKeywordRankHistory returned error: %v", err)
	}
	if history.Total != 1 || history.Items[0].Rank == nil || *history.Items[0].Rank != 1 {
		t.Fatalf("same-day upsert not reflected in history: %+v", history)
	}

	now = now.Add(24 * time.Hour)
	upstream.searchItems = []dto.AppSummary{
		{Platform: dto.PlatformGooglePlay, AppID: "com.other"},
		{Platform: dto.PlatformGooglePlay, AppID: "com.target"},
	}
	if _, err := svc.RankKeyword(context.Background(), dto.KeywordRankRequest{
		Keyword: "notes",
		AppID:   "com.target",
		Limit:   10,
	}); err != nil {
		t.Fatalf("third RankKeyword returned error: %v", err)
	}
	history, err = svc.ListKeywordRankHistory(context.Background(), dto.KeywordRankHistoryRequest{
		Keyword: "notes",
		AppID:   "com.target",
		Country: "us",
		Lang:    "en",
	})
	if err != nil {
		t.Fatalf("second ListKeywordRankHistory returned error: %v", err)
	}
	if history.Total != 2 || history.Items[0].CapturedAt >= history.Items[1].CapturedAt {
		t.Fatalf("history should contain two days in ascending order: %+v", history)
	}

	recent, err := svc.ListRecentKeywordRanks(context.Background(), dto.KeywordRankRecentRequest{
		AppID: "com.target", Country: "us", Lang: "en", Limit: 2,
	})
	if err != nil {
		t.Fatalf("ListRecentKeywordRanks returned error: %v", err)
	}
	if recent.Total != 2 || recent.Items[0].CapturedAt <= recent.Items[1].CapturedAt {
		t.Fatalf("recent keyword ranks should be newest first: %+v", recent)
	}
	if recent.Items[0].Keyword != "notes" || recent.Items[0].Rank == nil || *recent.Items[0].Rank != 2 {
		t.Fatalf("recent keyword rank payload not preserved: %+v", recent.Items[0])
	}
}

func TestFetchChartNormalizesAndSaveSnapshot(t *testing.T) {
	now := time.Date(2026, 6, 18, 9, 30, 0, 0, time.UTC)
	upstream := &fakeUpstream{charts: dto.FetchChartResponse{Items: []dto.ChartItem{
		{AppSummary: dto.AppSummary{AppID: "com.one"}, Rank: 1},
		{AppSummary: dto.AppSummary{AppID: "com.two"}, Rank: 2},
	}}}
	store := repo.NewMemoryRepo()
	svc := service.NewStoreIntelService(store, upstream, service.WithConfig(service.Config{
		Now: func() time.Time { return now },
	}))

	fetched, err := svc.FetchChart(context.Background(), dto.FetchChartRequest{
		ChartType: "top_paid",
		Category:  "GAME",
		Country:   "US",
		Lang:      "EN",
		Limit:     0,
	})
	if err != nil {
		t.Fatalf("FetchChart returned error: %v", err)
	}
	if fetched.Total != 2 || fetched.Items[0].ChartType != "top_paid" || fetched.Items[0].Country != "us" {
		t.Fatalf("chart items not normalized: %+v", fetched)
	}
	if len(upstream.chartReqs) != 1 || upstream.chartReqs[0].Limit != 100 || upstream.chartReqs[0].Category != "GAME" {
		t.Fatalf("chart request not normalized: %+v", upstream.chartReqs)
	}

	saved, err := svc.SaveChartSnapshot(context.Background(), dto.SaveChartSnapshotRequest{
		ChartType: "top_paid",
		Category:  "GAME",
		Country:   "us",
		Lang:      "en",
		Items:     fetched.Items,
	})
	if err != nil {
		t.Fatalf("SaveChartSnapshot returned error: %v", err)
	}
	if saved.Saved != 2 || saved.CapturedAt != "2026-06-18T09:30:00Z" {
		t.Fatalf("unexpected saved chart snapshot: %+v", saved)
	}
}

func TestRankChartPersistsOneRowPerDayAndHistory(t *testing.T) {
	now := time.Date(2026, 6, 18, 9, 30, 0, 0, time.UTC)
	upstream := &fakeUpstream{charts: dto.FetchChartResponse{Items: []dto.ChartItem{
		{AppSummary: dto.AppSummary{AppID: "com.first"}, Rank: 1},
		{AppSummary: dto.AppSummary{AppID: "com.Target"}, Rank: 2},
	}}}
	store := repo.NewMemoryRepo()
	svc := service.NewStoreIntelService(store, upstream, service.WithConfig(service.Config{
		Now: func() time.Time { return now },
	}))

	first, err := svc.RankChart(context.Background(), dto.ChartRankRequest{
		AppID:      "com.target",
		Collection: "top_grossing",
		Category:   "",
		Country:    "US",
		Lang:       "EN",
		Limit:      10,
	})
	if err != nil {
		t.Fatalf("first RankChart returned error: %v", err)
	}
	if !first.Found || first.Rank == nil || *first.Rank != 2 || first.Category != "APPLICATION" {
		t.Fatalf("unexpected first chart rank: %+v", first)
	}

	upstream.charts = dto.FetchChartResponse{Items: []dto.ChartItem{
		{AppSummary: dto.AppSummary{AppID: "com.target"}, Rank: 1},
	}}
	second, err := svc.RankChart(context.Background(), dto.ChartRankRequest{
		AppID:      "com.target",
		Collection: "top_grossing",
		Country:    "us",
		Lang:       "en",
		Limit:      10,
	})
	if err != nil {
		t.Fatalf("second RankChart returned error: %v", err)
	}
	if second.Rank == nil || *second.Rank != 1 {
		t.Fatalf("unexpected second chart rank: %+v", second)
	}

	history, err := svc.ListChartRankHistory(context.Background(), dto.ChartRankHistoryRequest{
		AppID:      "com.target",
		Collection: "top_grossing",
		Country:    "us",
		Lang:       "en",
	})
	if err != nil {
		t.Fatalf("ListChartRankHistory returned error: %v", err)
	}
	if history.Total != 1 || history.Items[0].Rank == nil || *history.Items[0].Rank != 1 {
		t.Fatalf("same-day chart upsert not reflected in history: %+v", history)
	}

	now = now.Add(24 * time.Hour)
	upstream.charts = dto.FetchChartResponse{Items: []dto.ChartItem{
		{AppSummary: dto.AppSummary{AppID: "com.other"}, Rank: 1},
		{AppSummary: dto.AppSummary{AppID: "com.target"}, Rank: 2},
	}}
	if _, err := svc.RankChart(context.Background(), dto.ChartRankRequest{
		AppID:      "com.target",
		Collection: "top_grossing",
		Country:    "us",
		Lang:       "en",
		Limit:      10,
	}); err != nil {
		t.Fatalf("third RankChart returned error: %v", err)
	}
	history, err = svc.ListChartRankHistory(context.Background(), dto.ChartRankHistoryRequest{
		AppID:      "com.target",
		Collection: "top_grossing",
		Country:    "us",
		Lang:       "en",
	})
	if err != nil {
		t.Fatalf("second ListChartRankHistory returned error: %v", err)
	}
	if history.Total != 2 || history.Items[0].CapturedAt >= history.Items[1].CapturedAt {
		t.Fatalf("history should contain two days in ascending order: %+v", history)
	}
}

func TestTrackedKeywordAndChartAppSyncAndSyncAll(t *testing.T) {
	now := time.Date(2026, 6, 18, 9, 30, 0, 0, time.UTC)
	upstream := &fakeUpstream{
		searchItems: []dto.AppSummary{
			{Platform: dto.PlatformGooglePlay, AppID: "com.other"},
			{Platform: dto.PlatformGooglePlay, AppID: "com.target"},
		},
		charts: dto.FetchChartResponse{Items: []dto.ChartItem{
			{AppSummary: dto.AppSummary{AppID: "com.target"}, Rank: 1},
		}},
	}
	store := repo.NewMemoryRepo()
	svc := service.NewStoreIntelService(store, upstream, service.WithConfig(service.Config{
		Now: func() time.Time { return now },
	}))
	ctx := context.Background()

	keyword, err := svc.AddTrackedKeyword(ctx, dto.AddTrackedKeywordRequest{
		Keyword: "notes",
		AppID:   "com.target",
		Country: "US",
		Lang:    "EN",
	})
	if err != nil {
		t.Fatalf("AddTrackedKeyword returned error: %v", err)
	}
	if keyword.Platform != dto.PlatformGooglePlay || keyword.Country != "us" || !keyword.Enabled {
		t.Fatalf("keyword monitor not normalized: %+v", keyword)
	}
	chart, err := svc.AddTrackedChartApp(ctx, dto.AddTrackedChartAppRequest{
		AppID:      "com.target",
		Collection: "top_paid",
		Country:    "US",
		Lang:       "EN",
	})
	if err != nil {
		t.Fatalf("AddTrackedChartApp returned error: %v", err)
	}
	if chart.Collection != "top_paid" || chart.Category != "APPLICATION" || !chart.Enabled {
		t.Fatalf("chart monitor not normalized: %+v", chart)
	}

	keywordSync, err := svc.SyncTrackedKeywordNow(ctx, dto.SyncTrackedKeywordRequest{
		Keyword: "notes",
		AppID:   "com.target",
		Country: "us",
		Lang:    "en",
		Limit:   10,
	})
	if err != nil {
		t.Fatalf("SyncTrackedKeywordNow returned error: %v", err)
	}
	if keywordSync.Rank.Rank == nil || *keywordSync.Rank.Rank != 2 {
		t.Fatalf("unexpected keyword sync rank: %+v", keywordSync)
	}
	chartSync, err := svc.SyncTrackedChartAppNow(ctx, dto.SyncTrackedChartAppRequest{
		AppID:      "com.target",
		Collection: "top_paid",
		Country:    "us",
		Lang:       "en",
		Limit:      10,
	})
	if err != nil {
		t.Fatalf("SyncTrackedChartAppNow returned error: %v", err)
	}
	if chartSync.Rank.Rank == nil || *chartSync.Rank.Rank != 1 {
		t.Fatalf("unexpected chart sync rank: %+v", chartSync)
	}

	keywords, err := svc.ListTrackedKeywords(ctx, dto.ListTrackedKeywordsRequest{})
	if err != nil {
		t.Fatalf("ListTrackedKeywords returned error: %v", err)
	}
	if keywords.Total != 1 || keywords.Items[0].LastSyncedAt == "" || keywords.Items[0].ConsecutiveFailures != 0 {
		t.Fatalf("keyword sync state not updated: %+v", keywords)
	}
	charts, err := svc.ListTrackedChartApps(ctx, dto.ListTrackedChartAppsRequest{})
	if err != nil {
		t.Fatalf("ListTrackedChartApps returned error: %v", err)
	}
	if charts.Total != 1 || charts.Items[0].LastSyncedAt == "" || charts.Items[0].ConsecutiveFailures != 0 {
		t.Fatalf("chart sync state not updated: %+v", charts)
	}

	result, err := svc.SyncAll(ctx, dto.SyncAllRequest{})
	if err != nil {
		t.Fatalf("SyncAll returned error: %v", err)
	}
	if result.KeywordsSynced != 1 || result.ChartsSynced != 1 || result.KeywordsFailed != 0 || result.ChartsFailed != 0 {
		t.Fatalf("sync all did not include keyword/chart monitors: %+v", result)
	}
}

func TestTrackedMonitorManagementMutations(t *testing.T) {
	now := time.Date(2026, 6, 18, 9, 30, 0, 0, time.UTC)
	store := repo.NewMemoryRepo()
	svc := service.NewStoreIntelService(store, &fakeUpstream{}, service.WithConfig(service.Config{
		Now: func() time.Time { return now },
	}))
	ctx := context.Background()

	if _, err := svc.AddTrackedApp(ctx, dto.AddTrackedAppRequest{
		AppID: "com.demo", Country: "US", Lang: "EN", Frequency: "daily", Tag: "core",
	}); err != nil {
		t.Fatalf("AddTrackedApp returned error: %v", err)
	}
	appEnabled, err := svc.SetTrackedAppEnabled(ctx, dto.SetTrackedAppEnabledRequest{
		AppID: "com.demo", Country: "us", Lang: "en", Enabled: false,
	})
	if err != nil {
		t.Fatalf("SetTrackedAppEnabled returned error: %v", err)
	}
	if appEnabled.Updated != 1 || appEnabled.Enabled == nil || *appEnabled.Enabled {
		t.Fatalf("unexpected app enabled mutation: %+v", appEnabled)
	}
	appFrequency, err := svc.SetTrackedAppFrequency(ctx, dto.SetTrackedAppFrequencyRequest{
		AppID: "com.demo", Country: "us", Lang: "en", Frequency: "manual",
	})
	if err != nil {
		t.Fatalf("SetTrackedAppFrequency returned error: %v", err)
	}
	if appFrequency.Updated != 1 || appFrequency.Frequency != "manual" {
		t.Fatalf("unexpected app frequency mutation: %+v", appFrequency)
	}
	appTag, err := svc.SetTrackedAppTag(ctx, dto.SetTrackedAppTagRequest{
		AppID: "com.demo", Country: "us", Lang: "en", Tag: "  retained  ",
	})
	if err != nil {
		t.Fatalf("SetTrackedAppTag returned error: %v", err)
	}
	if appTag.Updated != 1 || appTag.Tag != "retained" {
		t.Fatalf("unexpected app tag mutation: %+v", appTag)
	}
	missingApp, err := svc.SetTrackedAppEnabled(ctx, dto.SetTrackedAppEnabledRequest{
		AppID: "com.missing", Country: "us", Lang: "en", Enabled: true,
	})
	if err != nil {
		t.Fatalf("missing SetTrackedAppEnabled returned error: %v", err)
	}
	if missingApp.Updated != 0 || missingApp.Enabled == nil || !*missingApp.Enabled {
		t.Fatalf("missing app mutation should mirror requested value without creating: %+v", missingApp)
	}
	apps, err := svc.ListTrackedApps(ctx, dto.ListTrackedAppsRequest{})
	if err != nil {
		t.Fatalf("ListTrackedApps returned error: %v", err)
	}
	if apps.Total != 1 || apps.Items[0].Enabled || apps.Items[0].Frequency != "manual" || apps.Items[0].Tag != "retained" {
		t.Fatalf("app mutations not reflected in list: %+v", apps)
	}
	removedApp, err := svc.RemoveTrackedApp(ctx, dto.RemoveTrackedAppRequest{AppID: "com.demo", Country: "us", Lang: "en"})
	if err != nil {
		t.Fatalf("RemoveTrackedApp returned error: %v", err)
	}
	removedAppAgain, err := svc.RemoveTrackedApp(ctx, dto.RemoveTrackedAppRequest{AppID: "com.demo", Country: "us", Lang: "en"})
	if err != nil {
		t.Fatalf("second RemoveTrackedApp returned error: %v", err)
	}
	if removedApp.Updated != 1 || removedAppAgain.Updated != 0 {
		t.Fatalf("unexpected app remove counts: first=%+v second=%+v", removedApp, removedAppAgain)
	}

	if _, err := svc.AddTrackedKeyword(ctx, dto.AddTrackedKeywordRequest{
		Keyword: "notes", AppID: "com.target", Country: "us", Lang: "en", Platform: dto.PlatformGooglePlay,
	}); err != nil {
		t.Fatalf("AddTrackedKeyword google_play returned error: %v", err)
	}
	if _, err := svc.AddTrackedKeyword(ctx, dto.AddTrackedKeywordRequest{
		Keyword: "notes", AppID: "com.target", Country: "us", Lang: "en", Platform: "app_store",
	}); err != nil {
		t.Fatalf("AddTrackedKeyword app_store returned error: %v", err)
	}
	keywordEnabled, err := svc.SetTrackedKeywordEnabled(ctx, dto.SetTrackedKeywordEnabledRequest{
		Keyword: "notes", AppID: "com.target", Country: "us", Lang: "en", Platform: "app_store", Enabled: false,
	})
	if err != nil {
		t.Fatalf("SetTrackedKeywordEnabled returned error: %v", err)
	}
	if keywordEnabled.Updated != 1 || keywordEnabled.Enabled == nil || *keywordEnabled.Enabled {
		t.Fatalf("unexpected keyword enabled mutation: %+v", keywordEnabled)
	}
	keywordFrequency, err := svc.SetTrackedKeywordFrequency(ctx, dto.SetTrackedKeywordFrequencyRequest{
		Keyword: "notes", AppID: "com.target", Country: "us", Lang: "en", Platform: "app_store", Frequency: "weekly",
	})
	if err != nil {
		t.Fatalf("SetTrackedKeywordFrequency returned error: %v", err)
	}
	if keywordFrequency.Updated != 1 || keywordFrequency.Frequency != "weekly" {
		t.Fatalf("unexpected keyword frequency mutation: %+v", keywordFrequency)
	}
	removedKeyword, err := svc.RemoveTrackedKeyword(ctx, dto.RemoveTrackedKeywordRequest{
		Keyword: "notes", AppID: "com.target", Country: "us", Lang: "en", Platform: dto.PlatformGooglePlay,
	})
	if err != nil {
		t.Fatalf("RemoveTrackedKeyword returned error: %v", err)
	}
	keywords, err := svc.ListTrackedKeywords(ctx, dto.ListTrackedKeywordsRequest{})
	if err != nil {
		t.Fatalf("ListTrackedKeywords returned error: %v", err)
	}
	if removedKeyword.Updated != 1 || keywords.Total != 1 || keywords.Items[0].Platform != "app_store" ||
		keywords.Items[0].Enabled || keywords.Items[0].Frequency != "weekly" {
		t.Fatalf("keyword platform-scoped mutations not reflected: removed=%+v list=%+v", removedKeyword, keywords)
	}

	if _, err := svc.AddTrackedChartApp(ctx, dto.AddTrackedChartAppRequest{
		AppID: "com.target", Collection: "top_free", Category: "GAME", Country: "us", Lang: "en",
	}); err != nil {
		t.Fatalf("AddTrackedChartApp returned error: %v", err)
	}
	chartEnabled, err := svc.SetTrackedChartAppEnabled(ctx, dto.SetTrackedChartAppEnabledRequest{
		AppID: "com.target", Collection: "top_free", Category: "GAME", Country: "us", Lang: "en", Enabled: false,
	})
	if err != nil {
		t.Fatalf("SetTrackedChartAppEnabled returned error: %v", err)
	}
	if chartEnabled.Updated != 1 || chartEnabled.Enabled == nil || *chartEnabled.Enabled {
		t.Fatalf("unexpected chart enabled mutation: %+v", chartEnabled)
	}
	removedChart, err := svc.RemoveTrackedChartApp(ctx, dto.RemoveTrackedChartAppRequest{
		AppID: "com.target", Collection: "top_free", Category: "GAME", Country: "us", Lang: "en",
	})
	if err != nil {
		t.Fatalf("RemoveTrackedChartApp returned error: %v", err)
	}
	removedChartAgain, err := svc.RemoveTrackedChartApp(ctx, dto.RemoveTrackedChartAppRequest{
		AppID: "com.target", Collection: "top_free", Category: "GAME", Country: "us", Lang: "en",
	})
	if err != nil {
		t.Fatalf("second RemoveTrackedChartApp returned error: %v", err)
	}
	charts, err := svc.ListTrackedChartApps(ctx, dto.ListTrackedChartAppsRequest{})
	if err != nil {
		t.Fatalf("ListTrackedChartApps returned error: %v", err)
	}
	if removedChart.Updated != 1 || removedChartAgain.Updated != 0 || charts.Total != 0 {
		t.Fatalf("unexpected chart remove result: first=%+v second=%+v list=%+v", removedChart, removedChartAgain, charts)
	}
}

func TestTrackedKeywordAndChartFailuresIncrementCounters(t *testing.T) {
	now := time.Date(2026, 6, 18, 9, 30, 0, 0, time.UTC)
	upstream := &fakeUpstream{
		searchErr: errors.New("search blocked"),
		chartErr:  errors.New("chart blocked"),
	}
	store := repo.NewMemoryRepo()
	svc := service.NewStoreIntelService(store, upstream, service.WithConfig(service.Config{
		Now: func() time.Time { return now },
	}))
	ctx := context.Background()
	if _, err := svc.AddTrackedKeyword(ctx, dto.AddTrackedKeywordRequest{Keyword: "notes", AppID: "com.target"}); err != nil {
		t.Fatalf("AddTrackedKeyword returned error: %v", err)
	}
	if _, err := svc.AddTrackedChartApp(ctx, dto.AddTrackedChartAppRequest{AppID: "com.target", Collection: "top_free"}); err != nil {
		t.Fatalf("AddTrackedChartApp returned error: %v", err)
	}

	if _, err := svc.SyncTrackedKeywordNow(ctx, dto.SyncTrackedKeywordRequest{Keyword: "notes", AppID: "com.target"}); err == nil {
		t.Fatal("SyncTrackedKeywordNow should return upstream error")
	}
	if _, err := svc.SyncTrackedChartAppNow(ctx, dto.SyncTrackedChartAppRequest{AppID: "com.target", Collection: "top_free"}); err == nil {
		t.Fatal("SyncTrackedChartAppNow should return upstream error")
	}

	keywords, err := svc.ListTrackedKeywords(ctx, dto.ListTrackedKeywordsRequest{})
	if err != nil {
		t.Fatalf("ListTrackedKeywords returned error: %v", err)
	}
	if keywords.Items[0].ConsecutiveFailures != 1 || keywords.Items[0].LastFailedAt == "" {
		t.Fatalf("keyword failure state not updated: %+v", keywords.Items[0])
	}
	charts, err := svc.ListTrackedChartApps(ctx, dto.ListTrackedChartAppsRequest{})
	if err != nil {
		t.Fatalf("ListTrackedChartApps returned error: %v", err)
	}
	if charts.Items[0].ConsecutiveFailures != 1 || charts.Items[0].LastFailedAt == "" {
		t.Fatalf("chart failure state not updated: %+v", charts.Items[0])
	}

	alerts, err := svc.ListAlerts(ctx, dto.ListAlertsRequest{Limit: 10})
	if err != nil {
		t.Fatalf("ListAlerts returned error: %v", err)
	}
	if alerts.Total != 2 {
		t.Fatalf("expected keyword and chart failure alerts, got %+v", alerts)
	}
	for _, alert := range alerts.Items {
		if alert.Type != "fetch_failed" || alert.Severity != "medium" {
			t.Fatalf("unexpected first failure alert: %+v", alert)
		}
		if alert.Payload["failure_count"] != 1 {
			t.Fatalf("failure_count payload not recorded: %+v", alert.Payload)
		}
	}
}

func TestSyncAppFailureEscalatesAndRecoveryAlerts(t *testing.T) {
	now := time.Date(2026, 6, 18, 9, 30, 0, 0, time.UTC)
	upstream := &fakeUpstream{detailErr: errors.New("store blocked")}
	store := repo.NewMemoryRepo()
	svc := service.NewStoreIntelService(store, upstream, service.WithConfig(service.Config{
		Now: func() time.Time { return now },
	}))
	ctx := context.Background()
	if _, err := svc.SetSettings(ctx, map[string]string{"alert_fetch_escalate_after": "2"}); err != nil {
		t.Fatalf("SetSettings returned error: %v", err)
	}
	if _, err := svc.AddTrackedApp(ctx, dto.AddTrackedAppRequest{AppID: "com.target"}); err != nil {
		t.Fatalf("AddTrackedApp returned error: %v", err)
	}

	first, err := svc.SyncAppNow(ctx, dto.SyncAppNowRequest{AppID: "com.target"})
	if err == nil {
		t.Fatal("first SyncAppNow should return upstream error")
	}
	if len(first.Alerts) != 1 || first.Alerts[0].Type != "fetch_failed" {
		t.Fatalf("first failure should create quiet alert: %+v", first.Alerts)
	}
	second, err := svc.SyncAppNow(ctx, dto.SyncAppNowRequest{AppID: "com.target"})
	if err == nil {
		t.Fatal("second SyncAppNow should return upstream error")
	}
	if len(second.Alerts) != 1 || second.Alerts[0].Type != "fetch_failed_persistent" || second.Alerts[0].Severity != "high" {
		t.Fatalf("second failure should escalate: %+v", second.Alerts)
	}

	upstream.detailErr = nil
	upstream.details = []dto.AppDetail{{
		AppSummary: dto.AppSummary{Platform: dto.PlatformGooglePlay, AppID: "com.target", Title: "Target"},
	}}
	now = now.Add(24 * time.Hour)
	recovered, err := svc.SyncAppNow(ctx, dto.SyncAppNowRequest{AppID: "com.target"})
	if err != nil {
		t.Fatalf("recovered SyncAppNow returned error: %v", err)
	}
	if len(recovered.Alerts) != 1 || recovered.Alerts[0].Type != "fetch_recovered" {
		t.Fatalf("recovery alert not returned: %+v", recovered.Alerts)
	}
	if recovered.Alerts[0].Payload["previous"] != 2 {
		t.Fatalf("recovery payload should include prior failures: %+v", recovered.Alerts[0].Payload)
	}
	tracked, err := svc.ListTrackedApps(ctx, dto.ListTrackedAppsRequest{})
	if err != nil {
		t.Fatalf("ListTrackedApps returned error: %v", err)
	}
	if tracked.Items[0].ConsecutiveFailures != 0 || tracked.Items[0].LastFailedAt != "" {
		t.Fatalf("tracked app should reset after recovery: %+v", tracked.Items[0])
	}

	alerts, err := svc.ListAlerts(ctx, dto.ListAlertsRequest{Limit: 10})
	if err != nil {
		t.Fatalf("ListAlerts returned error: %v", err)
	}
	types := map[string]int{}
	for _, alert := range alerts.Items {
		types[alert.Type]++
	}
	if types["fetch_failed"] != 1 || types["fetch_failed_persistent"] != 1 || types["fetch_recovered"] != 1 {
		t.Fatalf("unexpected persisted alert types: %+v", alerts.Items)
	}
}

func TestSyncAllCountsFailureAndRecoveryAlerts(t *testing.T) {
	now := time.Date(2026, 6, 18, 9, 30, 0, 0, time.UTC)
	upstream := &fakeUpstream{
		searchErr: errors.New("search blocked"),
		chartErr:  errors.New("chart blocked"),
	}
	store := repo.NewMemoryRepo()
	svc := service.NewStoreIntelService(store, upstream, service.WithConfig(service.Config{
		Now: func() time.Time { return now },
	}))
	ctx := context.Background()
	if _, err := svc.SetSettings(ctx, map[string]string{"alert_fetch_escalate_after": "1"}); err != nil {
		t.Fatalf("SetSettings returned error: %v", err)
	}
	if _, err := svc.AddTrackedKeyword(ctx, dto.AddTrackedKeywordRequest{Keyword: "notes", AppID: "com.target"}); err != nil {
		t.Fatalf("AddTrackedKeyword returned error: %v", err)
	}
	if _, err := svc.AddTrackedChartApp(ctx, dto.AddTrackedChartAppRequest{AppID: "com.target", Collection: "top_free"}); err != nil {
		t.Fatalf("AddTrackedChartApp returned error: %v", err)
	}

	failed, err := svc.SyncAll(ctx, dto.SyncAllRequest{})
	if err != nil {
		t.Fatalf("failing SyncAll returned service error: %v", err)
	}
	if failed.KeywordsFailed != 1 || failed.ChartsFailed != 1 || failed.Alerts != 2 {
		t.Fatalf("SyncAll should count failure alerts: %+v", failed)
	}

	upstream.searchErr = nil
	upstream.chartErr = nil
	upstream.searchItems = []dto.AppSummary{{Platform: dto.PlatformGooglePlay, AppID: "com.target"}}
	upstream.charts = dto.FetchChartResponse{Items: []dto.ChartItem{{AppSummary: dto.AppSummary{AppID: "com.target"}, Rank: 1}}}
	now = now.Add(24 * time.Hour)
	recovered, err := svc.SyncAll(ctx, dto.SyncAllRequest{})
	if err != nil {
		t.Fatalf("recovered SyncAll returned error: %v", err)
	}
	if recovered.KeywordsSynced != 1 || recovered.ChartsSynced != 1 || recovered.Alerts != 2 {
		t.Fatalf("SyncAll should count recovery alerts: %+v", recovered)
	}

	alerts, err := svc.ListAlerts(ctx, dto.ListAlertsRequest{Limit: 10})
	if err != nil {
		t.Fatalf("ListAlerts returned error: %v", err)
	}
	types := map[string]int{}
	for _, alert := range alerts.Items {
		types[alert.Type]++
	}
	if types["fetch_failed_persistent"] != 2 || types["fetch_recovered"] != 2 {
		t.Fatalf("unexpected alert mix after failure and recovery: %+v", alerts.Items)
	}
}

func TestCleanupHistoryUsesRetentionSettingsAndKeepsNewestPerObject(t *testing.T) {
	now := time.Date(2026, 6, 18, 9, 30, 0, 0, time.UTC)
	store := repo.NewMemoryRepo()
	svc := service.NewStoreIntelService(store, &fakeUpstream{}, service.WithConfig(service.Config{
		Now: func() time.Time { return now },
	}))
	ctx := context.Background()
	if _, err := svc.SetSettings(ctx, map[string]string{
		"retention_enabled":          "true",
		"snapshot_retention_days":    "180",
		"keyword_retention_days":     "180",
		"alert_retention_days":       "365",
		"review_retention_days":      "180",
		"retention_min_keep":         "1",
		"review_monitor_enabled":     "true",
		"review_alert_min_count":     "3",
		"review_alert_max_rating":    "2",
		"alert_fetch_escalate_after": "3",
	}); err != nil {
		t.Fatalf("SetSettings returned error: %v", err)
	}

	for _, capturedAt := range []string{"2020-01-01T00:00:00Z", "2020-02-01T00:00:00Z", "2026-01-01T00:00:00Z"} {
		if _, err := store.UpsertAppSnapshot(ctx, repo.SnapshotUpsertInput{
			Detail:  dto.AppDetail{AppSummary: dto.AppSummary{Platform: dto.PlatformGooglePlay, AppID: "com.retained"}},
			Country: "us", Lang: "en", CapturedAt: capturedAt,
		}); err != nil {
			t.Fatalf("UpsertAppSnapshot %s returned error: %v", capturedAt, err)
		}
		rank := 1
		if _, err := store.UpsertKeywordRank(ctx, repo.KeywordRankUpsertInput{
			Result: dto.KeywordRankResponse{
				Platform: dto.PlatformGooglePlay, Keyword: "notes", AppID: "com.retained",
				Country: "us", Lang: "en", Found: true, Rank: &rank, CheckedLimit: 10, CapturedAt: capturedAt,
			},
			CapturedAt: capturedAt, CapturedDay: capturedAt[:10],
		}); err != nil {
			t.Fatalf("UpsertKeywordRank %s returned error: %v", capturedAt, err)
		}
		if _, _, err := store.UpsertChartRank(ctx, repo.ChartRankUpsertInput{
			Result: dto.ChartRankResponse{
				Platform: dto.PlatformGooglePlay, AppID: "com.retained", Collection: "top_free",
				Category: "APPLICATION", Country: "us", Lang: "en", Found: true, Rank: &rank,
				CheckedLimit: 10, CapturedAt: capturedAt,
			},
			CapturedAt: capturedAt, CapturedDay: capturedAt[:10],
		}); err != nil {
			t.Fatalf("UpsertChartRank %s returned error: %v", capturedAt, err)
		}
		if _, err := store.SaveReviews(ctx, repo.SaveReviewsInput{
			Identity:   dto.AppIdentity{Platform: dto.PlatformGooglePlay, AppID: "com.retained", Country: "us", Lang: "en"},
			CapturedAt: capturedAt,
			Items:      []dto.ReviewItem{{ReviewID: "review-" + capturedAt[:10]}},
		}); err != nil {
			t.Fatalf("SaveReviews %s returned error: %v", capturedAt, err)
		}
	}
	if _, err := store.CreateAlerts(ctx, []dto.Alert{
		{AppID: "com.retained", Type: "old_unread", Severity: "low", Message: "keep", IsRead: false, CreatedAt: "2020-01-01T00:00:00Z"},
		{AppID: "com.retained", Type: "old_read", Severity: "low", Message: "drop", IsRead: true, CreatedAt: "2020-02-01T00:00:00Z"},
		{AppID: "com.retained", Type: "older_read", Severity: "low", Message: "drop", IsRead: true, CreatedAt: "2020-03-01T00:00:00Z"},
		{AppID: "com.retained", Type: "recent_read", Severity: "low", Message: "keep", IsRead: true, CreatedAt: "2026-01-01T00:00:00Z"},
	}); err != nil {
		t.Fatalf("CreateAlerts returned error: %v", err)
	}

	cleaned, err := svc.CleanupHistory(ctx)
	if err != nil {
		t.Fatalf("CleanupHistory returned error: %v", err)
	}
	if cleaned.Snapshots != 2 || cleaned.Keywords != 2 || cleaned.Charts != 2 || cleaned.Alerts != 2 || cleaned.Reviews != 2 {
		t.Fatalf("unexpected cleanup result: %+v", cleaned)
	}
	keywords, err := svc.ListKeywordRankHistory(ctx, dto.KeywordRankHistoryRequest{Keyword: "notes", AppID: "com.retained", Country: "us", Lang: "en"})
	if err != nil {
		t.Fatalf("ListKeywordRankHistory returned error: %v", err)
	}
	if keywords.Total != 1 || keywords.Items[0].CapturedAt != "2026-01-01T00:00:00Z" {
		t.Fatalf("keyword retention did not keep newest only: %+v", keywords)
	}
	charts, err := svc.ListChartRankHistory(ctx, dto.ChartRankHistoryRequest{AppID: "com.retained", Collection: "top_free", Category: "APPLICATION", Country: "us", Lang: "en"})
	if err != nil {
		t.Fatalf("ListChartRankHistory returned error: %v", err)
	}
	if charts.Total != 1 || charts.Items[0].CapturedAt != "2026-01-01T00:00:00Z" {
		t.Fatalf("chart retention did not keep newest only: %+v", charts)
	}
	reviews, err := svc.ListCachedReviews(ctx, dto.ListCachedReviewsRequest{AppID: "com.retained", Limit: 10})
	if err != nil {
		t.Fatalf("ListCachedReviews returned error: %v", err)
	}
	if reviews.Total != 1 || reviews.Items[0].CapturedAt != "2026-01-01T00:00:00Z" {
		t.Fatalf("review retention did not keep newest only: %+v", reviews)
	}
	alerts, err := svc.ListAlerts(ctx, dto.ListAlertsRequest{Limit: 10})
	if err != nil {
		t.Fatalf("ListAlerts returned error: %v", err)
	}
	unread := 0
	for _, alert := range alerts.Items {
		if !alert.IsRead {
			unread++
		}
	}
	if alerts.Total != 2 || unread != 1 {
		t.Fatalf("alert retention should keep unread old plus newest read: %+v", alerts)
	}
}

func TestCleanupHistoryDisabledIsNoop(t *testing.T) {
	store := repo.NewMemoryRepo()
	svc := service.NewStoreIntelService(store, &fakeUpstream{})
	ctx := context.Background()
	if _, err := svc.SetSettings(ctx, map[string]string{"retention_enabled": "false"}); err != nil {
		t.Fatalf("SetSettings returned error: %v", err)
	}
	if _, err := store.UpsertKeywordRank(ctx, repo.KeywordRankUpsertInput{
		Result: dto.KeywordRankResponse{
			Platform: dto.PlatformGooglePlay, Keyword: "notes", AppID: "com.retained",
			Country: "us", Lang: "en", Found: false, CapturedAt: "2020-01-01T00:00:00Z",
		},
		CapturedAt: "2020-01-01T00:00:00Z", CapturedDay: "2020-01-01",
	}); err != nil {
		t.Fatalf("UpsertKeywordRank returned error: %v", err)
	}
	cleaned, err := svc.CleanupHistory(ctx)
	if err != nil {
		t.Fatalf("CleanupHistory returned error: %v", err)
	}
	if cleaned != (dto.HistoryRetentionCleanupResponse{}) {
		t.Fatalf("disabled cleanup should be zero, got %+v", cleaned)
	}
}

func TestSettingsDefaultsAndOverrides(t *testing.T) {
	store := repo.NewMemoryRepo()
	now := time.Date(2026, 6, 18, 9, 30, 0, 0, time.UTC)
	svc := service.NewStoreIntelService(store, &fakeUpstream{}, service.WithConfig(service.Config{
		Now: func() time.Time { return now },
	}))

	if err := svc.EnsureSettingsDefaults(context.Background()); err != nil {
		t.Fatalf("EnsureSettingsDefaults returned error: %v", err)
	}
	settings, err := svc.GetSettings(context.Background())
	if err != nil {
		t.Fatalf("GetSettings returned error: %v", err)
	}
	if settings["default_country"] != "us" || settings["daily_sync_time"] != "09:00" {
		t.Fatalf("defaults not merged: %+v", settings)
	}

	settings, err = svc.SetSettings(context.Background(), map[string]string{
		"default_country": "jp",
		"theme":           "teal",
		"input_history":   `{"app_id":["com.demo"]}`,
	})
	if err != nil {
		t.Fatalf("SetSettings returned error: %v", err)
	}
	if settings["default_country"] != "jp" || settings["theme"] != "teal" {
		t.Fatalf("overrides not applied: %+v", settings)
	}
	if settings["default_lang"] != "en" || settings["input_history"] == "" {
		t.Fatalf("custom setting or defaults lost: %+v", settings)
	}
}

func TestAcquireSettingValueOnlySucceedsWhenValueChanges(t *testing.T) {
	store := repo.NewMemoryRepo()
	svc := service.NewStoreIntelService(store, &fakeUpstream{})
	ctx := context.Background()

	acquired, err := svc.AcquireSettingValue(ctx, "scheduler_last_run_day", "2026-06-18")
	if err != nil || !acquired {
		t.Fatalf("first acquire acquired=%v err=%v", acquired, err)
	}
	acquired, err = svc.AcquireSettingValue(ctx, "scheduler_last_run_day", "2026-06-18")
	if err != nil || acquired {
		t.Fatalf("same-value acquire acquired=%v err=%v", acquired, err)
	}
	acquired, err = svc.AcquireSettingValue(ctx, "scheduler_last_run_day", "2026-06-19")
	if err != nil || !acquired {
		t.Fatalf("changed-value acquire acquired=%v err=%v", acquired, err)
	}
	if _, err = svc.AcquireSettingValue(ctx, " ", "2026-06-20"); !errors.Is(err, service.ErrInvalidRequest) {
		t.Fatalf("blank key error = %v, want ErrInvalidRequest", err)
	}
}

func TestReviewsFetchSaveAndListCached(t *testing.T) {
	ratingOne := 1
	ratingFive := 5
	helpful := int64(7)
	now := time.Date(2026, 6, 18, 9, 30, 0, 0, time.UTC)
	upstream := &fakeUpstream{reviews: dto.FetchReviewsResponse{
		Items: []dto.ReviewItem{
			{ReviewID: "r1", UserName: "Ann", Rating: &ratingOne, Content: "bad", HelpfulCount: &helpful, ReviewCreatedAt: "2026-06-18T01:00:00Z"},
			{ReviewID: "r2", UserName: "Ben", Rating: &ratingFive, Content: "great", ReviewCreatedAt: "2026-06-17T01:00:00Z"},
		},
		NextToken: "next-page",
	}}
	store := repo.NewMemoryRepo()
	svc := service.NewStoreIntelService(store, upstream, service.WithConfig(service.Config{
		Now: func() time.Time { return now },
	}))

	fetched, err := svc.FetchReviews(context.Background(), dto.FetchReviewsRequest{
		AppID:   "com.demo",
		Country: "US",
		Lang:    "EN",
		Sort:    "rating",
	})
	if err != nil {
		t.Fatalf("FetchReviews returned error: %v", err)
	}
	if fetched.Total != 2 || fetched.NextToken != "next-page" {
		t.Fatalf("unexpected fetched reviews: %+v", fetched)
	}
	if len(upstream.reviewReqs) != 1 || upstream.reviewReqs[0].Country != "us" || upstream.reviewReqs[0].Limit != 20 {
		t.Fatalf("reviews request not normalized: %+v", upstream.reviewReqs)
	}

	saved, err := svc.SaveReviews(context.Background(), dto.SaveReviewsRequest{
		AppID:   "com.demo",
		Country: "us",
		Lang:    "en",
		Items:   fetched.Items,
	})
	if err != nil {
		t.Fatalf("SaveReviews returned error: %v", err)
	}
	if saved.Saved != 2 {
		t.Fatalf("saved = %d, want 2", saved.Saved)
	}
	savedAgain, err := svc.SaveReviews(context.Background(), dto.SaveReviewsRequest{
		AppID:   "com.demo",
		Country: "us",
		Lang:    "en",
		Items:   fetched.Items,
	})
	if err != nil {
		t.Fatalf("second SaveReviews returned error: %v", err)
	}
	if savedAgain.Saved != 0 {
		t.Fatalf("duplicate save inserted %d rows", savedAgain.Saved)
	}

	cached, err := svc.ListCachedReviews(context.Background(), dto.ListCachedReviewsRequest{AppID: "com.demo", Limit: 10})
	if err != nil {
		t.Fatalf("ListCachedReviews returned error: %v", err)
	}
	if cached.Total != 2 || cached.Items[0].ReviewID != "r1" || cached.Items[0].CapturedAt == "" {
		t.Fatalf("unexpected cached reviews: %+v", cached)
	}
}

func TestSyncAppNowMonitorsReviewsAndCreatesNegativeSpikeAlert(t *testing.T) {
	ratingOne := 1
	ratingTwo := 2
	now := time.Date(2026, 6, 1, 9, 0, 0, 0, time.UTC)
	upstream := &fakeUpstream{
		details: []dto.AppDetail{{
			AppSummary: dto.AppSummary{Platform: dto.PlatformGooglePlay, AppID: "com.target", Title: "Target"},
		}},
		reviews: dto.FetchReviewsResponse{Items: []dto.ReviewItem{
			{ReviewID: "r1", Rating: &ratingOne, Content: "bad one", ReviewCreatedAt: "2026-06-01T08:00:00Z"},
			{ReviewID: "r2", Rating: &ratingTwo, Content: "bad two", ReviewCreatedAt: "2026-06-01T07:00:00Z"},
			{ReviewID: "r3", Rating: &ratingOne, Content: "bad three", ReviewCreatedAt: "2026-06-01T06:00:00Z"},
		}},
	}
	store := repo.NewMemoryRepo()
	svc := service.NewStoreIntelService(store, upstream, service.WithConfig(service.Config{
		Now: func() time.Time { return now },
	}))
	ctx := context.Background()
	if _, err := svc.AddTrackedApp(ctx, dto.AddTrackedAppRequest{AppID: "com.target"}); err != nil {
		t.Fatalf("AddTrackedApp returned error: %v", err)
	}

	first, err := svc.SyncAppNow(ctx, dto.SyncAppNowRequest{AppID: "com.target"})
	if err != nil {
		t.Fatalf("first SyncAppNow returned error: %v", err)
	}
	if len(first.Alerts) != 1 || first.Alerts[0].Type != "review_negative_spike" || first.Alerts[0].Severity != "high" {
		t.Fatalf("first sync should create review spike alert: %+v", first.Alerts)
	}
	if first.Alerts[0].Payload["current"] != 3 || !strings.Contains(first.Alerts[0].Message, "bad one") {
		t.Fatalf("review spike alert should include count and sample: %+v", first.Alerts[0])
	}
	if len(upstream.reviewReqs) != 1 || upstream.reviewReqs[0].Sort != "newest" || upstream.reviewReqs[0].Limit != 50 {
		t.Fatalf("review monitor request not normalized: %+v", upstream.reviewReqs)
	}
	cached, err := svc.ListCachedReviews(ctx, dto.ListCachedReviewsRequest{AppID: "com.target", Limit: 10})
	if err != nil {
		t.Fatalf("ListCachedReviews returned error: %v", err)
	}
	if cached.Total != 3 {
		t.Fatalf("review monitor should persist fetched reviews: %+v", cached)
	}

	sameDay, err := svc.SyncAppNow(ctx, dto.SyncAppNowRequest{AppID: "com.target"})
	if err != nil {
		t.Fatalf("same-day SyncAppNow returned error: %v", err)
	}
	if len(sameDay.Alerts) != 0 || len(upstream.reviewReqs) != 1 {
		t.Fatalf("same-day sync should not re-monitor reviews: alerts=%+v reqs=%+v", sameDay.Alerts, upstream.reviewReqs)
	}

	now = now.Add(24 * time.Hour)
	nextDay, err := svc.SyncAppNow(ctx, dto.SyncAppNowRequest{AppID: "com.target"})
	if err != nil {
		t.Fatalf("next-day SyncAppNow returned error: %v", err)
	}
	if len(nextDay.Alerts) != 0 || len(upstream.reviewReqs) != 2 {
		t.Fatalf("existing reviews should not alert again: alerts=%+v reqs=%+v", nextDay.Alerts, upstream.reviewReqs)
	}
}

func TestSyncAppNowReviewMonitorFailureIsNonFatal(t *testing.T) {
	now := time.Date(2026, 6, 1, 9, 0, 0, 0, time.UTC)
	upstream := &fakeUpstream{
		details: []dto.AppDetail{{
			AppSummary: dto.AppSummary{Platform: dto.PlatformGooglePlay, AppID: "com.target", Title: "Target"},
		}},
		reviewErr: errors.New("reviews down"),
	}
	store := repo.NewMemoryRepo()
	svc := service.NewStoreIntelService(store, upstream, service.WithConfig(service.Config{
		Now: func() time.Time { return now },
	}))
	ctx := context.Background()
	if _, err := svc.AddTrackedApp(ctx, dto.AddTrackedAppRequest{AppID: "com.target"}); err != nil {
		t.Fatalf("AddTrackedApp returned error: %v", err)
	}

	resp, err := svc.SyncAppNow(ctx, dto.SyncAppNowRequest{AppID: "com.target"})
	if err != nil {
		t.Fatalf("SyncAppNow should ignore review monitor errors: %v", err)
	}
	if len(resp.Alerts) != 0 || len(upstream.reviewReqs) != 1 {
		t.Fatalf("review failure should not create alerts but should be attempted: alerts=%+v reqs=%+v", resp.Alerts, upstream.reviewReqs)
	}
	tracked, err := svc.ListTrackedApps(ctx, dto.ListTrackedAppsRequest{})
	if err != nil {
		t.Fatalf("ListTrackedApps returned error: %v", err)
	}
	if tracked.Items[0].LastSyncedAt == "" || tracked.Items[0].ConsecutiveFailures != 0 {
		t.Fatalf("review failure should not mark app sync failed: %+v", tracked.Items[0])
	}
}

func TestSyncAppNowPersistsTrackingAndCreatesDiffAlerts(t *testing.T) {
	ratingHigh := 4.8
	ratingLow := 4.2
	installsOld := int64(100)
	installsNew := int64(150)
	now := time.Date(2026, 6, 1, 9, 0, 0, 0, time.UTC)
	upstream := &fakeUpstream{details: []dto.AppDetail{
		{
			AppSummary: dto.AppSummary{
				Platform:    dto.PlatformGooglePlay,
				AppID:       "com.target",
				Title:       "Target",
				Rating:      &ratingHigh,
				MinInstalls: &installsOld,
			},
		},
		{
			AppSummary: dto.AppSummary{
				Platform:    dto.PlatformGooglePlay,
				AppID:       "com.target",
				Title:       "Target",
				Rating:      &ratingLow,
				MinInstalls: &installsNew,
			},
		},
	}}
	store := repo.NewMemoryRepo()
	svc := service.NewStoreIntelService(store, upstream, service.WithConfig(service.Config{
		Now: func() time.Time { return now },
	}))

	if _, err := svc.AddTrackedApp(context.Background(), dto.AddTrackedAppRequest{AppID: "com.target"}); err != nil {
		t.Fatalf("AddTrackedApp returned error: %v", err)
	}
	first, err := svc.SyncAppNow(context.Background(), dto.SyncAppNowRequest{AppID: "com.target"})
	if err != nil {
		t.Fatalf("first SyncAppNow returned error: %v", err)
	}
	if !first.FirstSync || len(first.Alerts) != 0 {
		t.Fatalf("first sync should not alert: %+v", first)
	}

	now = now.Add(24 * time.Hour)
	second, err := svc.SyncAppNow(context.Background(), dto.SyncAppNowRequest{AppID: "com.target"})
	if err != nil {
		t.Fatalf("second SyncAppNow returned error: %v", err)
	}
	if !second.FirstSync {
		t.Fatalf("second day should be first sync of that day: %+v", second)
	}
	if len(second.Alerts) != 2 {
		t.Fatalf("expected rating and installs alerts, got %+v", second.Alerts)
	}

	alerts, err := svc.ListAlerts(context.Background(), dto.ListAlertsRequest{Limit: 10})
	if err != nil {
		t.Fatalf("ListAlerts returned error: %v", err)
	}
	if alerts.Total != 2 {
		t.Fatalf("unexpected alert list: %+v", alerts)
	}

	tracked, err := svc.ListTrackedApps(context.Background(), dto.ListTrackedAppsRequest{})
	if err != nil {
		t.Fatalf("ListTrackedApps returned error: %v", err)
	}
	if tracked.Total != 1 || tracked.Items[0].Title != "Target" || tracked.Items[0].LastSyncedAt == "" {
		t.Fatalf("tracking record not refreshed: %+v", tracked)
	}
}

func TestAppSnapshotHistoryRecentAndCount(t *testing.T) {
	firstRating := 4.6
	secondRating := 4.9
	firstRatings := int64(120)
	secondRatings := int64(150)
	firstReviews := int64(40)
	secondReviews := int64(55)
	firstInstalls := int64(1000)
	secondInstalls := int64(1250)
	now := time.Date(2026, 6, 18, 9, 0, 0, 0, time.UTC)
	upstream := &fakeUpstream{details: []dto.AppDetail{
		{
			AppSummary: dto.AppSummary{
				Platform:     dto.PlatformGooglePlay,
				AppID:        "com.target",
				Title:        "Target",
				Rating:       &firstRating,
				RatingsCount: &firstRatings,
				ReviewsCount: &firstReviews,
				Installs:     "1,000+",
				MinInstalls:  &firstInstalls,
			},
			RealInstalls: &firstInstalls,
			Version:      "1.0.0",
		},
		{
			AppSummary: dto.AppSummary{
				Platform:     dto.PlatformGooglePlay,
				AppID:        "com.target",
				Title:        "Target",
				Rating:       &secondRating,
				RatingsCount: &secondRatings,
				ReviewsCount: &secondReviews,
				Installs:     "1,000+",
				MinInstalls:  &secondInstalls,
			},
			RealInstalls: &secondInstalls,
			Version:      "1.1.0",
		},
	}}
	store := repo.NewMemoryRepo()
	svc := service.NewStoreIntelService(store, upstream, service.WithConfig(service.Config{
		Now: func() time.Time { return now },
	}))
	ctx := context.Background()

	if _, err := svc.SyncAppNow(ctx, dto.SyncAppNowRequest{AppID: "com.target", Country: "US", Lang: "EN"}); err != nil {
		t.Fatalf("first SyncAppNow returned error: %v", err)
	}
	now = now.Add(24 * time.Hour)
	if _, err := svc.SyncAppNow(ctx, dto.SyncAppNowRequest{AppID: "com.target", Country: "us", Lang: "en"}); err != nil {
		t.Fatalf("second SyncAppNow returned error: %v", err)
	}

	count, err := svc.CountAppSnapshots(ctx)
	if err != nil {
		t.Fatalf("CountAppSnapshots returned error: %v", err)
	}
	if count.Total != 2 {
		t.Fatalf("unexpected snapshot count: %+v", count)
	}

	history, err := svc.ListAppSnapshotHistory(ctx, dto.ListAppSnapshotsRequest{
		AppID: "com.target", Country: "us", Lang: "en",
	})
	if err != nil {
		t.Fatalf("ListAppSnapshotHistory returned error: %v", err)
	}
	if history.Total != 2 || history.Items[0].CapturedAt >= history.Items[1].CapturedAt {
		t.Fatalf("history should return ascending snapshots: %+v", history)
	}
	if history.Items[1].Version != "1.1.0" || history.Items[1].RatingsCount == nil || *history.Items[1].RatingsCount != secondRatings ||
		history.Items[1].ReviewsCount == nil || *history.Items[1].ReviewsCount != secondReviews ||
		history.Items[1].RealInstalls == nil || *history.Items[1].RealInstalls != secondInstalls {
		t.Fatalf("latest snapshot fields not preserved: %+v", history.Items[1])
	}

	limited, err := svc.ListAppSnapshotHistory(ctx, dto.ListAppSnapshotsRequest{
		AppID: "com.target", Country: "us", Lang: "en", Limit: 1,
	})
	if err != nil {
		t.Fatalf("limited ListAppSnapshotHistory returned error: %v", err)
	}
	if limited.Total != 1 || limited.Items[0].Version != "1.1.0" {
		t.Fatalf("limited history should keep the latest snapshot: %+v", limited)
	}

	recent, err := svc.ListRecentAppSnapshots(ctx, dto.ListRecentAppSnapshotsRequest{Limit: 1})
	if err != nil {
		t.Fatalf("ListRecentAppSnapshots returned error: %v", err)
	}
	if recent.Total != 1 || recent.Items[0].CapturedAt != history.Items[1].CapturedAt {
		t.Fatalf("recent snapshots should return newest first: %+v", recent)
	}
}

func TestGetCachedAppDetailMissReturnsCacheMiss(t *testing.T) {
	svc := service.NewStoreIntelService(repo.NewMemoryRepo(), &fakeUpstream{})
	result, err := svc.GetCachedAppDetail(context.Background(), dto.GetAppDetailRequest{
		AppID: "com.missing", Country: "US", Lang: "EN",
	})
	if err != nil {
		t.Fatalf("GetCachedAppDetail miss returned error: %v", err)
	}
	if result.Cached {
		t.Fatalf("cache miss should return cached=false: %+v", result)
	}
	if result.Detail.Platform != dto.PlatformGooglePlay || result.Detail.AppID != "com.missing" {
		t.Fatalf("cache miss should keep normalized identity: %+v", result.Detail)
	}
	if result.Detail.StoreURL == "" {
		t.Fatalf("cache miss should include store url for refresh context: %+v", result.Detail)
	}
}
