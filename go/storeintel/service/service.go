package service

import (
	"context"
	"errors"
	"fmt"
	"net/url"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/catch-radar/storeintel/dto"
	"github.com/catch-radar/storeintel/repo"
)

var (
	ErrInvalidRequest      = errors.New("invalid store intel request")
	ErrNotFound            = errors.New("store intel resource not found")
	ErrServiceUnavailable  = errors.New("store intel service unavailable")
	ErrUpstreamUnavailable = errors.New("store intel upstream unavailable")
)

type UpstreamClient interface {
	SearchApps(ctx context.Context, req dto.SearchAppsRequest) ([]dto.AppSummary, error)
	Suggest(ctx context.Context, req dto.SuggestRequest) ([]string, error)
	GetAppDetail(ctx context.Context, req dto.GetAppDetailRequest) (dto.AppDetail, error)
	SimilarApps(ctx context.Context, req dto.SimilarAppsRequest) ([]dto.AppSummary, error)
	GetAppPermissions(ctx context.Context, req dto.AppPermissionsRequest) (map[string][]string, error)
	FetchChart(ctx context.Context, req dto.FetchChartRequest) (dto.FetchChartResponse, error)
	FetchReviews(ctx context.Context, req dto.FetchReviewsRequest) (dto.FetchReviewsResponse, error)
}

type AlertPublisher interface {
	PublishAlerts(ctx context.Context, alerts []dto.Alert) error
}

type KeywordCorpusClient interface {
	Candidates(ctx context.Context, req KeywordCorpusCandidateRequest) ([]string, error)
	Contribute(ctx context.Context, req KeywordCorpusContributeRequest) error
}

type CoverageProgressFunc func(message string, fraction float64)

type StoreIntelService interface {
	EnsureSettingsDefaults(ctx context.Context) error
	GetSettings(ctx context.Context) (map[string]string, error)
	SetSettings(ctx context.Context, values map[string]string) (map[string]string, error)
	AcquireSettingValue(ctx context.Context, key, value string) (bool, error)
	CreateRefreshJob(ctx context.Context, req dto.RefreshJobRequest, job dto.RefreshJobResponse) (dto.RefreshJobResponse, error)
	UpdateRefreshJob(ctx context.Context, job dto.RefreshJobResponse) (dto.RefreshJobResponse, error)
	GetRefreshJob(ctx context.Context, jobID string) (dto.RefreshJobResponse, error)
	ListRefreshJobs(ctx context.Context, statuses []string, limit int) ([]dto.RefreshJobRecord, error)
	ClaimRefreshJob(ctx context.Context, jobID, workerID string, lockFor time.Duration) (dto.RefreshJobResponse, bool, error)
	SearchApps(ctx context.Context, req dto.SearchAppsRequest) (dto.SearchAppsResponse, error)
	SearchCachedApps(ctx context.Context, req dto.SearchAppsRequest) (dto.SearchAppsResponse, error)
	GetAppDetail(ctx context.Context, req dto.GetAppDetailRequest) (dto.AppDetail, error)
	GetCachedAppDetail(ctx context.Context, req dto.GetAppDetailRequest) (dto.CachedAppDetailResponse, error)
	SimilarApps(ctx context.Context, req dto.SimilarAppsRequest) (dto.SimilarAppsResponse, error)
	GetAppPermissions(ctx context.Context, req dto.AppPermissionsRequest) (dto.AppPermissionsResponse, error)
	FetchChart(ctx context.Context, req dto.FetchChartRequest) (dto.FetchChartResponse, error)
	FetchCachedChart(ctx context.Context, req dto.FetchChartRequest) (dto.FetchChartResponse, error)
	SaveChartSnapshot(ctx context.Context, req dto.SaveChartSnapshotRequest) (dto.SaveChartSnapshotResponse, error)
	ListAppSnapshotHistory(ctx context.Context, req dto.ListAppSnapshotsRequest) (dto.ListAppSnapshotsResponse, error)
	ListRecentAppSnapshots(ctx context.Context, req dto.ListRecentAppSnapshotsRequest) (dto.ListAppSnapshotsResponse, error)
	CountAppSnapshots(ctx context.Context) (dto.AppSnapshotCountResponse, error)
	RankChart(ctx context.Context, req dto.ChartRankRequest) (dto.ChartRankResponse, error)
	ListChartRankHistory(ctx context.Context, req dto.ChartRankHistoryRequest) (dto.ChartRankHistoryResponse, error)
	RankKeyword(ctx context.Context, req dto.KeywordRankRequest) (dto.KeywordRankResponse, error)
	ListKeywordRankHistory(ctx context.Context, req dto.KeywordRankHistoryRequest) (dto.KeywordRankHistoryResponse, error)
	ListRecentKeywordRanks(ctx context.Context, req dto.KeywordRankRecentRequest) (dto.KeywordRankHistoryResponse, error)
	AnalyzeKeywordCoverage(ctx context.Context, req dto.KeywordCoverageRequest) (dto.KeywordCoverageResponse, error)
	AnalyzeKeywordCoverageWithProgress(ctx context.Context, req dto.KeywordCoverageRequest, progress CoverageProgressFunc) (dto.KeywordCoverageResponse, error)
	LatestKeywordCoverage(ctx context.Context, req dto.KeywordCoverageRequest) (dto.KeywordCoverageResponse, error)
	FetchReviews(ctx context.Context, req dto.FetchReviewsRequest) (dto.FetchReviewsResponse, error)
	SaveReviews(ctx context.Context, req dto.SaveReviewsRequest) (dto.SaveReviewsResponse, error)
	ListCachedReviews(ctx context.Context, req dto.ListCachedReviewsRequest) (dto.ListCachedReviewsResponse, error)
	AddTrackedApp(ctx context.Context, req dto.AddTrackedAppRequest) (dto.TrackedApp, error)
	ListTrackedApps(ctx context.Context, req dto.ListTrackedAppsRequest) (dto.ListTrackedAppsResponse, error)
	RemoveTrackedApp(ctx context.Context, req dto.RemoveTrackedAppRequest) (dto.TrackingMutationResponse, error)
	SetTrackedAppEnabled(ctx context.Context, req dto.SetTrackedAppEnabledRequest) (dto.TrackingMutationResponse, error)
	SetTrackedAppFrequency(ctx context.Context, req dto.SetTrackedAppFrequencyRequest) (dto.TrackingMutationResponse, error)
	SetTrackedAppTag(ctx context.Context, req dto.SetTrackedAppTagRequest) (dto.TrackingMutationResponse, error)
	AddTrackedKeyword(ctx context.Context, req dto.AddTrackedKeywordRequest) (dto.TrackedKeyword, error)
	ListTrackedKeywords(ctx context.Context, req dto.ListTrackedKeywordsRequest) (dto.ListTrackedKeywordsResponse, error)
	RemoveTrackedKeyword(ctx context.Context, req dto.RemoveTrackedKeywordRequest) (dto.TrackingMutationResponse, error)
	SetTrackedKeywordEnabled(ctx context.Context, req dto.SetTrackedKeywordEnabledRequest) (dto.TrackingMutationResponse, error)
	SetTrackedKeywordFrequency(ctx context.Context, req dto.SetTrackedKeywordFrequencyRequest) (dto.TrackingMutationResponse, error)
	SyncTrackedKeywordNow(ctx context.Context, req dto.SyncTrackedKeywordRequest) (dto.SyncTrackedKeywordResponse, error)
	AddTrackedChartApp(ctx context.Context, req dto.AddTrackedChartAppRequest) (dto.TrackedChartApp, error)
	ListTrackedChartApps(ctx context.Context, req dto.ListTrackedChartAppsRequest) (dto.ListTrackedChartAppsResponse, error)
	RemoveTrackedChartApp(ctx context.Context, req dto.RemoveTrackedChartAppRequest) (dto.TrackingMutationResponse, error)
	SetTrackedChartAppEnabled(ctx context.Context, req dto.SetTrackedChartAppEnabledRequest) (dto.TrackingMutationResponse, error)
	SyncTrackedChartAppNow(ctx context.Context, req dto.SyncTrackedChartAppRequest) (dto.SyncTrackedChartAppResponse, error)
	SyncAppNow(ctx context.Context, req dto.SyncAppNowRequest) (dto.SyncAppNowResponse, error)
	SyncAll(ctx context.Context, req dto.SyncAllRequest) (dto.SyncAllResponse, error)
	ListAlerts(ctx context.Context, req dto.ListAlertsRequest) (dto.ListAlertsResponse, error)
	MarkAlertsRead(ctx context.Context, req dto.MarkAlertsReadRequest) (dto.MarkAlertsReadResponse, error)
	CleanupHistory(ctx context.Context) (dto.HistoryRetentionCleanupResponse, error)
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
	corpus    KeywordCorpusClient
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

func (s *storeIntelService) EnsureSettingsDefaults(ctx context.Context) error {
	if s == nil || s.repo == nil {
		return ErrServiceUnavailable
	}
	current, err := s.repo.ListSettings(ctx)
	if err != nil {
		return err
	}
	missing := map[string]string{}
	for key, value := range dto.DefaultSettings {
		if _, ok := current[key]; !ok {
			missing[key] = value
		}
	}
	if len(missing) == 0 {
		return nil
	}
	return s.repo.UpsertSettings(ctx, missing, nowISO(s.cfg.Now))
}

func (s *storeIntelService) GetSettings(ctx context.Context) (map[string]string, error) {
	if s == nil || s.repo == nil {
		return nil, ErrServiceUnavailable
	}
	values, err := s.repo.ListSettings(ctx)
	if err != nil {
		return nil, err
	}
	merged := copySettings(dto.DefaultSettings)
	for key, value := range values {
		merged[key] = value
	}
	return merged, nil
}

func (s *storeIntelService) SetSettings(ctx context.Context, values map[string]string) (map[string]string, error) {
	if s == nil || s.repo == nil {
		return nil, ErrServiceUnavailable
	}
	if len(values) > 0 {
		if err := s.repo.UpsertSettings(ctx, values, nowISO(s.cfg.Now)); err != nil {
			return nil, err
		}
	}
	return s.GetSettings(ctx)
}

func (s *storeIntelService) AcquireSettingValue(ctx context.Context, key, value string) (bool, error) {
	if s == nil || s.repo == nil {
		return false, ErrServiceUnavailable
	}
	key = strings.TrimSpace(key)
	if key == "" {
		return false, fmt.Errorf("%w: setting key is required", ErrInvalidRequest)
	}
	return s.repo.AcquireSettingValue(ctx, key, value, nowISO(s.cfg.Now))
}

func (s *storeIntelService) CreateRefreshJob(ctx context.Context, req dto.RefreshJobRequest, job dto.RefreshJobResponse) (dto.RefreshJobResponse, error) {
	if s == nil || s.repo == nil {
		return dto.RefreshJobResponse{}, ErrServiceUnavailable
	}
	req.Kind = strings.ToLower(strings.TrimSpace(req.Kind))
	if req.Kind == "" {
		return dto.RefreshJobResponse{}, fmt.Errorf("%w: refresh kind is required", ErrInvalidRequest)
	}
	job.JobID = strings.TrimSpace(job.JobID)
	if job.JobID == "" {
		return dto.RefreshJobResponse{}, fmt.Errorf("%w: refresh job_id is required", ErrInvalidRequest)
	}
	now := nowISO(s.cfg.Now)
	job.Kind = req.Kind
	if strings.TrimSpace(job.Status) == "" {
		job.Status = "queued"
	}
	if strings.TrimSpace(job.Message) == "" {
		job.Message = "刷新请求已加入服务器队列。"
	}
	if strings.TrimSpace(job.RequestedAt) == "" {
		job.RequestedAt = now
	}
	job.UpdatedAt = now
	return s.repo.CreateRefreshJob(ctx, repo.RefreshJobCreateInput{Job: job, Request: req})
}

func (s *storeIntelService) UpdateRefreshJob(ctx context.Context, job dto.RefreshJobResponse) (dto.RefreshJobResponse, error) {
	if s == nil || s.repo == nil {
		return dto.RefreshJobResponse{}, ErrServiceUnavailable
	}
	job.JobID = strings.TrimSpace(job.JobID)
	if job.JobID == "" {
		return dto.RefreshJobResponse{}, fmt.Errorf("%w: refresh job_id is required", ErrInvalidRequest)
	}
	if strings.TrimSpace(job.Status) == "" {
		return dto.RefreshJobResponse{}, fmt.Errorf("%w: refresh status is required", ErrInvalidRequest)
	}
	job.UpdatedAt = nowISO(s.cfg.Now)
	updated, err := s.repo.UpdateRefreshJob(ctx, repo.RefreshJobUpdateInput{
		JobID:      job.JobID,
		Status:     job.Status,
		Message:    job.Message,
		StartedAt:  job.StartedAt,
		FinishedAt: job.FinishedAt,
		UpdatedAt:  job.UpdatedAt,
	})
	if errors.Is(err, repo.ErrNotFound) {
		return dto.RefreshJobResponse{}, fmt.Errorf("%w: refresh job not found", ErrNotFound)
	}
	return updated, err
}

func (s *storeIntelService) GetRefreshJob(ctx context.Context, jobID string) (dto.RefreshJobResponse, error) {
	if s == nil || s.repo == nil {
		return dto.RefreshJobResponse{}, ErrServiceUnavailable
	}
	jobID = strings.TrimSpace(jobID)
	if jobID == "" {
		return dto.RefreshJobResponse{}, fmt.Errorf("%w: refresh job_id is required", ErrInvalidRequest)
	}
	job, err := s.repo.GetRefreshJob(ctx, jobID)
	if errors.Is(err, repo.ErrNotFound) {
		return dto.RefreshJobResponse{}, fmt.Errorf("%w: refresh job not found", ErrNotFound)
	}
	return job, err
}

func (s *storeIntelService) ListRefreshJobs(ctx context.Context, statuses []string, limit int) ([]dto.RefreshJobRecord, error) {
	if s == nil || s.repo == nil {
		return nil, ErrServiceUnavailable
	}
	normalized := make([]string, 0, len(statuses))
	for _, status := range statuses {
		status = strings.ToLower(strings.TrimSpace(status))
		if status != "" {
			normalized = append(normalized, status)
		}
	}
	if limit <= 0 {
		limit = 100
	}
	return s.repo.ListRefreshJobs(ctx, repo.RefreshJobListFilter{
		Statuses: normalized,
		Limit:    clamp(limit, 1, 500, 100),
	})
}

func (s *storeIntelService) ClaimRefreshJob(ctx context.Context, jobID, workerID string, lockFor time.Duration) (dto.RefreshJobResponse, bool, error) {
	if s == nil || s.repo == nil {
		return dto.RefreshJobResponse{}, false, ErrServiceUnavailable
	}
	jobID = strings.TrimSpace(jobID)
	if jobID == "" {
		return dto.RefreshJobResponse{}, false, fmt.Errorf("%w: refresh job_id is required", ErrInvalidRequest)
	}
	workerID = strings.TrimSpace(workerID)
	if workerID == "" {
		return dto.RefreshJobResponse{}, false, fmt.Errorf("%w: refresh worker_id is required", ErrInvalidRequest)
	}
	if lockFor <= 0 {
		lockFor = time.Hour
	}
	now := s.cfg.Now().UTC()
	job, claimed, err := s.repo.ClaimRefreshJob(ctx, repo.RefreshJobClaimInput{
		JobID:       jobID,
		WorkerID:    workerID,
		StartedAt:   now.Format(time.RFC3339),
		UpdatedAt:   now.Format(time.RFC3339),
		LockedUntil: now.Add(lockFor).Format(time.RFC3339),
	})
	if errors.Is(err, repo.ErrNotFound) {
		return dto.RefreshJobResponse{}, false, fmt.Errorf("%w: refresh job not found", ErrNotFound)
	}
	return job, claimed, err
}

type Option func(*storeIntelService)

func WithAlertPublisher(publisher AlertPublisher) Option {
	return func(s *storeIntelService) { s.publisher = publisher }
}

func WithKeywordCorpusClient(client KeywordCorpusClient) Option {
	return func(s *storeIntelService) { s.corpus = client }
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
	if s.repo != nil {
		_, _ = s.repo.UpsertCachedApps(ctx, repo.CachedAppsUpsertInput{
			Platform:  dto.PlatformGooglePlay,
			Country:   req.Country,
			Lang:      req.Lang,
			Items:     items,
			UpdatedAt: nowISO(s.cfg.Now),
		})
	}
	return dto.SearchAppsResponse{Items: items, Total: len(items)}, nil
}

func (s *storeIntelService) SearchCachedApps(ctx context.Context, req dto.SearchAppsRequest) (dto.SearchAppsResponse, error) {
	if s == nil || s.repo == nil {
		return dto.SearchAppsResponse{}, ErrServiceUnavailable
	}
	req.Query = strings.TrimSpace(req.Query)
	if req.Query == "" {
		return dto.SearchAppsResponse{}, fmt.Errorf("%w: query is required", ErrInvalidRequest)
	}
	req.Country, req.Lang = s.locale(req.Country, req.Lang)
	req.Limit = clamp(req.Limit, 1, 100, 50)
	items, err := s.repo.SearchCachedApps(ctx, repo.CachedAppSearchFilter{
		Platform: dto.PlatformGooglePlay,
		Query:    req.Query,
		Country:  req.Country,
		Lang:     req.Lang,
		Limit:    req.Limit,
	})
	if err != nil {
		return dto.SearchAppsResponse{}, err
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

func (s *storeIntelService) GetCachedAppDetail(ctx context.Context, req dto.GetAppDetailRequest) (dto.CachedAppDetailResponse, error) {
	if s == nil || s.repo == nil {
		return dto.CachedAppDetailResponse{}, ErrServiceUnavailable
	}
	identity, err := s.identity(req.AppID, req.Country, req.Lang)
	if err != nil {
		return dto.CachedAppDetailResponse{}, err
	}
	record, err := s.repo.LatestAppSnapshot(ctx, repo.LatestAppSnapshotFilter{
		Platform: identity.Platform,
		AppID:    identity.AppID,
		Country:  identity.Country,
		Lang:     identity.Lang,
	})
	if err != nil {
		if errors.Is(err, repo.ErrNotFound) {
			return dto.CachedAppDetailResponse{
				Detail: dto.AppDetail{AppSummary: dto.AppSummary{
					Platform: identity.Platform,
					AppID:    identity.AppID,
					StoreURL: googlePlayStoreURL(identity.AppID, identity.Country, identity.Lang),
				}},
				Cached: false,
			}, nil
		}
		return dto.CachedAppDetailResponse{}, err
	}
	detail := record.Raw
	detail.Platform = coalesce(detail.Platform, identity.Platform)
	detail.AppID = coalesce(detail.AppID, identity.AppID)
	detail.Title = coalesce(detail.Title, record.Title, identity.AppID)
	detail.Rating = coalesceFloat(detail.Rating, record.Rating)
	detail.RatingsCount = coalesceInt64(detail.RatingsCount, record.RatingsCount)
	detail.ReviewsCount = coalesceInt64(detail.ReviewsCount, record.ReviewsCount)
	detail.Installs = coalesce(detail.Installs, record.Installs)
	detail.MinInstalls = coalesceInt64(detail.MinInstalls, record.MinInstalls)
	detail.RealInstalls = coalesceInt64(detail.RealInstalls, record.RealInstalls)
	detail.Version = coalesce(detail.Version, record.Version)
	detail.StoreURL = coalesce(detail.StoreURL, googlePlayStoreURL(identity.AppID, identity.Country, identity.Lang))
	return dto.CachedAppDetailResponse{Detail: detail, Cached: true, CapturedAt: record.CapturedAt}, nil
}

func (s *storeIntelService) SimilarApps(ctx context.Context, req dto.SimilarAppsRequest) (dto.SimilarAppsResponse, error) {
	if s == nil || s.upstream == nil {
		return dto.SimilarAppsResponse{}, ErrServiceUnavailable
	}
	req.AppID = strings.TrimSpace(req.AppID)
	if req.AppID == "" {
		return dto.SimilarAppsResponse{}, fmt.Errorf("%w: app_id is required", ErrInvalidRequest)
	}
	req.Country, req.Lang = s.locale(req.Country, req.Lang)
	req.Limit = clamp(req.Limit, 1, 100, 20)
	items, err := s.upstream.SimilarApps(ctx, req)
	if err != nil {
		return dto.SimilarAppsResponse{}, fmt.Errorf("%w: %v", ErrUpstreamUnavailable, err)
	}
	for index := range items {
		items[index].Platform = coalesce(items[index].Platform, dto.PlatformGooglePlay)
		items[index].StoreURL = coalesce(items[index].StoreURL, googlePlayStoreURL(items[index].AppID, req.Country, req.Lang))
	}
	return dto.SimilarAppsResponse{Items: items, Total: len(items)}, nil
}

func (s *storeIntelService) GetAppPermissions(ctx context.Context, req dto.AppPermissionsRequest) (dto.AppPermissionsResponse, error) {
	if s == nil || s.upstream == nil {
		return dto.AppPermissionsResponse{}, ErrServiceUnavailable
	}
	req.AppID = strings.TrimSpace(req.AppID)
	if req.AppID == "" {
		return dto.AppPermissionsResponse{}, fmt.Errorf("%w: app_id is required", ErrInvalidRequest)
	}
	req.Country, req.Lang = s.locale(req.Country, req.Lang)
	groups, err := s.upstream.GetAppPermissions(ctx, req)
	if err != nil {
		return dto.AppPermissionsResponse{}, fmt.Errorf("%w: %v", ErrUpstreamUnavailable, err)
	}
	return dto.AppPermissionsResponse{Groups: groups}, nil
}

func (s *storeIntelService) FetchChart(ctx context.Context, req dto.FetchChartRequest) (dto.FetchChartResponse, error) {
	if s == nil || s.upstream == nil {
		return dto.FetchChartResponse{}, ErrServiceUnavailable
	}
	req.ChartType = normalizeChartType(req.ChartType)
	req.Category = strings.TrimSpace(req.Category)
	req.Country, req.Lang = s.locale(req.Country, req.Lang)
	req.Limit = clamp(req.Limit, 1, 200, 100)
	result, err := s.upstream.FetchChart(ctx, req)
	if err != nil {
		return dto.FetchChartResponse{}, fmt.Errorf("%w: %v", ErrUpstreamUnavailable, err)
	}
	for index := range result.Items {
		result.Items[index].Platform = coalesce(result.Items[index].Platform, dto.PlatformGooglePlay)
		result.Items[index].ChartType = coalesce(result.Items[index].ChartType, req.ChartType)
		result.Items[index].Category = coalesce(result.Items[index].Category, req.Category)
		result.Items[index].Country = coalesce(result.Items[index].Country, req.Country)
		result.Items[index].Lang = coalesce(result.Items[index].Lang, req.Lang)
		if result.Items[index].Rank == 0 {
			result.Items[index].Rank = index + 1
		}
	}
	result.Total = len(result.Items)
	if s.repo != nil {
		_, _ = s.repo.SaveChartSnapshot(ctx, repo.SaveChartSnapshotInput{
			ChartType:  req.ChartType,
			Category:   req.Category,
			Country:    req.Country,
			Lang:       req.Lang,
			Items:      result.Items,
			CapturedAt: nowISO(s.cfg.Now),
		})
	}
	return result, nil
}

func (s *storeIntelService) FetchCachedChart(ctx context.Context, req dto.FetchChartRequest) (dto.FetchChartResponse, error) {
	if s == nil || s.repo == nil {
		return dto.FetchChartResponse{}, ErrServiceUnavailable
	}
	req.ChartType = normalizeChartType(req.ChartType)
	req.Category = strings.TrimSpace(req.Category)
	req.Country, req.Lang = s.locale(req.Country, req.Lang)
	req.Limit = clamp(req.Limit, 1, 200, 100)
	items, capturedAt, err := s.repo.ListLatestChartSnapshot(ctx, repo.LatestChartSnapshotFilter{
		Platform:  dto.PlatformGooglePlay,
		ChartType: req.ChartType,
		Category:  req.Category,
		Country:   req.Country,
		Lang:      req.Lang,
		Limit:     req.Limit,
	})
	if err != nil {
		return dto.FetchChartResponse{}, err
	}
	return dto.FetchChartResponse{Items: items, Total: len(items), Cached: true, CapturedAt: capturedAt}, nil
}

func (s *storeIntelService) SaveChartSnapshot(ctx context.Context, req dto.SaveChartSnapshotRequest) (dto.SaveChartSnapshotResponse, error) {
	if s == nil || s.repo == nil {
		return dto.SaveChartSnapshotResponse{}, ErrServiceUnavailable
	}
	chartType := normalizeChartType(req.ChartType)
	country, lang := s.locale(req.Country, req.Lang)
	capturedAt := nowISO(s.cfg.Now)
	saved, err := s.repo.SaveChartSnapshot(ctx, repo.SaveChartSnapshotInput{
		ChartType:  chartType,
		Category:   strings.TrimSpace(req.Category),
		Country:    country,
		Lang:       lang,
		Items:      req.Items,
		CapturedAt: capturedAt,
	})
	if err != nil {
		return dto.SaveChartSnapshotResponse{}, err
	}
	return dto.SaveChartSnapshotResponse{Saved: saved, CapturedAt: capturedAt}, nil
}

func (s *storeIntelService) ListAppSnapshotHistory(ctx context.Context, req dto.ListAppSnapshotsRequest) (dto.ListAppSnapshotsResponse, error) {
	if s == nil || s.repo == nil {
		return dto.ListAppSnapshotsResponse{}, ErrServiceUnavailable
	}
	req.AppID = strings.TrimSpace(req.AppID)
	if req.AppID == "" {
		return dto.ListAppSnapshotsResponse{}, fmt.Errorf("%w: app_id is required", ErrInvalidRequest)
	}
	country, lang := s.locale(req.Country, req.Lang)
	limit := 0
	if req.Limit > 0 {
		limit = clamp(req.Limit, 1, 1000, 1000)
	}
	items, err := s.repo.ListAppSnapshotHistory(ctx, repo.AppSnapshotHistoryFilter{
		Platform: dto.PlatformGooglePlay,
		AppID:    req.AppID,
		Country:  country,
		Lang:     lang,
		Limit:    limit,
	})
	if err != nil {
		return dto.ListAppSnapshotsResponse{}, err
	}
	return dto.ListAppSnapshotsResponse{Items: items, Total: len(items)}, nil
}

func (s *storeIntelService) ListRecentAppSnapshots(ctx context.Context, req dto.ListRecentAppSnapshotsRequest) (dto.ListAppSnapshotsResponse, error) {
	if s == nil || s.repo == nil {
		return dto.ListAppSnapshotsResponse{}, ErrServiceUnavailable
	}
	items, err := s.repo.ListRecentAppSnapshots(ctx, repo.AppSnapshotRecentFilter{
		Limit: clamp(req.Limit, 1, 1000, 8),
	})
	if err != nil {
		return dto.ListAppSnapshotsResponse{}, err
	}
	return dto.ListAppSnapshotsResponse{Items: items, Total: len(items)}, nil
}

func (s *storeIntelService) CountAppSnapshots(ctx context.Context) (dto.AppSnapshotCountResponse, error) {
	if s == nil || s.repo == nil {
		return dto.AppSnapshotCountResponse{}, ErrServiceUnavailable
	}
	total, err := s.repo.CountAppSnapshots(ctx)
	if err != nil {
		return dto.AppSnapshotCountResponse{}, err
	}
	return dto.AppSnapshotCountResponse{Total: total}, nil
}

func (s *storeIntelService) RankChart(ctx context.Context, req dto.ChartRankRequest) (dto.ChartRankResponse, error) {
	if s == nil || s.repo == nil {
		return dto.ChartRankResponse{}, ErrServiceUnavailable
	}
	req.AppID = strings.TrimSpace(req.AppID)
	if req.AppID == "" {
		return dto.ChartRankResponse{}, fmt.Errorf("%w: app_id is required", ErrInvalidRequest)
	}
	collection := normalizeChartType(req.Collection)
	category := normalizeChartCategory(req.Category)
	country, lang := s.locale(req.Country, req.Lang)
	limit := clamp(req.Limit, 1, 200, 100)
	chart, err := s.FetchChart(ctx, dto.FetchChartRequest{
		ChartType: collection,
		Category:  category,
		Country:   country,
		Lang:      lang,
		Limit:     limit,
	})
	if err != nil {
		return dto.ChartRankResponse{}, err
	}
	var rank *int
	for _, item := range chart.Items {
		if sameAppID(item.AppID, req.AppID) {
			value := item.Rank
			if value == 0 {
				value = 1
			}
			rank = &value
			break
		}
	}
	capturedAt := nowISO(s.cfg.Now)
	result := dto.ChartRankResponse{
		Platform:     dto.PlatformGooglePlay,
		AppID:        req.AppID,
		Collection:   collection,
		Category:     category,
		Country:      country,
		Lang:         lang,
		Found:        rank != nil,
		Rank:         rank,
		CheckedLimit: limit,
		CapturedAt:   capturedAt,
	}
	current, _, err := s.repo.UpsertChartRank(ctx, repo.ChartRankUpsertInput{
		Result:      result,
		CapturedAt:  capturedAt,
		CapturedDay: dateKey(capturedAt),
	})
	if err != nil {
		return dto.ChartRankResponse{}, err
	}
	return current, nil
}

func (s *storeIntelService) ListChartRankHistory(ctx context.Context, req dto.ChartRankHistoryRequest) (dto.ChartRankHistoryResponse, error) {
	if s == nil || s.repo == nil {
		return dto.ChartRankHistoryResponse{}, ErrServiceUnavailable
	}
	req.AppID = strings.TrimSpace(req.AppID)
	if req.AppID == "" {
		return dto.ChartRankHistoryResponse{}, fmt.Errorf("%w: app_id is required", ErrInvalidRequest)
	}
	collection := normalizeChartType(req.Collection)
	category := normalizeChartCategory(req.Category)
	country, lang := s.locale(req.Country, req.Lang)
	limit := 0
	if req.Limit > 0 {
		limit = clamp(req.Limit, 1, 1000, 1000)
	}
	items, err := s.repo.ListChartRankHistory(ctx, repo.ChartRankHistoryFilter{
		Platform:   dto.PlatformGooglePlay,
		AppID:      req.AppID,
		Collection: collection,
		Category:   category,
		Country:    country,
		Lang:       lang,
		Limit:      limit,
	})
	if err != nil {
		return dto.ChartRankHistoryResponse{}, err
	}
	return dto.ChartRankHistoryResponse{Items: items, Total: len(items)}, nil
}

func (s *storeIntelService) RankKeyword(ctx context.Context, req dto.KeywordRankRequest) (dto.KeywordRankResponse, error) {
	if s == nil || s.repo == nil {
		return dto.KeywordRankResponse{}, ErrServiceUnavailable
	}
	req.Keyword = strings.TrimSpace(req.Keyword)
	req.AppID = strings.TrimSpace(req.AppID)
	if req.Keyword == "" || req.AppID == "" {
		return dto.KeywordRankResponse{}, fmt.Errorf("%w: keyword and app_id are required", ErrInvalidRequest)
	}
	country, lang := s.locale(req.Country, req.Lang)
	limit := clamp(req.Limit, 1, 200, 100)
	search, err := s.SearchApps(ctx, dto.SearchAppsRequest{
		Query:   req.Keyword,
		Country: country,
		Lang:    lang,
		Limit:   limit,
	})
	if err != nil {
		return dto.KeywordRankResponse{}, err
	}
	var rank *int
	for index, item := range search.Items {
		if sameAppID(item.AppID, req.AppID) {
			value := index + 1
			rank = &value
			break
		}
	}
	capturedAt := nowISO(s.cfg.Now)
	result := dto.KeywordRankResponse{
		Platform:     dto.PlatformGooglePlay,
		Keyword:      req.Keyword,
		AppID:        req.AppID,
		Country:      country,
		Lang:         lang,
		Found:        rank != nil,
		Rank:         rank,
		CheckedLimit: limit,
		CapturedAt:   capturedAt,
		Results:      search.Items,
	}
	if _, err := s.repo.UpsertKeywordRank(ctx, repo.KeywordRankUpsertInput{
		Result:      result,
		CapturedAt:  capturedAt,
		CapturedDay: dateKey(capturedAt),
	}); err != nil {
		return dto.KeywordRankResponse{}, err
	}
	return result, nil
}

func (s *storeIntelService) AnalyzeKeywordCoverage(ctx context.Context, req dto.KeywordCoverageRequest) (dto.KeywordCoverageResponse, error) {
	return s.analyzeKeywordCoverage(ctx, req, nil)
}

func (s *storeIntelService) AnalyzeKeywordCoverageWithProgress(ctx context.Context, req dto.KeywordCoverageRequest, progress CoverageProgressFunc) (dto.KeywordCoverageResponse, error) {
	return s.analyzeKeywordCoverage(ctx, req, progress)
}

func (s *storeIntelService) analyzeKeywordCoverage(ctx context.Context, req dto.KeywordCoverageRequest, progress CoverageProgressFunc) (dto.KeywordCoverageResponse, error) {
	if s == nil || s.upstream == nil {
		return dto.KeywordCoverageResponse{}, ErrServiceUnavailable
	}
	appID := strings.TrimSpace(req.AppID)
	if appID == "" {
		return dto.KeywordCoverageResponse{}, fmt.Errorf("%w: app_id is required", ErrInvalidRequest)
	}
	country, lang := s.locale(req.Country, req.Lang)
	limit := clamp(req.Limit, 1, 200, 50)
	maxCandidates := clamp(req.MaxCandidates, 1, 200, 120)
	if req.Deep && maxCandidates < 200 {
		maxCandidates = 200
	}
	canonical := strings.TrimSpace(req.CanonicalAppID)
	candidates := normalizeCoverageCandidates(req.Candidates, maxCandidates)
	if len(candidates) == 0 {
		if progress != nil {
			progress("正在生成候选关键词...", 0)
		}
		detail, err := s.GetAppDetail(ctx, dto.GetAppDetailRequest{
			AppID:   appID,
			Country: country,
			Lang:    lang,
		})
		if err != nil {
			return dto.KeywordCoverageResponse{}, err
		}
		canonical = coalesce(canonical, detail.AppID)
		candidates = s.coverageCandidates(ctx, detail, appID, country, lang, maxCandidates, req.Deep)
	}
	targets := coverageTargets(appID, canonical)
	covered := make([]dto.KeywordCoverageHit, 0)
	proxyPool, workers := s.coverageProxySearchConfig(ctx)
	covered, failures, successes := s.scanCoverageCandidates(ctx, candidates, country, lang, limit, targets, proxyPool, workers, progress)
	if successes == 0 && failures >= 5 {
		return dto.KeywordCoverageResponse{}, fmt.Errorf("%w: first %d keyword searches failed", ErrUpstreamUnavailable, failures)
	}
	sort.SliceStable(covered, func(i, j int) bool {
		if covered[i].Rank == covered[j].Rank {
			return covered[i].Keyword < covered[j].Keyword
		}
		return covered[i].Rank < covered[j].Rank
	})
	if len(covered) > 0 {
		items := make([]repo.KeywordCorpusItem, 0, len(covered))
		for _, hit := range covered {
			items = append(items, repo.KeywordCorpusItem{
				Keyword:   hit.Keyword,
				Source:    "covered",
				Confirmed: true,
			})
		}
		s.recordCoverageCorpus(ctx, country, lang, items)
	}
	result := dto.KeywordCoverageResponse{
		Platform:       dto.PlatformGooglePlay,
		AppID:          appID,
		CanonicalAppID: coalesce(canonical, appID),
		Country:        country,
		Lang:           lang,
		Deep:           req.Deep,
		Candidates:     candidates,
		CandidateCount: len(candidates),
		Covered:        covered,
		CheckedLimit:   limit,
		CapturedAt:     nowISO(s.cfg.Now),
	}
	if s.repo != nil {
		_ = s.repo.UpsertKeywordCoverage(ctx, repo.KeywordCoverageUpsertInput{
			Result:     result,
			CapturedAt: result.CapturedAt,
		})
	}
	return result, nil
}

func (s *storeIntelService) LatestKeywordCoverage(ctx context.Context, req dto.KeywordCoverageRequest) (dto.KeywordCoverageResponse, error) {
	if s == nil || s.repo == nil {
		return dto.KeywordCoverageResponse{}, ErrServiceUnavailable
	}
	appID := strings.TrimSpace(req.AppID)
	if appID == "" {
		return dto.KeywordCoverageResponse{}, fmt.Errorf("%w: app_id is required", ErrInvalidRequest)
	}
	country, lang := s.locale(req.Country, req.Lang)
	return s.repo.LatestKeywordCoverage(ctx, repo.KeywordCoverageLatestFilter{
		Platform: dto.PlatformGooglePlay,
		AppID:    appID,
		Country:  country,
		Lang:     lang,
		Deep:     req.Deep,
	})
}

func (s *storeIntelService) scanCoverageCandidates(
	ctx context.Context,
	candidates []string,
	country, lang string,
	limit int,
	targets []string,
	proxyPool *coverageProxyPool,
	workers int,
	progress CoverageProgressFunc,
) ([]dto.KeywordCoverageHit, int, int) {
	total := len(candidates)
	if workers <= 1 || proxyPool == nil || !proxyPool.hasProxies() {
		searchPool := proxyPool
		if searchPool != nil && !searchPool.hasProxies() {
			searchPool = nil
		}
		covered := make([]dto.KeywordCoverageHit, 0)
		failures := 0
		successes := 0
		for index, keyword := range candidates {
			rank, ok := s.searchCoverageKeyword(ctx, keyword, country, lang, limit, targets, searchPool)
			if ok {
				successes++
				if rank > 0 {
					covered = append(covered, dto.KeywordCoverageHit{Keyword: keyword, Rank: rank})
				}
			} else {
				failures++
				if successes == 0 && failures >= 5 {
					emitCoverageProgress(progress, index+1, total, keyword)
					break
				}
			}
			emitCoverageProgress(progress, index+1, total, keyword)
		}
		return covered, failures, successes
	}

	workers = clamp(workers, 1, 16, 1)
	jobs := make(chan string)
	var wg sync.WaitGroup
	var mu sync.Mutex
	covered := make([]dto.KeywordCoverageHit, 0)
	failures := 0
	successes := 0
	stop := false
	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for keyword := range jobs {
				mu.Lock()
				if stop {
					mu.Unlock()
					continue
				}
				mu.Unlock()
				rank, ok := s.searchCoverageKeyword(ctx, keyword, country, lang, limit, targets, proxyPool)
				var done int
				mu.Lock()
				if ok {
					successes++
					if rank > 0 {
						covered = append(covered, dto.KeywordCoverageHit{Keyword: keyword, Rank: rank})
					}
				} else {
					failures++
					if successes == 0 && failures >= 5 {
						stop = true
					}
				}
				done = failures + successes
				mu.Unlock()
				emitCoverageProgress(progress, done, total, keyword)
			}
		}()
	}
	for _, keyword := range candidates {
		mu.Lock()
		shouldStop := stop
		mu.Unlock()
		if shouldStop {
			break
		}
		jobs <- keyword
	}
	close(jobs)
	wg.Wait()
	return covered, failures, successes
}

func (s *storeIntelService) searchCoverageKeyword(
	ctx context.Context,
	keyword, country, lang string,
	limit int,
	targets []string,
	proxyPool *coverageProxyPool,
) (int, bool) {
	if proxyPool == nil || !proxyPool.hasProxies() {
		search, err := s.SearchApps(ctx, dto.SearchAppsRequest{
			Query:   keyword,
			Country: country,
			Lang:    lang,
			Limit:   limit,
		})
		if err != nil {
			return 0, false
		}
		return coverageRank(search.Items, targets), true
	}
	attempts := min(coverageMaxProxyAttempts, proxyPool.len())
	for i := 0; i < max(1, attempts); i++ {
		proxy := proxyPool.lease()
		if proxy == "" {
			break
		}
		search, err := s.SearchApps(ctx, dto.SearchAppsRequest{
			Query:   keyword,
			Country: country,
			Lang:    lang,
			Limit:   limit,
			Proxy:   proxy,
		})
		if err != nil {
			proxyPool.reportBad(proxy)
			continue
		}
		proxyPool.reportOK(proxy)
		return coverageRank(search.Items, targets), true
	}
	return 0, false
}

func (s *storeIntelService) coverageProxySearchConfig(ctx context.Context) (*coverageProxyPool, int) {
	settings, err := s.GetSettings(ctx)
	if err != nil {
		settings = dto.DefaultSettings
	}
	proxies := parseCoverageProxies(settingValue(settings, "coverage_proxies"))
	if len(proxies) == 0 {
		return nil, 1
	}
	return newCoverageProxyPool(proxies), clamp(settingInt(settings, "coverage_concurrency"), 1, 16, 6)
}

func emitCoverageProgress(progress CoverageProgressFunc, done, total int, keyword string) {
	if progress == nil {
		return
	}
	fraction := 1.0
	if total > 0 {
		fraction = float64(done) / float64(total)
	}
	if fraction < 0 {
		fraction = 0
	}
	if fraction > 1 {
		fraction = 1
	}
	progress(fmt.Sprintf("覆盖检测 %d/%d：%s", done, total, keyword), fraction)
}

func (s *storeIntelService) ListKeywordRankHistory(ctx context.Context, req dto.KeywordRankHistoryRequest) (dto.KeywordRankHistoryResponse, error) {
	if s == nil || s.repo == nil {
		return dto.KeywordRankHistoryResponse{}, ErrServiceUnavailable
	}
	req.Keyword = strings.TrimSpace(req.Keyword)
	req.AppID = strings.TrimSpace(req.AppID)
	if req.Keyword == "" || req.AppID == "" {
		return dto.KeywordRankHistoryResponse{}, fmt.Errorf("%w: keyword and app_id are required", ErrInvalidRequest)
	}
	country, lang := s.locale(req.Country, req.Lang)
	limit := 0
	if req.Limit > 0 {
		limit = clamp(req.Limit, 1, 1000, 1000)
	}
	items, err := s.repo.ListKeywordRankHistory(ctx, repo.KeywordRankHistoryFilter{
		Platform: dto.PlatformGooglePlay,
		Keyword:  req.Keyword,
		AppID:    req.AppID,
		Country:  country,
		Lang:     lang,
		Limit:    limit,
	})
	if err != nil {
		return dto.KeywordRankHistoryResponse{}, err
	}
	return dto.KeywordRankHistoryResponse{Items: items, Total: len(items)}, nil
}

func (s *storeIntelService) ListRecentKeywordRanks(ctx context.Context, req dto.KeywordRankRecentRequest) (dto.KeywordRankHistoryResponse, error) {
	if s == nil || s.repo == nil {
		return dto.KeywordRankHistoryResponse{}, ErrServiceUnavailable
	}
	country := ""
	lang := ""
	if strings.TrimSpace(req.Country) != "" {
		country = strings.ToLower(strings.TrimSpace(req.Country))
	}
	if strings.TrimSpace(req.Lang) != "" {
		lang = strings.ToLower(strings.TrimSpace(req.Lang))
	}
	items, err := s.repo.ListRecentKeywordRanks(ctx, repo.KeywordRankRecentFilter{
		Platform: dto.PlatformGooglePlay,
		AppID:    strings.TrimSpace(req.AppID),
		Country:  country,
		Lang:     lang,
		Limit:    clamp(req.Limit, 1, 1000, 8),
	})
	if err != nil {
		return dto.KeywordRankHistoryResponse{}, err
	}
	return dto.KeywordRankHistoryResponse{Items: items, Total: len(items)}, nil
}

func (s *storeIntelService) FetchReviews(ctx context.Context, req dto.FetchReviewsRequest) (dto.FetchReviewsResponse, error) {
	if s == nil || s.upstream == nil {
		return dto.FetchReviewsResponse{}, ErrServiceUnavailable
	}
	identity, err := s.identity(req.AppID, req.Country, req.Lang)
	if err != nil {
		return dto.FetchReviewsResponse{}, err
	}
	req.AppID = identity.AppID
	req.Country = identity.Country
	req.Lang = identity.Lang
	req.Sort = normalizeReviewSort(req.Sort)
	req.Limit = clamp(req.Limit, 1, 200, 20)
	result, err := s.upstream.FetchReviews(ctx, req)
	if err != nil {
		return dto.FetchReviewsResponse{}, fmt.Errorf("%w: %v", ErrUpstreamUnavailable, err)
	}
	for i := range result.Items {
		result.Items[i].Platform = coalesce(result.Items[i].Platform, identity.Platform)
		result.Items[i].AppID = coalesce(result.Items[i].AppID, identity.AppID)
		result.Items[i].Country = coalesce(result.Items[i].Country, identity.Country)
		result.Items[i].Lang = coalesce(result.Items[i].Lang, identity.Lang)
	}
	result.Total = len(result.Items)
	return result, nil
}

func (s *storeIntelService) SaveReviews(ctx context.Context, req dto.SaveReviewsRequest) (dto.SaveReviewsResponse, error) {
	if s == nil || s.repo == nil {
		return dto.SaveReviewsResponse{}, ErrServiceUnavailable
	}
	identity, err := s.identity(req.AppID, req.Country, req.Lang)
	if err != nil {
		return dto.SaveReviewsResponse{}, err
	}
	saved, err := s.repo.SaveReviews(ctx, repo.SaveReviewsInput{
		Identity:   identity,
		Items:      req.Items,
		CapturedAt: nowISO(s.cfg.Now),
	})
	if err != nil {
		return dto.SaveReviewsResponse{}, err
	}
	return dto.SaveReviewsResponse{Saved: saved}, nil
}

func (s *storeIntelService) ListCachedReviews(ctx context.Context, req dto.ListCachedReviewsRequest) (dto.ListCachedReviewsResponse, error) {
	if s == nil || s.repo == nil {
		return dto.ListCachedReviewsResponse{}, ErrServiceUnavailable
	}
	req.AppID = strings.TrimSpace(req.AppID)
	if req.AppID == "" {
		return dto.ListCachedReviewsResponse{}, fmt.Errorf("%w: app_id is required", ErrInvalidRequest)
	}
	items, err := s.repo.ListReviews(ctx, repo.ListReviewsFilter{
		AppID: req.AppID,
		Limit: clamp(req.Limit, 1, 1000, 100),
	})
	if err != nil {
		return dto.ListCachedReviewsResponse{}, err
	}
	return dto.ListCachedReviewsResponse{Items: items, Total: len(items)}, nil
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

func (s *storeIntelService) RemoveTrackedApp(ctx context.Context, req dto.RemoveTrackedAppRequest) (dto.TrackingMutationResponse, error) {
	if s == nil || s.repo == nil {
		return dto.TrackingMutationResponse{}, ErrServiceUnavailable
	}
	identity, err := s.identity(req.AppID, req.Country, req.Lang)
	if err != nil {
		return dto.TrackingMutationResponse{}, err
	}
	updated, err := s.repo.RemoveTrackedApp(ctx, identity)
	if err != nil {
		return dto.TrackingMutationResponse{}, err
	}
	return dto.TrackingMutationResponse{Updated: updated}, nil
}

func (s *storeIntelService) SetTrackedAppEnabled(ctx context.Context, req dto.SetTrackedAppEnabledRequest) (dto.TrackingMutationResponse, error) {
	if s == nil || s.repo == nil {
		return dto.TrackingMutationResponse{}, ErrServiceUnavailable
	}
	identity, err := s.identity(req.AppID, req.Country, req.Lang)
	if err != nil {
		return dto.TrackingMutationResponse{}, err
	}
	enabled, updated, err := s.repo.SetTrackedAppEnabled(ctx, identity, req.Enabled, nowISO(s.cfg.Now))
	if err != nil {
		return dto.TrackingMutationResponse{}, err
	}
	return dto.TrackingMutationResponse{Updated: updated, Enabled: boolPtr(enabled)}, nil
}

func (s *storeIntelService) SetTrackedAppFrequency(ctx context.Context, req dto.SetTrackedAppFrequencyRequest) (dto.TrackingMutationResponse, error) {
	if s == nil || s.repo == nil {
		return dto.TrackingMutationResponse{}, ErrServiceUnavailable
	}
	identity, err := s.identity(req.AppID, req.Country, req.Lang)
	if err != nil {
		return dto.TrackingMutationResponse{}, err
	}
	frequency, updated, err := s.repo.SetTrackedAppFrequency(ctx, identity, strings.TrimSpace(req.Frequency), nowISO(s.cfg.Now))
	if err != nil {
		return dto.TrackingMutationResponse{}, err
	}
	return dto.TrackingMutationResponse{Updated: updated, Frequency: frequency}, nil
}

func (s *storeIntelService) SetTrackedAppTag(ctx context.Context, req dto.SetTrackedAppTagRequest) (dto.TrackingMutationResponse, error) {
	if s == nil || s.repo == nil {
		return dto.TrackingMutationResponse{}, ErrServiceUnavailable
	}
	identity, err := s.identity(req.AppID, req.Country, req.Lang)
	if err != nil {
		return dto.TrackingMutationResponse{}, err
	}
	tag, updated, err := s.repo.SetTrackedAppTag(ctx, identity, req.Tag, nowISO(s.cfg.Now))
	if err != nil {
		return dto.TrackingMutationResponse{}, err
	}
	return dto.TrackingMutationResponse{Updated: updated, Tag: tag}, nil
}

func (s *storeIntelService) AddTrackedKeyword(ctx context.Context, req dto.AddTrackedKeywordRequest) (dto.TrackedKeyword, error) {
	if s == nil || s.repo == nil {
		return dto.TrackedKeyword{}, ErrServiceUnavailable
	}
	input, err := s.trackedKeywordInput(req.Keyword, req.AppID, req.Country, req.Lang, req.Platform)
	if err != nil {
		return dto.TrackedKeyword{}, err
	}
	input.Enabled = true
	input.NowISO = nowISO(s.cfg.Now)
	return s.repo.UpsertTrackedKeyword(ctx, input)
}

func (s *storeIntelService) ListTrackedKeywords(ctx context.Context, req dto.ListTrackedKeywordsRequest) (dto.ListTrackedKeywordsResponse, error) {
	if s == nil || s.repo == nil {
		return dto.ListTrackedKeywordsResponse{}, ErrServiceUnavailable
	}
	items, err := s.repo.ListTrackedKeywords(ctx, repo.TrackedMonitorFilter{Enabled: req.Enabled})
	if err != nil {
		return dto.ListTrackedKeywordsResponse{}, err
	}
	return dto.ListTrackedKeywordsResponse{Items: items, Total: len(items)}, nil
}

func (s *storeIntelService) RemoveTrackedKeyword(ctx context.Context, req dto.RemoveTrackedKeywordRequest) (dto.TrackingMutationResponse, error) {
	if s == nil || s.repo == nil {
		return dto.TrackingMutationResponse{}, ErrServiceUnavailable
	}
	input, err := s.trackedKeywordInput(req.Keyword, req.AppID, req.Country, req.Lang, req.Platform)
	if err != nil {
		return dto.TrackingMutationResponse{}, err
	}
	updated, err := s.repo.RemoveTrackedKeyword(ctx, input)
	if err != nil {
		return dto.TrackingMutationResponse{}, err
	}
	return dto.TrackingMutationResponse{Updated: updated}, nil
}

func (s *storeIntelService) SetTrackedKeywordEnabled(ctx context.Context, req dto.SetTrackedKeywordEnabledRequest) (dto.TrackingMutationResponse, error) {
	if s == nil || s.repo == nil {
		return dto.TrackingMutationResponse{}, ErrServiceUnavailable
	}
	input, err := s.trackedKeywordInput(req.Keyword, req.AppID, req.Country, req.Lang, req.Platform)
	if err != nil {
		return dto.TrackingMutationResponse{}, err
	}
	enabled, updated, err := s.repo.SetTrackedKeywordEnabled(ctx, input, req.Enabled, nowISO(s.cfg.Now))
	if err != nil {
		return dto.TrackingMutationResponse{}, err
	}
	return dto.TrackingMutationResponse{Updated: updated, Enabled: boolPtr(enabled)}, nil
}

func (s *storeIntelService) SetTrackedKeywordFrequency(ctx context.Context, req dto.SetTrackedKeywordFrequencyRequest) (dto.TrackingMutationResponse, error) {
	if s == nil || s.repo == nil {
		return dto.TrackingMutationResponse{}, ErrServiceUnavailable
	}
	input, err := s.trackedKeywordInput(req.Keyword, req.AppID, req.Country, req.Lang, req.Platform)
	if err != nil {
		return dto.TrackingMutationResponse{}, err
	}
	frequency, updated, err := s.repo.SetTrackedKeywordFrequency(ctx, input, strings.TrimSpace(req.Frequency), nowISO(s.cfg.Now))
	if err != nil {
		return dto.TrackingMutationResponse{}, err
	}
	return dto.TrackingMutationResponse{Updated: updated, Frequency: frequency}, nil
}

func (s *storeIntelService) SyncTrackedKeywordNow(ctx context.Context, req dto.SyncTrackedKeywordRequest) (dto.SyncTrackedKeywordResponse, error) {
	if s == nil || s.repo == nil {
		return dto.SyncTrackedKeywordResponse{}, ErrServiceUnavailable
	}
	input, err := s.trackedKeywordInput(req.Keyword, req.AppID, req.Country, req.Lang, req.Platform)
	if err != nil {
		return dto.SyncTrackedKeywordResponse{}, err
	}
	if input.Platform != dto.PlatformGooglePlay {
		return dto.SyncTrackedKeywordResponse{}, fmt.Errorf("%w: platform %s is not supported by Go keyword sync", ErrInvalidRequest, input.Platform)
	}
	limit := clamp(req.Limit, 1, 200, s.defaultLimit(ctx))
	result, err := s.RankKeyword(ctx, dto.KeywordRankRequest{
		Keyword: input.Keyword,
		AppID:   input.AppID,
		Country: input.Country,
		Lang:    input.Lang,
		Limit:   limit,
	})
	now := nowISO(s.cfg.Now)
	if err != nil {
		failureCount, countErr := s.repo.RecordTrackedKeywordFailure(ctx, input, now, err.Error())
		if countErr != nil || failureCount <= 0 {
			failureCount = 1
		}
		alerts, _ := s.createFetchFailureAlert(ctx, input.AppID, fmt.Sprintf("关键词 %s", input.Keyword), input.Country, input.Lang, err.Error(), failureCount, now)
		return dto.SyncTrackedKeywordResponse{Alerts: alerts}, err
	}
	input.Enabled = true
	input.NowISO = now
	if _, err := s.repo.UpsertTrackedKeyword(ctx, input); err != nil {
		return dto.SyncTrackedKeywordResponse{}, err
	}
	priorFailures, err := s.repo.UpdateTrackedKeywordSyncSuccess(ctx, input, now)
	if err != nil && !errors.Is(err, repo.ErrNotFound) {
		return dto.SyncTrackedKeywordResponse{}, err
	}
	alerts, err := s.createFetchRecoveredAlertIfNeeded(ctx, input.AppID, fmt.Sprintf("关键词 %s", input.Keyword), input.Country, input.Lang, priorFailures, now)
	if err != nil {
		return dto.SyncTrackedKeywordResponse{}, err
	}
	return dto.SyncTrackedKeywordResponse{Rank: result, Alerts: alerts}, nil
}

func (s *storeIntelService) AddTrackedChartApp(ctx context.Context, req dto.AddTrackedChartAppRequest) (dto.TrackedChartApp, error) {
	if s == nil || s.repo == nil {
		return dto.TrackedChartApp{}, ErrServiceUnavailable
	}
	input, err := s.trackedChartAppInput(req.AppID, req.Collection, req.Category, req.Country, req.Lang, req.Frequency)
	if err != nil {
		return dto.TrackedChartApp{}, err
	}
	input.Enabled = true
	input.NowISO = nowISO(s.cfg.Now)
	return s.repo.UpsertTrackedChartApp(ctx, input)
}

func (s *storeIntelService) ListTrackedChartApps(ctx context.Context, req dto.ListTrackedChartAppsRequest) (dto.ListTrackedChartAppsResponse, error) {
	if s == nil || s.repo == nil {
		return dto.ListTrackedChartAppsResponse{}, ErrServiceUnavailable
	}
	items, err := s.repo.ListTrackedChartApps(ctx, repo.TrackedMonitorFilter{Enabled: req.Enabled})
	if err != nil {
		return dto.ListTrackedChartAppsResponse{}, err
	}
	return dto.ListTrackedChartAppsResponse{Items: items, Total: len(items)}, nil
}

func (s *storeIntelService) RemoveTrackedChartApp(ctx context.Context, req dto.RemoveTrackedChartAppRequest) (dto.TrackingMutationResponse, error) {
	if s == nil || s.repo == nil {
		return dto.TrackingMutationResponse{}, ErrServiceUnavailable
	}
	input, err := s.trackedChartAppInput(req.AppID, req.Collection, req.Category, req.Country, req.Lang, "")
	if err != nil {
		return dto.TrackingMutationResponse{}, err
	}
	updated, err := s.repo.RemoveTrackedChartApp(ctx, input)
	if err != nil {
		return dto.TrackingMutationResponse{}, err
	}
	return dto.TrackingMutationResponse{Updated: updated}, nil
}

func (s *storeIntelService) SetTrackedChartAppEnabled(ctx context.Context, req dto.SetTrackedChartAppEnabledRequest) (dto.TrackingMutationResponse, error) {
	if s == nil || s.repo == nil {
		return dto.TrackingMutationResponse{}, ErrServiceUnavailable
	}
	input, err := s.trackedChartAppInput(req.AppID, req.Collection, req.Category, req.Country, req.Lang, "")
	if err != nil {
		return dto.TrackingMutationResponse{}, err
	}
	enabled, updated, err := s.repo.SetTrackedChartAppEnabled(ctx, input, req.Enabled, nowISO(s.cfg.Now))
	if err != nil {
		return dto.TrackingMutationResponse{}, err
	}
	return dto.TrackingMutationResponse{Updated: updated, Enabled: boolPtr(enabled)}, nil
}

func (s *storeIntelService) SyncTrackedChartAppNow(ctx context.Context, req dto.SyncTrackedChartAppRequest) (dto.SyncTrackedChartAppResponse, error) {
	if s == nil || s.repo == nil {
		return dto.SyncTrackedChartAppResponse{}, ErrServiceUnavailable
	}
	input, err := s.trackedChartAppInput(req.AppID, req.Collection, req.Category, req.Country, req.Lang, "")
	if err != nil {
		return dto.SyncTrackedChartAppResponse{}, err
	}
	limit := clamp(req.Limit, 1, 200, s.defaultLimit(ctx))
	result, err := s.RankChart(ctx, dto.ChartRankRequest{
		AppID:      input.AppID,
		Collection: input.Collection,
		Category:   input.Category,
		Country:    input.Country,
		Lang:       input.Lang,
		Limit:      limit,
	})
	now := nowISO(s.cfg.Now)
	if err != nil {
		failureCount, countErr := s.repo.RecordTrackedChartAppFailure(ctx, input, now, err.Error())
		if countErr != nil || failureCount <= 0 {
			failureCount = 1
		}
		alerts, _ := s.createFetchFailureAlert(ctx, input.AppID, fmt.Sprintf("榜单 %s/%s", input.Collection, coalesce(input.Category, "-")), input.Country, input.Lang, err.Error(), failureCount, now)
		return dto.SyncTrackedChartAppResponse{Alerts: alerts}, err
	}
	input.Enabled = true
	input.NowISO = now
	if _, err := s.repo.UpsertTrackedChartApp(ctx, input); err != nil {
		return dto.SyncTrackedChartAppResponse{}, err
	}
	priorFailures, err := s.repo.UpdateTrackedChartAppSyncSuccess(ctx, input, now)
	if err != nil && !errors.Is(err, repo.ErrNotFound) {
		return dto.SyncTrackedChartAppResponse{}, err
	}
	alerts, err := s.createFetchRecoveredAlertIfNeeded(ctx, input.AppID, fmt.Sprintf("榜单 %s/%s", input.Collection, coalesce(input.Category, "-")), input.Country, input.Lang, priorFailures, now)
	if err != nil {
		return dto.SyncTrackedChartAppResponse{}, err
	}
	return dto.SyncTrackedChartAppResponse{Rank: result, Alerts: alerts}, nil
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
		failureCount, countErr := s.repo.RecordTrackedAppFailure(ctx, identity, now, err.Error())
		if countErr != nil || failureCount <= 0 {
			failureCount = 1
		}
		alerts, _ := s.createFetchFailureAlert(ctx, identity.AppID, "", identity.Country, identity.Lang, err.Error(), failureCount, now)
		return dto.SyncAppNowResponse{Alerts: alerts}, err
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
	priorFailures, err := s.repo.UpdateTrackedAppSyncSuccess(ctx, identity, now)
	if err != nil && !errors.Is(err, repo.ErrNotFound) {
		return dto.SyncAppNowResponse{}, err
	}
	alerts := buildSnapshotAlerts(upsert.Previous, upsert.Current, upsert.FirstOfDay, now)
	if recovered := s.buildFetchRecoveredAlertIfNeeded(ctx, identity.AppID, detail.Title, identity.Country, identity.Lang, priorFailures, now); recovered != nil {
		alerts = append(alerts, *recovered)
	}
	if len(alerts) > 0 {
		alerts, err = s.createAlerts(ctx, alerts)
		if err != nil {
			return dto.SyncAppNowResponse{}, err
		}
	}
	if upsert.FirstOfDay {
		alerts = append(alerts, s.monitorReviewAlerts(ctx, identity, detail.Title, now)...)
	}
	return dto.SyncAppNowResponse{Detail: detail, Alerts: alerts, FirstSync: upsert.FirstOfDay}, nil
}

func (s *storeIntelService) SyncAll(ctx context.Context, req dto.SyncAllRequest) (dto.SyncAllResponse, error) {
	if s == nil || s.repo == nil {
		return dto.SyncAllResponse{}, ErrServiceUnavailable
	}
	enabled := true
	now := s.cfg.Now()
	tracked, err := s.repo.ListTrackedApps(ctx, repo.TrackedAppFilter{Enabled: &enabled})
	if err != nil {
		return dto.SyncAllResponse{}, err
	}
	var result dto.SyncAllResponse
	for _, item := range tracked {
		if req.DueOnly && !isDue(item, now) {
			continue
		}
		resp, err := s.SyncAppNow(ctx, dto.SyncAppNowRequest{
			AppID:   item.AppID,
			Country: item.Country,
			Lang:    item.Lang,
		})
		if err != nil {
			result.AppsFailed++
			result.Alerts += len(resp.Alerts)
			continue
		}
		result.AppsSynced++
		result.Alerts += len(resp.Alerts)
	}
	keywords, err := s.repo.ListTrackedKeywords(ctx, repo.TrackedMonitorFilter{Enabled: &enabled})
	if err != nil {
		return dto.SyncAllResponse{}, err
	}
	for _, item := range keywords {
		if req.DueOnly && !isDueMonitor(item.LastSyncedAt, item.Frequency, now) {
			continue
		}
		resp, err := s.SyncTrackedKeywordNow(ctx, dto.SyncTrackedKeywordRequest{
			Keyword:  item.Keyword,
			AppID:    item.AppID,
			Country:  item.Country,
			Lang:     item.Lang,
			Platform: item.Platform,
		})
		if err != nil {
			result.KeywordsFailed++
			result.Alerts += len(resp.Alerts)
			continue
		}
		result.KeywordsSynced++
		result.Alerts += len(resp.Alerts)
	}
	charts, err := s.repo.ListTrackedChartApps(ctx, repo.TrackedMonitorFilter{Enabled: &enabled})
	if err != nil {
		return dto.SyncAllResponse{}, err
	}
	for _, item := range charts {
		if req.DueOnly && !isDueMonitor(item.LastSyncedAt, item.Frequency, now) {
			continue
		}
		resp, err := s.SyncTrackedChartAppNow(ctx, dto.SyncTrackedChartAppRequest{
			AppID:      item.AppID,
			Collection: item.Collection,
			Category:   item.Category,
			Country:    item.Country,
			Lang:       item.Lang,
		})
		if err != nil {
			result.ChartsFailed++
			result.Alerts += len(resp.Alerts)
			continue
		}
		result.ChartsSynced++
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

func (s *storeIntelService) CleanupHistory(ctx context.Context) (dto.HistoryRetentionCleanupResponse, error) {
	if s == nil || s.repo == nil {
		return dto.HistoryRetentionCleanupResponse{}, ErrServiceUnavailable
	}
	settings, err := s.GetSettings(ctx)
	if err != nil {
		return dto.HistoryRetentionCleanupResponse{}, err
	}
	if strings.ToLower(strings.TrimSpace(settingValue(settings, "retention_enabled"))) != "true" {
		return dto.HistoryRetentionCleanupResponse{}, nil
	}
	now := s.cfg.Now().UTC()
	minKeep := settingInt(settings, "retention_min_keep")
	snapshotDays := settingInt(settings, "snapshot_retention_days")
	keywordDays := settingInt(settings, "keyword_retention_days")
	alertDays := settingInt(settings, "alert_retention_days")
	reviewDays := settingInt(settings, "review_retention_days")
	return s.repo.CleanupHistory(ctx, repo.HistoryRetentionCleanupInput{
		SnapshotCutoff: retentionCutoff(now, snapshotDays),
		KeywordCutoff:  retentionCutoff(now, keywordDays),
		ChartCutoff:    retentionCutoff(now, keywordDays),
		AlertCutoff:    retentionCutoff(now, alertDays),
		ReviewCutoff:   retentionCutoff(now, reviewDays),
		MinKeep:        minKeep,
	})
}

func (s *storeIntelService) identity(appID, country, lang string) (dto.AppIdentity, error) {
	appID = strings.TrimSpace(appID)
	if appID == "" {
		return dto.AppIdentity{}, fmt.Errorf("%w: app_id is required", ErrInvalidRequest)
	}
	country, lang = s.locale(country, lang)
	return dto.AppIdentity{Platform: dto.PlatformGooglePlay, AppID: appID, Country: country, Lang: lang}, nil
}

func (s *storeIntelService) trackedKeywordInput(keyword, appID, country, lang, platform string) (repo.TrackedKeywordInput, error) {
	keyword = strings.TrimSpace(keyword)
	appID = strings.TrimSpace(appID)
	if keyword == "" || appID == "" {
		return repo.TrackedKeywordInput{}, fmt.Errorf("%w: keyword and app_id are required", ErrInvalidRequest)
	}
	country, lang = s.locale(country, lang)
	return repo.TrackedKeywordInput{
		Platform:  coalesce(platform, dto.PlatformGooglePlay),
		Keyword:   keyword,
		AppID:     appID,
		Country:   country,
		Lang:      lang,
		Frequency: s.cfg.DefaultFrequency,
	}, nil
}

func (s *storeIntelService) trackedChartAppInput(appID, collection, category, country, lang, frequency string) (repo.TrackedChartAppInput, error) {
	appID = strings.TrimSpace(appID)
	if appID == "" {
		return repo.TrackedChartAppInput{}, fmt.Errorf("%w: app_id is required", ErrInvalidRequest)
	}
	country, lang = s.locale(country, lang)
	return repo.TrackedChartAppInput{
		Platform:   dto.PlatformGooglePlay,
		AppID:      appID,
		Collection: normalizeChartType(collection),
		Category:   normalizeChartCategory(category),
		Country:    country,
		Lang:       lang,
		Frequency:  coalesce(frequency, s.cfg.DefaultFrequency),
	}, nil
}

func (s *storeIntelService) coverageCandidates(ctx context.Context, detail dto.AppDetail, appID, country, lang string, maxCandidates int, deep bool) []string {
	builder := newCoverageCandidateBuilder(maxCandidates)
	seeds := coverageSeedTerms(detail, 12)
	for _, seed := range seeds {
		builder.addWithSource(seed, "seed")
	}
	for _, seed := range seeds {
		if builder.len() >= maxCandidates {
			break
		}
		if deep {
			parents := s.coverageSuggest(ctx, seed, country, lang, 6)
			if len(parents) > 0 {
				stop := false
				for _, parent := range parents {
					if !builder.addWithSource(parent, "autocomplete") {
						break
					}
					for _, child := range s.coverageSuggest(ctx, parent, country, lang, 6) {
						if !builder.addWithSource(child, "autocomplete") {
							stop = true
							break
						}
					}
					if stop {
						break
					}
				}
				continue
			}
		}
		for _, hint := range s.coverageSuggest(ctx, seed, country, lang, 8) {
			if !builder.addWithSource(hint, "autocomplete") {
				break
			}
		}
	}
	if builder.len() < maxCandidates {
		seedTokens := coverageSeedTokenSet(seeds)
		for _, keyword := range s.coverageCorpusCandidates(ctx, country, lang, seedTokens, maxCandidates) {
			if !builder.addWithSource(keyword, "corpus") {
				break
			}
		}
	}
	if deep && builder.len() < maxCandidates {
		similar, err := s.SimilarApps(ctx, dto.SimilarAppsRequest{
			AppID:   appID,
			Country: country,
			Lang:    lang,
			Limit:   20,
		})
		if err == nil {
			for _, item := range similar.Items {
				builder.addWithSource(coverageHead(item.Title), "similar")
				tokens := coverageMeaningfulTokens(item.Title)
				for index := 0; index+1 < len(tokens); index++ {
					builder.addWithSource(tokens[index]+" "+tokens[index+1], "similar")
				}
				if builder.len() >= maxCandidates {
					break
				}
			}
		}
	}
	corpusItems := builder.corpusItems()
	if deep {
		corpusItems = append(corpusItems, s.coverageSoupCorpusItems(ctx, seeds, country, lang)...)
	}
	s.recordCoverageCorpus(ctx, country, lang, corpusItems)
	return builder.items
}

func (s *storeIntelService) coverageSuggest(ctx context.Context, term, country, lang string, count int) []string {
	if s == nil || s.upstream == nil || strings.TrimSpace(term) == "" {
		return nil
	}
	hints, err := s.upstream.Suggest(ctx, dto.SuggestRequest{
		Term:    term,
		Country: country,
		Lang:    lang,
		Count:   count,
	})
	if err != nil {
		return nil
	}
	return normalizeCoverageCandidates(hints, count)
}

func (s *storeIntelService) coverageCorpusCandidates(ctx context.Context, country, lang string, seedTokens map[string]struct{}, limit int) []string {
	if s == nil || len(seedTokens) == 0 || limit <= 0 {
		return nil
	}
	keywords := make([]string, 0, limit)
	seen := map[string]struct{}{}
	add := func(keyword string) bool {
		keyword = strings.TrimSpace(keyword)
		if keyword == "" {
			return len(keywords) < limit
		}
		if _, ok := seen[keyword]; ok {
			return len(keywords) < limit
		}
		seen[keyword] = struct{}{}
		keywords = append(keywords, keyword)
		return len(keywords) < limit
	}
	if s.corpus != nil {
		remote, err := s.corpus.Candidates(ctx, KeywordCorpusCandidateRequest{
			Platform:   dto.PlatformGooglePlay,
			Country:    country,
			Lang:       lang,
			SeedTokens: seedTokens,
			Limit:      limit,
		})
		if err == nil {
			for _, keyword := range remote {
				if !add(keyword) {
					return keywords
				}
			}
		}
	}
	if s.repo == nil {
		return keywords
	}
	items, err := s.repo.ListKeywordCorpus(ctx, repo.KeywordCorpusFilter{
		Platform: dto.PlatformGooglePlay,
		Country:  country,
		Lang:     lang,
		Limit:    limit,
	})
	if err != nil {
		return keywords
	}
	for _, item := range items {
		for _, token := range coverageTokens(item.Keyword) {
			if _, ok := seedTokens[token]; ok {
				if !add(item.Keyword) {
					return keywords
				}
				break
			}
		}
	}
	return keywords
}

func (s *storeIntelService) coverageSoupCorpusItems(ctx context.Context, seeds []string, country, lang string) []repo.KeywordCorpusItem {
	items := []repo.KeywordCorpusItem{}
	for index, seed := range seeds {
		if index >= coverageSoupSeeds {
			break
		}
		for _, letter := range coverageSoupLetters {
			for _, hint := range s.coverageSuggest(ctx, seed+" "+string(letter), country, lang, 8) {
				items = append(items, repo.KeywordCorpusItem{
					Keyword: hint,
					Source:  "soup",
				})
			}
		}
	}
	return items
}

func (s *storeIntelService) recordCoverageCorpus(ctx context.Context, country, lang string, items []repo.KeywordCorpusItem) {
	if s == nil || len(items) == 0 {
		return
	}
	if s.repo != nil {
		_, _ = s.repo.RecordKeywordCorpus(ctx, repo.KeywordCorpusRecordInput{
			Platform: dto.PlatformGooglePlay,
			Country:  country,
			Lang:     lang,
			Items:    items,
			SeenAt:   nowISO(s.cfg.Now),
		})
	}
	if s.corpus != nil {
		remoteItems := make([]repo.KeywordCorpusItem, 0, len(items))
		for _, item := range items {
			if item.Confirmed || strings.TrimSpace(item.Source) != "soup" {
				remoteItems = append(remoteItems, item)
			}
		}
		if len(remoteItems) > 0 {
			_ = s.corpus.Contribute(ctx, KeywordCorpusContributeRequest{
				Platform: dto.PlatformGooglePlay,
				Country:  country,
				Lang:     lang,
				Items:    remoteItems,
			})
		}
	}
}

func (s *storeIntelService) defaultLimit(ctx context.Context) int {
	settings, err := s.GetSettings(ctx)
	if err != nil {
		return 100
	}
	return clamp(settingInt(settings, "default_limit"), 1, 200, 100)
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

func (s *storeIntelService) createAlerts(ctx context.Context, alerts []dto.Alert) ([]dto.Alert, error) {
	if len(alerts) == 0 {
		return nil, nil
	}
	if s == nil || s.repo == nil {
		return nil, ErrServiceUnavailable
	}
	created, err := s.repo.CreateAlerts(ctx, alerts)
	if err != nil {
		return nil, err
	}
	if s.publisher != nil {
		_ = s.publisher.PublishAlerts(ctx, created)
	}
	return created, nil
}

func (s *storeIntelService) monitorReviewAlerts(ctx context.Context, identity dto.AppIdentity, title, createdAt string) []dto.Alert {
	if s == nil || s.repo == nil || s.upstream == nil {
		return nil
	}
	settings, err := s.GetSettings(ctx)
	if err != nil {
		settings = dto.DefaultSettings
	}
	if !settingBool(settings, "review_monitor_enabled") {
		return nil
	}
	limit := settingInt(settings, "review_monitor_limit")
	if limit <= 0 {
		return nil
	}
	maxRating := settingInt(settings, "review_alert_max_rating")
	minCount := settingInt(settings, "review_alert_min_count")
	fetched, err := s.FetchReviews(ctx, dto.FetchReviewsRequest{
		AppID:   identity.AppID,
		Country: identity.Country,
		Lang:    identity.Lang,
		Sort:    "newest",
		Limit:   limit,
	})
	if err != nil {
		return nil
	}
	items := fetched.Items
	if len(items) > limit {
		items = items[:limit]
	}
	if len(items) == 0 {
		return nil
	}
	reviewIDs := make([]string, 0, len(items))
	for _, item := range items {
		if strings.TrimSpace(item.ReviewID) != "" {
			reviewIDs = append(reviewIDs, item.ReviewID)
		}
	}
	existing, err := s.repo.ExistingReviewIDs(ctx, repo.ExistingReviewsFilter{
		Identity:  identity,
		ReviewIDs: reviewIDs,
	})
	if err != nil {
		return nil
	}
	if _, err := s.repo.SaveReviews(ctx, repo.SaveReviewsInput{
		Identity:   identity,
		Items:      items,
		CapturedAt: createdAt,
	}); err != nil {
		return nil
	}
	newNegative := make([]dto.ReviewItem, 0, len(items))
	for _, item := range items {
		if item.ReviewID != "" && existing[item.ReviewID] {
			continue
		}
		if item.Rating != nil && *item.Rating <= maxRating {
			newNegative = append(newNegative, item)
		}
	}
	alert := buildReviewNegativeSpikeAlert(identity.AppID, title, newNegative, minCount, createdAt)
	if alert == nil {
		return nil
	}
	created, err := s.createAlerts(ctx, []dto.Alert{*alert})
	if err != nil {
		return nil
	}
	return created
}

func buildReviewNegativeSpikeAlert(appID, title string, newNegativeReviews []dto.ReviewItem, minCount int, createdAt string) *dto.Alert {
	count := len(newNegativeReviews)
	if count < minCount {
		return nil
	}
	name := coalesce(title, appID)
	sample := ""
	if count > 0 {
		sample = strings.TrimSpace(strings.ReplaceAll(newNegativeReviews[0].Content, "\n", " "))
		if runes := []rune(sample); len(runes) > 40 {
			sample = string(runes[:40]) + "…"
		}
	}
	message := fmt.Sprintf("%s 新增 %d 条差评", name, count)
	if sample != "" {
		message += fmt.Sprintf("，例：「%s」", sample)
	}
	return &dto.Alert{
		Type:      "review_negative_spike",
		Severity:  "high",
		AppID:     appID,
		Title:     title,
		Message:   message,
		Payload:   map[string]any{"current": count},
		CreatedAt: createdAt,
	}
}

func (s *storeIntelService) createFetchFailureAlert(ctx context.Context, appID, title, country, lang, message string, failureCount int, createdAt string) ([]dto.Alert, error) {
	if failureCount <= 0 {
		failureCount = 1
	}
	name := coalesce(title, appID)
	alertType := "fetch_failed"
	severity := "medium"
	fullMessage := fmt.Sprintf("%s 获取失败：%s", name, message)
	escalateAfter := s.fetchEscalateAfter(ctx)
	if failureCount >= escalateAfter {
		alertType = "fetch_failed_persistent"
		if failureCount == escalateAfter {
			severity = "high"
		}
		fullMessage = fmt.Sprintf("%s 已连续 %d 次抓取失败：%s", name, failureCount, message)
	}
	return s.createAlerts(ctx, []dto.Alert{{
		Type:      alertType,
		Severity:  severity,
		AppID:     appID,
		Title:     title,
		Message:   fullMessage,
		Payload:   map[string]any{"country": country, "lang": lang, "error": message, "failure_count": failureCount},
		CreatedAt: createdAt,
	}})
}

func (s *storeIntelService) createFetchRecoveredAlertIfNeeded(ctx context.Context, appID, title, country, lang string, priorFailures int, createdAt string) ([]dto.Alert, error) {
	alert := s.buildFetchRecoveredAlertIfNeeded(ctx, appID, title, country, lang, priorFailures, createdAt)
	if alert == nil {
		return nil, nil
	}
	return s.createAlerts(ctx, []dto.Alert{*alert})
}

func (s *storeIntelService) buildFetchRecoveredAlertIfNeeded(ctx context.Context, appID, title, country, lang string, priorFailures int, createdAt string) *dto.Alert {
	if priorFailures < s.fetchEscalateAfter(ctx) {
		return nil
	}
	name := coalesce(title, appID)
	alert := dto.Alert{
		Type:      "fetch_recovered",
		Severity:  "medium",
		AppID:     appID,
		Title:     title,
		Message:   fmt.Sprintf("%s 抓取已恢复（此前连续失败 %d 次）", name, priorFailures),
		Payload:   map[string]any{"country": country, "lang": lang, "previous": priorFailures},
		CreatedAt: createdAt,
	}
	return &alert
}

func (s *storeIntelService) fetchEscalateAfter(ctx context.Context) int {
	settings, err := s.GetSettings(ctx)
	if err != nil {
		settings = dto.DefaultSettings
	}
	return settingInt(settings, "alert_fetch_escalate_after")
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
	return isDueMonitor(item.LastSyncedAt, item.Frequency, now)
}

func isDueMonitor(lastSyncedAt, frequency string, now time.Time) bool {
	if strings.TrimSpace(lastSyncedAt) == "" {
		return true
	}
	last, err := time.Parse(time.RFC3339, lastSyncedAt)
	if err != nil {
		return true
	}
	switch strings.ToLower(strings.TrimSpace(frequency)) {
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

func dateKey(iso string) string {
	if len(iso) >= 10 {
		return iso[:10]
	}
	return iso
}

func retentionCutoff(now time.Time, days int) string {
	return now.AddDate(0, 0, -days).UTC().Format(time.RFC3339)
}

func settingValue(settings map[string]string, key string) string {
	if value, ok := settings[key]; ok {
		return value
	}
	return dto.DefaultSettings[key]
}

func settingInt(settings map[string]string, key string) int {
	fallback, _ := strconv.Atoi(dto.DefaultSettings[key])
	value := strings.TrimSpace(settingValue(settings, key))
	parsed, err := strconv.ParseFloat(value, 64)
	if err != nil {
		return fallback
	}
	return int(parsed)
}

func parseCoverageProxies(text string) []string {
	proxies := []string{}
	seen := map[string]struct{}{}
	for _, line := range strings.Split(text, "\n") {
		line = strings.SplitN(line, "#", 2)[0]
		for _, token := range strings.FieldsFunc(line, func(r rune) bool {
			return r == ',' || r == ' ' || r == '\t' || r == '\r' || r == '\n'
		}) {
			proxy := strings.TrimSpace(token)
			if proxy == "" {
				continue
			}
			if !strings.Contains(proxy, "://") {
				proxy = "http://" + proxy
			}
			if _, ok := seen[proxy]; ok {
				continue
			}
			seen[proxy] = struct{}{}
			proxies = append(proxies, proxy)
		}
	}
	return proxies
}

func settingBool(settings map[string]string, key string) bool {
	return strings.ToLower(strings.TrimSpace(settingValue(settings, key))) == "true"
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

func coalesceFloat(values ...*float64) *float64 {
	for _, value := range values {
		if value != nil {
			return value
		}
	}
	return nil
}

func coalesceInt64(values ...*int64) *int64 {
	for _, value := range values {
		if value != nil {
			return value
		}
	}
	return nil
}

func googlePlayStoreURL(appID, country, lang string) string {
	appID = strings.TrimSpace(appID)
	if appID == "" {
		return ""
	}
	values := url.Values{}
	values.Set("id", appID)
	values.Set("gl", strings.ToLower(coalesce(country, "us")))
	values.Set("hl", strings.ToLower(coalesce(lang, "en")))
	return "https://play.google.com/store/apps/details?" + values.Encode()
}

func normalizeReviewSort(value string) string {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "rating", "helpfulness", "most_relevant":
		return strings.ToLower(strings.TrimSpace(value))
	default:
		return "newest"
	}
}

func normalizeChartType(value string) string {
	value = strings.ToLower(strings.TrimSpace(value))
	switch value {
	case "top_paid", "top_grossing":
		return value
	default:
		return "top_free"
	}
}

func normalizeChartCategory(value string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return "APPLICATION"
	}
	return value
}

func sameAppID(left, right string) bool {
	return strings.EqualFold(strings.TrimSpace(left), strings.TrimSpace(right))
}

func copySettings(values map[string]string) map[string]string {
	copied := make(map[string]string, len(values))
	for key, value := range values {
		copied[key] = value
	}
	return copied
}

func boolPtr(value bool) *bool {
	return &value
}

var (
	coverageSplitRE = regexp.MustCompile(`[:\-–—|·,，、（(]`)
	coverageTokenRE = regexp.MustCompile(`[A-Za-z0-9]+`)
	coverageSpaceRE = regexp.MustCompile(`\s+`)
)

const (
	coverageMaxProxyAttempts = 3
	coverageProxyMaxFailures = 2
	coverageProxyCooldown    = 120 * time.Second
	coverageSoupSeeds        = 2
	coverageSoupLetters      = "abcdefghijklmnopqrstuvwxyz"
)

var coverageStopwords = map[string]struct{}{
	"the": {}, "a": {}, "an": {}, "and": {}, "or": {}, "of": {}, "to": {}, "for": {},
	"in": {}, "on": {}, "with": {}, "your": {}, "you": {}, "app": {}, "apps": {},
	"free": {}, "best": {}, "new": {}, "get": {}, "all": {}, "this": {}, "that": {},
	"it": {}, "is": {}, "are": {}, "be": {}, "by": {}, "from": {}, "at": {}, "as": {},
	"can": {}, "will": {}, "now": {}, "more": {}, "my": {}, "our": {}, "we": {},
	"us": {}, "android": {}, "google": {}, "play": {}, "store": {}, "mobile": {},
	"phone": {}, "com": {}, "ios": {}, "iphone": {}, "ipad": {}, "apple": {},
}

type coverageProxyPool struct {
	mu          sync.Mutex
	entries     []coverageProxyEntry
	cursor      int
	maxFailures int
	cooldown    time.Duration
	now         func() time.Time
}

type coverageProxyEntry struct {
	url      string
	failures int
	until    time.Time
}

func newCoverageProxyPool(proxies []string) *coverageProxyPool {
	entries := make([]coverageProxyEntry, 0, len(proxies))
	seen := map[string]struct{}{}
	for _, proxy := range proxies {
		proxy = strings.TrimSpace(proxy)
		if proxy == "" {
			continue
		}
		if _, ok := seen[proxy]; ok {
			continue
		}
		seen[proxy] = struct{}{}
		entries = append(entries, coverageProxyEntry{url: proxy})
	}
	return &coverageProxyPool{
		entries:     entries,
		maxFailures: coverageProxyMaxFailures,
		cooldown:    coverageProxyCooldown,
		now:         time.Now,
	}
}

func (p *coverageProxyPool) len() int {
	if p == nil {
		return 0
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	return len(p.entries)
}

func (p *coverageProxyPool) hasProxies() bool {
	return p != nil && p.len() > 0
}

func (p *coverageProxyPool) lease() string {
	if p == nil {
		return ""
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	count := len(p.entries)
	if count == 0 {
		return ""
	}
	now := p.now()
	for i := 0; i < count; i++ {
		entry := &p.entries[p.cursor]
		p.cursor = (p.cursor + 1) % count
		if !entry.until.After(now) {
			return entry.url
		}
	}
	return ""
}

func (p *coverageProxyPool) reportOK(proxy string) {
	if p == nil || strings.TrimSpace(proxy) == "" {
		return
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	if entry := p.find(proxy); entry != nil {
		entry.failures = 0
		entry.until = time.Time{}
	}
}

func (p *coverageProxyPool) reportBad(proxy string) {
	if p == nil || strings.TrimSpace(proxy) == "" {
		return
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	entry := p.find(proxy)
	if entry == nil {
		return
	}
	entry.failures++
	if entry.failures >= p.maxFailures {
		entry.until = p.now().Add(p.cooldown)
		entry.failures = 0
	}
}

func (p *coverageProxyPool) find(proxy string) *coverageProxyEntry {
	for index := range p.entries {
		if p.entries[index].url == proxy {
			return &p.entries[index]
		}
	}
	return nil
}

type coverageCandidateBuilder struct {
	items   []string
	seen    map[string]struct{}
	sources map[string]string
	limit   int
}

func newCoverageCandidateBuilder(limit int) *coverageCandidateBuilder {
	return &coverageCandidateBuilder{
		items:   make([]string, 0, limit),
		seen:    map[string]struct{}{},
		sources: map[string]string{},
		limit:   limit,
	}
}

func (b *coverageCandidateBuilder) add(term string) bool {
	return b.addWithSource(term, "")
}

func (b *coverageCandidateBuilder) addWithSource(term, source string) bool {
	term = normalizeCoverageTerm(term)
	if term == "" || len([]rune(term)) < 2 || len([]rune(term)) > 50 {
		return b.len() < b.limit
	}
	if _, ok := b.seen[term]; ok {
		return b.len() < b.limit
	}
	b.seen[term] = struct{}{}
	b.items = append(b.items, term)
	if strings.TrimSpace(source) != "" {
		b.sources[term] = strings.TrimSpace(source)
	}
	return b.len() < b.limit
}

func (b *coverageCandidateBuilder) len() int {
	return len(b.items)
}

func (b *coverageCandidateBuilder) corpusItems() []repo.KeywordCorpusItem {
	items := make([]repo.KeywordCorpusItem, 0, len(b.items))
	for _, keyword := range b.items {
		source := b.sources[keyword]
		if source == "" {
			source = "seed"
		}
		items = append(items, repo.KeywordCorpusItem{
			Keyword: keyword,
			Source:  source,
		})
	}
	return items
}

func normalizeCoverageCandidates(values []string, limit int) []string {
	builder := newCoverageCandidateBuilder(limit)
	for _, value := range values {
		if !builder.add(value) {
			break
		}
	}
	return builder.items
}

func coverageSeedTokenSet(seeds []string) map[string]struct{} {
	tokens := map[string]struct{}{}
	for _, seed := range seeds {
		for _, token := range strings.Fields(seed) {
			if token != "" {
				tokens[token] = struct{}{}
			}
		}
	}
	return tokens
}

func coverageSeedTerms(detail dto.AppDetail, maxSeeds int) []string {
	builder := newCoverageCandidateBuilder(maxSeeds)
	builder.add(coverageHead(detail.Title))
	titleTokens := coverageMeaningfulTokens(detail.Title)
	for index := 0; index+1 < len(titleTokens); index++ {
		builder.add(titleTokens[index] + " " + titleTokens[index+1])
	}
	for _, token := range titleTokens {
		builder.add(token)
	}
	builder.add(detail.Category)
	text := strings.TrimSpace(detail.Summary + " " + firstRunes(detail.Description, 600))
	frequencies := map[string]int{}
	for _, token := range coverageTokens(text) {
		if _, stop := coverageStopwords[token]; stop || len(token) < 4 || isDigits(token) {
			continue
		}
		frequencies[token]++
	}
	words := make([]string, 0, len(frequencies))
	for word := range frequencies {
		words = append(words, word)
	}
	sort.Slice(words, func(i, j int) bool {
		if frequencies[words[i]] == frequencies[words[j]] {
			return words[i] < words[j]
		}
		return frequencies[words[i]] > frequencies[words[j]]
	})
	for _, word := range words {
		if !builder.add(word) {
			break
		}
	}
	return builder.items
}

func coverageMeaningfulTokens(text string) []string {
	tokens := coverageTokens(text)
	out := make([]string, 0, len(tokens))
	for _, token := range tokens {
		if _, stop := coverageStopwords[token]; !stop {
			out = append(out, token)
		}
	}
	return out
}

func coverageTokens(text string) []string {
	matches := coverageTokenRE.FindAllString(text, -1)
	out := make([]string, 0, len(matches))
	for _, match := range matches {
		out = append(out, strings.ToLower(match))
	}
	return out
}

func coverageHead(text string) string {
	parts := coverageSplitRE.Split(text, 2)
	if len(parts) == 0 {
		return ""
	}
	return strings.TrimSpace(parts[0])
}

func normalizeCoverageTerm(term string) string {
	return coverageSpaceRE.ReplaceAllString(strings.ToLower(strings.TrimSpace(term)), " ")
}

func firstRunes(text string, limit int) string {
	if limit <= 0 {
		return ""
	}
	runes := []rune(text)
	if len(runes) <= limit {
		return text
	}
	return string(runes[:limit])
}

func isDigits(value string) bool {
	if value == "" {
		return false
	}
	for _, ch := range value {
		if ch < '0' || ch > '9' {
			return false
		}
	}
	return true
}

func coverageTargets(appID, canonical string) []string {
	values := []string{strings.TrimSpace(appID), strings.TrimSpace(canonical)}
	targets := make([]string, 0, len(values))
	seen := map[string]struct{}{}
	for _, value := range values {
		if value == "" {
			continue
		}
		key := strings.ToLower(value)
		if _, ok := seen[key]; ok {
			continue
		}
		seen[key] = struct{}{}
		targets = append(targets, value)
	}
	return targets
}

func coverageRank(items []dto.AppSummary, targets []string) int {
	for index, item := range items {
		for _, target := range targets {
			if sameAppID(item.AppID, target) {
				return index + 1
			}
		}
	}
	return 0
}
