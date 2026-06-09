package service_test

import (
	"context"
	"testing"
	"time"

	"github.com/diandian-mini/storeintel/dto"
	"github.com/diandian-mini/storeintel/repo"
	"github.com/diandian-mini/storeintel/service"
)

type fakeUpstream struct {
	searchItems []dto.AppSummary
	details     []dto.AppDetail
	detailIndex int
}

func (f *fakeUpstream) SearchApps(context.Context, dto.SearchAppsRequest) ([]dto.AppSummary, error) {
	return f.searchItems, nil
}

func (f *fakeUpstream) GetAppDetail(context.Context, dto.GetAppDetailRequest) (dto.AppDetail, error) {
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

func TestRankKeywordUsesSearchOrder(t *testing.T) {
	upstream := &fakeUpstream{searchItems: []dto.AppSummary{
		{Platform: dto.PlatformGooglePlay, AppID: "com.one"},
		{Platform: dto.PlatformGooglePlay, AppID: "com.target"},
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
