package service

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/diandian-mini/storeintel/dto"
	"github.com/diandian-mini/storeintel/repo"
)

var (
	ErrInvalidRequest      = errors.New("invalid store intel request")
	ErrServiceUnavailable  = errors.New("store intel service unavailable")
	ErrUpstreamUnavailable = errors.New("store intel upstream unavailable")
)

type UpstreamClient interface {
	SearchApps(ctx context.Context, req dto.SearchAppsRequest) ([]dto.AppSummary, error)
	GetAppDetail(ctx context.Context, req dto.GetAppDetailRequest) (dto.AppDetail, error)
}

type AlertPublisher interface {
	PublishAlerts(ctx context.Context, alerts []dto.Alert) error
}

type StoreIntelService interface {
	SearchApps(ctx context.Context, req dto.SearchAppsRequest) (dto.SearchAppsResponse, error)
	GetAppDetail(ctx context.Context, req dto.GetAppDetailRequest) (dto.AppDetail, error)
	RankKeyword(ctx context.Context, req dto.KeywordRankRequest) (dto.KeywordRankResponse, error)
	AddTrackedApp(ctx context.Context, req dto.AddTrackedAppRequest) (dto.TrackedApp, error)
	ListTrackedApps(ctx context.Context, req dto.ListTrackedAppsRequest) (dto.ListTrackedAppsResponse, error)
	SyncAppNow(ctx context.Context, req dto.SyncAppNowRequest) (dto.SyncAppNowResponse, error)
	SyncAll(ctx context.Context, req dto.SyncAllRequest) (dto.SyncAllResponse, error)
	ListAlerts(ctx context.Context, req dto.ListAlertsRequest) (dto.ListAlertsResponse, error)
	MarkAlertsRead(ctx context.Context, req dto.MarkAlertsReadRequest) (dto.MarkAlertsReadResponse, error)
}

type Config struct {
	DefaultCountry   string
	DefaultLang      string
	DefaultFrequency string
	Now              func() time.Time
}

type storeIntelService struct {
	repo      repo.StoreIntelRepo
	upstream  UpstreamClient
	publisher AlertPublisher
	cfg       Config
}

func NewStoreIntelService(storeRepo repo.StoreIntelRepo, upstream UpstreamClient, opts ...Option) StoreIntelService {
	cfg := Config{DefaultCountry: "us", DefaultLang: "en", DefaultFrequency: "daily", Now: time.Now}
	s := &storeIntelService{repo: storeRepo, upstream: upstream, cfg: cfg}
	for _, opt := range opts {
		if opt != nil {
			opt(s)
		}
	}
	if s.cfg.DefaultCountry == "" {
		s.cfg.DefaultCountry = "us"
	}
	if s.cfg.DefaultLang == "" {
		s.cfg.DefaultLang = "en"
	}
	if s.cfg.DefaultFrequency == "" {
		s.cfg.DefaultFrequency = "daily"
	}
	if s.cfg.Now == nil {
		s.cfg.Now = time.Now
	}
	return s
}

type Option func(*storeIntelService)

func WithAlertPublisher(publisher AlertPublisher) Option {
	return func(s *storeIntelService) { s.publisher = publisher }
}

func WithConfig(cfg Config) Option {
	return func(s *storeIntelService) {
		if cfg.DefaultCountry != "" {
			s.cfg.DefaultCountry = cfg.DefaultCountry
		}
		if cfg.DefaultLang != "" {
			s.cfg.DefaultLang = cfg.DefaultLang
		}
		if cfg.DefaultFrequency != "" {
			s.cfg.DefaultFrequency = cfg.DefaultFrequency
		}
		if cfg.Now != nil {
			s.cfg.Now = cfg.Now
		}
	}
}

func (s *storeIntelService) SearchApps(ctx context.Context, req dto.SearchAppsRequest) (dto.SearchAppsResponse, error) {
	if s == nil || s.upstream == nil {
		return dto.SearchAppsResponse{}, ErrServiceUnavailable
	}
	req.Query = strings.TrimSpace(req.Query)
	if req.Query == "" {
		return dto.SearchAppsResponse{}, fmt.Errorf("%w: query is required", ErrInvalidRequest)
	}
	req.Country, req.Lang = s.locale(req.Country, req.Lang)
	req.Limit = clamp(req.Limit, 1, 100, 20)
	items, err := s.upstream.SearchApps(ctx, req)
	if err != nil {
		return dto.SearchAppsResponse{}, fmt.Errorf("%w: %v", ErrUpstreamUnavailable, err)
	}
	return dto.SearchAppsResponse{Items: items, Total: len(items)}, nil
}

func (s *storeIntelService) GetAppDetail(ctx context.Context, req dto.GetAppDetailRequest) (dto.AppDetail, error) {
	if s == nil || s.upstream == nil {
		return dto.AppDetail{}, ErrServiceUnavailable
	}
	req.AppID = strings.TrimSpace(req.AppID)
	if req.AppID == "" {
		return dto.AppDetail{}, fmt.Errorf("%w: app_id is required", ErrInvalidRequest)
	}
	req.Country, req.Lang = s.locale(req.Country, req.Lang)
	detail, err := s.upstream.GetAppDetail(ctx, req)
	if err != nil {
		return dto.AppDetail{}, fmt.Errorf("%w: %v", ErrUpstreamUnavailable, err)
	}
	if detail.Platform == "" {
		detail.Platform = dto.PlatformGooglePlay
	}
	if detail.AppID == "" {
		detail.AppID = req.AppID
	}
	return detail, nil
}

func (s *storeIntelService) RankKeyword(ctx context.Context, req dto.KeywordRankRequest) (dto.KeywordRankResponse, error) {
	req.Keyword = strings.TrimSpace(req.Keyword)
	req.AppID = strings.TrimSpace(req.AppID)
	if req.Keyword == "" || req.AppID == "" {
		return dto.KeywordRankResponse{}, fmt.Errorf("%w: keyword and app_id are required", ErrInvalidRequest)
	}
	country, lang := s.locale(req.Country, req.Lang)
	search, err := s.SearchApps(ctx, dto.SearchAppsRequest{
		Query:   req.Keyword,
		Country: country,
		Lang:    lang,
		Limit:   clamp(req.Limit, 1, 200, 100),
	})
	if err != nil {
		return dto.KeywordRankResponse{}, err
	}
	var rank *int
	for index, item := range search.Items {
		if item.AppID == req.AppID {
			value := index + 1
			rank = &value
			break
		}
	}
	return dto.KeywordRankResponse{
		Platform:     dto.PlatformGooglePlay,
		Keyword:      req.Keyword,
		AppID:        req.AppID,
		Country:      country,
		Lang:         lang,
		Found:        rank != nil,
		Rank:         rank,
		CheckedLimit: clamp(req.Limit, 1, 200, 100),
		CapturedAt:   nowISO(s.cfg.Now),
		Results:      search.Items,
	}, nil
}

func (s *storeIntelService) AddTrackedApp(ctx context.Context, req dto.AddTrackedAppRequest) (dto.TrackedApp, error) {
	if s == nil || s.repo == nil {
		return dto.TrackedApp{}, ErrServiceUnavailable
	}
	identity, err := s.identity(req.AppID, req.Country, req.Lang)
	if err != nil {
		return dto.TrackedApp{}, err
	}
	return s.repo.UpsertTrackedApp(ctx, repo.TrackedAppInput{
		Identity:  identity,
		Frequency: coalesce(req.Frequency, s.cfg.DefaultFrequency),
		Tag:       strings.TrimSpace(req.Tag),
		Enabled:   true,
		NowISO:    nowISO(s.cfg.Now),
	})
}

func (s *storeIntelService) ListTrackedApps(ctx context.Context, req dto.ListTrackedAppsRequest) (dto.ListTrackedAppsResponse, error) {
	if s == nil || s.repo == nil {
		return dto.ListTrackedAppsResponse{}, ErrServiceUnavailable
	}
	items, err := s.repo.ListTrackedApps(ctx, repo.TrackedAppFilter{Enabled: req.Enabled})
	if err != nil {
		return dto.ListTrackedAppsResponse{}, err
	}
	return dto.ListTrackedAppsResponse{Items: items, Total: len(items)}, nil
}

func (s *storeIntelService) SyncAppNow(ctx context.Context, req dto.SyncAppNowRequest) (dto.SyncAppNowResponse, error) {
	if s == nil || s.repo == nil || s.upstream == nil {
		return dto.SyncAppNowResponse{}, ErrServiceUnavailable
	}
	identity, err := s.identity(req.AppID, req.Country, req.Lang)
	if err != nil {
		return dto.SyncAppNowResponse{}, err
	}
	detail, err := s.GetAppDetail(ctx, dto.GetAppDetailRequest{
		AppID:   identity.AppID,
		Country: identity.Country,
		Lang:    identity.Lang,
	})
	now := nowISO(s.cfg.Now)
	if err != nil {
		_, _ = s.repo.RecordTrackedAppFailure(ctx, identity, now, err.Error())
		return dto.SyncAppNowResponse{}, err
	}
	_, _ = s.repo.UpsertTrackedApp(ctx, repo.TrackedAppInput{
		Identity:  identity,
		Title:     detail.Title,
		Frequency: s.cfg.DefaultFrequency,
		Enabled:   true,
		NowISO:    now,
	})
	upsert, err := s.repo.UpsertAppSnapshot(ctx, repo.SnapshotUpsertInput{
		Detail:     detail,
		Country:    identity.Country,
		Lang:       identity.Lang,
		CapturedAt: now,
	})
	if err != nil {
		return dto.SyncAppNowResponse{}, err
	}
	if err := s.repo.UpdateTrackedAppSyncSuccess(ctx, identity, now); err != nil && !errors.Is(err, repo.ErrNotFound) {
		return dto.SyncAppNowResponse{}, err
	}
	alerts := buildSnapshotAlerts(upsert.Previous, upsert.Current, upsert.FirstOfDay, now)
	if len(alerts) > 0 {
		alerts, err = s.repo.CreateAlerts(ctx, alerts)
		if err != nil {
			return dto.SyncAppNowResponse{}, err
		}
		if s.publisher != nil {
			_ = s.publisher.PublishAlerts(ctx, alerts)
		}
	}
	return dto.SyncAppNowResponse{Detail: detail, Alerts: alerts, FirstSync: upsert.FirstOfDay}, nil
}

func (s *storeIntelService) SyncAll(ctx context.Context, req dto.SyncAllRequest) (dto.SyncAllResponse, error) {
	if s == nil || s.repo == nil {
		return dto.SyncAllResponse{}, ErrServiceUnavailable
	}
	enabled := true
	tracked, err := s.repo.ListTrackedApps(ctx, repo.TrackedAppFilter{Enabled: &enabled})
	if err != nil {
		return dto.SyncAllResponse{}, err
	}
	var result dto.SyncAllResponse
	for _, item := range tracked {
		if req.DueOnly && !isDue(item, s.cfg.Now()) {
			continue
		}
		resp, err := s.SyncAppNow(ctx, dto.SyncAppNowRequest{
			AppID:   item.AppID,
			Country: item.Country,
			Lang:    item.Lang,
		})
		if err != nil {
			result.AppsFailed++
			continue
		}
		result.AppsSynced++
		result.Alerts += len(resp.Alerts)
	}
	return result, nil
}

func (s *storeIntelService) ListAlerts(ctx context.Context, req dto.ListAlertsRequest) (dto.ListAlertsResponse, error) {
	if s == nil || s.repo == nil {
		return dto.ListAlertsResponse{}, ErrServiceUnavailable
	}
	items, err := s.repo.ListAlerts(ctx, repo.AlertFilter{
		AppID:    strings.TrimSpace(req.AppID),
		Type:     strings.TrimSpace(req.Type),
		Severity: strings.TrimSpace(req.Severity),
		IsRead:   req.IsRead,
		Limit:    clamp(req.Limit, 1, 200, 200),
	})
	if err != nil {
		return dto.ListAlertsResponse{}, err
	}
	return dto.ListAlertsResponse{Items: items, Total: len(items)}, nil
}

func (s *storeIntelService) MarkAlertsRead(ctx context.Context, req dto.MarkAlertsReadRequest) (dto.MarkAlertsReadResponse, error) {
	if s == nil || s.repo == nil {
		return dto.MarkAlertsReadResponse{}, ErrServiceUnavailable
	}
	updated, err := s.repo.MarkAlertsRead(ctx, req.IDs)
	if err != nil {
		return dto.MarkAlertsReadResponse{}, err
	}
	return dto.MarkAlertsReadResponse{Updated: updated}, nil
}

func (s *storeIntelService) identity(appID, country, lang string) (dto.AppIdentity, error) {
	appID = strings.TrimSpace(appID)
	if appID == "" {
		return dto.AppIdentity{}, fmt.Errorf("%w: app_id is required", ErrInvalidRequest)
	}
	country, lang = s.locale(country, lang)
	return dto.AppIdentity{Platform: dto.PlatformGooglePlay, AppID: appID, Country: country, Lang: lang}, nil
}

func (s *storeIntelService) locale(country, lang string) (string, string) {
	country = strings.ToLower(strings.TrimSpace(country))
	lang = strings.ToLower(strings.TrimSpace(lang))
	if country == "" {
		country = s.cfg.DefaultCountry
	}
	if lang == "" {
		lang = s.cfg.DefaultLang
	}
	return country, lang
}

func buildSnapshotAlerts(previous *repo.SnapshotRecord, current repo.SnapshotRecord, firstOfDay bool, createdAt string) []dto.Alert {
	if previous == nil || !firstOfDay {
		return nil
	}
	title := coalesce(current.Title, current.Identity.AppID)
	alerts := []dto.Alert{}
	if previous.Rating != nil && current.Rating != nil {
		drop := *previous.Rating - *current.Rating
		if drop >= 0.3 {
			alerts = append(alerts, dto.Alert{
				Type:      "rating_drop",
				Severity:  "high",
				AppID:     current.Identity.AppID,
				Title:     title,
				Message:   fmt.Sprintf("%s rating dropped %.1f -> %.1f", title, *previous.Rating, *current.Rating),
				Payload:   map[string]any{"previous": *previous.Rating, "current": *current.Rating},
				CreatedAt: createdAt,
			})
		}
	}
	if previous.MinInstalls != nil && current.MinInstalls != nil && *previous.MinInstalls > 0 {
		growth := float64(*current.MinInstalls-*previous.MinInstalls) / float64(*previous.MinInstalls)
		if growth >= 0.2 {
			alerts = append(alerts, dto.Alert{
				Type:      "installs_growth",
				Severity:  "medium",
				AppID:     current.Identity.AppID,
				Title:     title,
				Message:   fmt.Sprintf("%s installs grew %.0f%%", title, growth*100),
				Payload:   map[string]any{"previous": *previous.MinInstalls, "current": *current.MinInstalls},
				CreatedAt: createdAt,
			})
		}
	}
	return alerts
}

func isDue(item dto.TrackedApp, now time.Time) bool {
	if strings.TrimSpace(item.LastSyncedAt) == "" {
		return true
	}
	last, err := time.Parse(time.RFC3339, item.LastSyncedAt)
	if err != nil {
		return true
	}
	switch strings.ToLower(strings.TrimSpace(item.Frequency)) {
	case "hourly":
		return now.Sub(last) >= time.Hour
	case "weekly":
		return now.Sub(last) >= 7*24*time.Hour
	default:
		return now.Sub(last) >= 24*time.Hour
	}
}

func nowISO(now func() time.Time) string {
	return now().UTC().Format(time.RFC3339)
}

func clamp(value, min, max, fallback int) int {
	if value <= 0 {
		value = fallback
	}
	if value < min {
		return min
	}
	if value > max {
		return max
	}
	return value
}

func coalesce(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return strings.TrimSpace(value)
		}
	}
	return ""
}
