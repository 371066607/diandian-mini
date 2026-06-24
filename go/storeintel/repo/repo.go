package repo

import (
	"context"
	"errors"
	"sort"
	"strings"

	"github.com/catch-radar/storeintel/dto"
)

var ErrNotFound = errors.New("storeintel repo not found")

type TrackedAppInput struct {
	Identity  dto.AppIdentity
	Title     string
	Frequency string
	Tag       string
	Enabled   bool
	NowISO    string
}

type TrackedKeywordInput struct {
	Platform  string
	Keyword   string
	AppID     string
	Country   string
	Lang      string
	Frequency string
	Enabled   bool
	NowISO    string
}

type TrackedChartAppInput struct {
	Platform   string
	AppID      string
	Collection string
	Category   string
	Country    string
	Lang       string
	Frequency  string
	Enabled    bool
	NowISO     string
}

type TrackedAppFilter struct {
	Enabled *bool
}

type TrackedMonitorFilter struct {
	Enabled *bool
}

type SnapshotUpsertInput struct {
	Detail     dto.AppDetail
	Country    string
	Lang       string
	CapturedAt string
}

type SnapshotRecord struct {
	Identity     dto.AppIdentity
	CapturedAt   string
	Title        string
	Rating       *float64
	RatingsCount *int64
	ReviewsCount *int64
	Installs     string
	MinInstalls  *int64
	RealInstalls *int64
	Version      string
	Raw          dto.AppDetail
}

func (s SnapshotRecord) DTO() dto.AppSnapshot {
	return dto.AppSnapshot{
		Platform:     s.Identity.Platform,
		AppID:        s.Identity.AppID,
		Country:      s.Identity.Country,
		Lang:         s.Identity.Lang,
		CapturedAt:   s.CapturedAt,
		Title:        s.Title,
		Rating:       s.Rating,
		RatingsCount: s.RatingsCount,
		ReviewsCount: s.ReviewsCount,
		Installs:     s.Installs,
		MinInstalls:  s.MinInstalls,
		RealInstalls: s.RealInstalls,
		Version:      s.Version,
	}
}

type SnapshotUpsertResult struct {
	Previous   *SnapshotRecord
	Current    SnapshotRecord
	FirstOfDay bool
}

type AppSnapshotHistoryFilter struct {
	Platform string
	AppID    string
	Country  string
	Lang     string
	Limit    int
}

type AppSnapshotRecentFilter struct {
	Limit int
}

type CachedAppSearchFilter struct {
	Platform string
	Query    string
	Country  string
	Lang     string
	Limit    int
}

type CachedAppsUpsertInput struct {
	Platform  string
	Country   string
	Lang      string
	Items     []dto.AppSummary
	UpdatedAt string
}

type LatestAppSnapshotFilter struct {
	Platform string
	AppID    string
	Country  string
	Lang     string
}

type SaveChartSnapshotInput struct {
	ChartType  string
	Category   string
	Country    string
	Lang       string
	Items      []dto.ChartItem
	CapturedAt string
}

type LatestChartSnapshotFilter struct {
	Platform  string
	ChartType string
	Category  string
	Country   string
	Lang      string
	Limit     int
}

type ChartRankUpsertInput struct {
	Result      dto.ChartRankResponse
	CapturedAt  string
	CapturedDay string
}

type ChartRankHistoryFilter struct {
	Platform   string
	AppID      string
	Collection string
	Category   string
	Country    string
	Lang       string
	Limit      int
}

type KeywordRankUpsertInput struct {
	Result      dto.KeywordRankResponse
	CapturedAt  string
	CapturedDay string
}

type KeywordRankUpsertResult struct {
	Current    dto.KeywordRankSnapshot
	FirstOfDay bool
}

type KeywordRankHistoryFilter struct {
	Platform string
	Keyword  string
	AppID    string
	Country  string
	Lang     string
	Limit    int
}

type KeywordRankRecentFilter struct {
	Platform string
	AppID    string
	Country  string
	Lang     string
	Limit    int
}

type KeywordCorpusItem struct {
	Platform    string
	Country     string
	Lang        string
	Keyword     string
	Source      string
	Confirmed   bool
	HitCount    int
	FirstSeenAt string
	LastSeenAt  string
}

type KeywordCorpusRecordInput struct {
	Platform string
	Country  string
	Lang     string
	Items    []KeywordCorpusItem
	SeenAt   string
}

type KeywordCorpusFilter struct {
	Platform string
	Country  string
	Lang     string
	Limit    int
}

type KeywordCoverageUpsertInput struct {
	Result     dto.KeywordCoverageResponse
	CapturedAt string
}

type KeywordCoverageLatestFilter struct {
	Platform string
	AppID    string
	Country  string
	Lang     string
	Deep     bool
}

type SaveReviewsInput struct {
	Identity   dto.AppIdentity
	Items      []dto.ReviewItem
	CapturedAt string
}

type ListReviewsFilter struct {
	AppID string
	Limit int
}

type ExistingReviewsFilter struct {
	Identity  dto.AppIdentity
	ReviewIDs []string
}

type AlertFilter struct {
	AppID    string
	Type     string
	Severity string
	IsRead   *bool
	Limit    int
}

type HistoryRetentionCleanupInput struct {
	SnapshotCutoff string
	KeywordCutoff  string
	ChartCutoff    string
	AlertCutoff    string
	ReviewCutoff   string
	MinKeep        int
}

type RefreshJobCreateInput struct {
	Job     dto.RefreshJobResponse
	Request dto.RefreshJobRequest
}

type RefreshJobUpdateInput struct {
	JobID      string
	Status     string
	Message    string
	StartedAt  string
	FinishedAt string
	UpdatedAt  string
}

type RefreshJobListFilter struct {
	Statuses []string
	Limit    int
}

type RefreshJobClaimInput struct {
	JobID       string
	WorkerID    string
	StartedAt   string
	UpdatedAt   string
	LockedUntil string
}

type StoreIntelRepo interface {
	ListSettings(ctx context.Context) (map[string]string, error)
	UpsertSettings(ctx context.Context, values map[string]string, updatedAt string) error
	AcquireSettingValue(ctx context.Context, key, value, updatedAt string) (bool, error)
	CreateRefreshJob(ctx context.Context, input RefreshJobCreateInput) (dto.RefreshJobResponse, error)
	UpdateRefreshJob(ctx context.Context, input RefreshJobUpdateInput) (dto.RefreshJobResponse, error)
	GetRefreshJob(ctx context.Context, jobID string) (dto.RefreshJobResponse, error)
	ListRefreshJobs(ctx context.Context, filter RefreshJobListFilter) ([]dto.RefreshJobRecord, error)
	ClaimRefreshJob(ctx context.Context, input RefreshJobClaimInput) (dto.RefreshJobResponse, bool, error)
	UpsertTrackedApp(ctx context.Context, input TrackedAppInput) (dto.TrackedApp, error)
	ListTrackedApps(ctx context.Context, filter TrackedAppFilter) ([]dto.TrackedApp, error)
	RemoveTrackedApp(ctx context.Context, identity dto.AppIdentity) (int, error)
	SetTrackedAppEnabled(ctx context.Context, identity dto.AppIdentity, enabled bool, updatedAt string) (bool, int, error)
	SetTrackedAppFrequency(ctx context.Context, identity dto.AppIdentity, frequency, updatedAt string) (string, int, error)
	SetTrackedAppTag(ctx context.Context, identity dto.AppIdentity, tag, updatedAt string) (string, int, error)
	UpdateTrackedAppSyncSuccess(ctx context.Context, identity dto.AppIdentity, syncedAt string) (int, error)
	RecordTrackedAppFailure(ctx context.Context, identity dto.AppIdentity, failedAt, message string) (int, error)
	UpsertCachedApps(ctx context.Context, input CachedAppsUpsertInput) (int, error)
	SearchCachedApps(ctx context.Context, filter CachedAppSearchFilter) ([]dto.AppSummary, error)
	UpsertTrackedKeyword(ctx context.Context, input TrackedKeywordInput) (dto.TrackedKeyword, error)
	ListTrackedKeywords(ctx context.Context, filter TrackedMonitorFilter) ([]dto.TrackedKeyword, error)
	RemoveTrackedKeyword(ctx context.Context, input TrackedKeywordInput) (int, error)
	SetTrackedKeywordEnabled(ctx context.Context, input TrackedKeywordInput, enabled bool, updatedAt string) (bool, int, error)
	SetTrackedKeywordFrequency(ctx context.Context, input TrackedKeywordInput, frequency, updatedAt string) (string, int, error)
	UpdateTrackedKeywordSyncSuccess(ctx context.Context, input TrackedKeywordInput, syncedAt string) (int, error)
	RecordTrackedKeywordFailure(ctx context.Context, input TrackedKeywordInput, failedAt, message string) (int, error)
	UpsertTrackedChartApp(ctx context.Context, input TrackedChartAppInput) (dto.TrackedChartApp, error)
	ListTrackedChartApps(ctx context.Context, filter TrackedMonitorFilter) ([]dto.TrackedChartApp, error)
	RemoveTrackedChartApp(ctx context.Context, input TrackedChartAppInput) (int, error)
	SetTrackedChartAppEnabled(ctx context.Context, input TrackedChartAppInput, enabled bool, updatedAt string) (bool, int, error)
	UpdateTrackedChartAppSyncSuccess(ctx context.Context, input TrackedChartAppInput, syncedAt string) (int, error)
	RecordTrackedChartAppFailure(ctx context.Context, input TrackedChartAppInput, failedAt, message string) (int, error)
	UpsertAppSnapshot(ctx context.Context, input SnapshotUpsertInput) (SnapshotUpsertResult, error)
	LatestAppSnapshot(ctx context.Context, filter LatestAppSnapshotFilter) (SnapshotRecord, error)
	ListAppSnapshotHistory(ctx context.Context, filter AppSnapshotHistoryFilter) ([]dto.AppSnapshot, error)
	ListRecentAppSnapshots(ctx context.Context, filter AppSnapshotRecentFilter) ([]dto.AppSnapshot, error)
	CountAppSnapshots(ctx context.Context) (int, error)
	SaveChartSnapshot(ctx context.Context, input SaveChartSnapshotInput) (int, error)
	ListLatestChartSnapshot(ctx context.Context, filter LatestChartSnapshotFilter) ([]dto.ChartItem, string, error)
	UpsertChartRank(ctx context.Context, input ChartRankUpsertInput) (dto.ChartRankResponse, bool, error)
	ListChartRankHistory(ctx context.Context, filter ChartRankHistoryFilter) ([]dto.ChartRankResponse, error)
	UpsertKeywordRank(ctx context.Context, input KeywordRankUpsertInput) (KeywordRankUpsertResult, error)
	ListKeywordRankHistory(ctx context.Context, filter KeywordRankHistoryFilter) ([]dto.KeywordRankSnapshot, error)
	ListRecentKeywordRanks(ctx context.Context, filter KeywordRankRecentFilter) ([]dto.KeywordRankSnapshot, error)
	RecordKeywordCorpus(ctx context.Context, input KeywordCorpusRecordInput) (int, error)
	ListKeywordCorpus(ctx context.Context, filter KeywordCorpusFilter) ([]KeywordCorpusItem, error)
	UpsertKeywordCoverage(ctx context.Context, input KeywordCoverageUpsertInput) error
	LatestKeywordCoverage(ctx context.Context, filter KeywordCoverageLatestFilter) (dto.KeywordCoverageResponse, error)
	ExistingReviewIDs(ctx context.Context, filter ExistingReviewsFilter) (map[string]bool, error)
	SaveReviews(ctx context.Context, input SaveReviewsInput) (int, error)
	ListReviews(ctx context.Context, filter ListReviewsFilter) ([]dto.ReviewItem, error)
	CreateAlerts(ctx context.Context, alerts []dto.Alert) ([]dto.Alert, error)
	ListAlerts(ctx context.Context, filter AlertFilter) ([]dto.Alert, error)
	MarkAlertsRead(ctx context.Context, ids []uint64) (int, error)
	CleanupHistory(ctx context.Context, input HistoryRetentionCleanupInput) (dto.HistoryRetentionCleanupResponse, error)
}

func normalizeKeywordCorpusRecordInput(input KeywordCorpusRecordInput) KeywordCorpusRecordInput {
	input.Platform = defaultString(input.Platform, dto.PlatformGooglePlay)
	input.Country = strings.ToLower(defaultString(input.Country, "us"))
	input.Lang = strings.ToLower(defaultString(input.Lang, "en"))
	input.SeenAt = strings.TrimSpace(input.SeenAt)

	byKeyword := map[string]KeywordCorpusItem{}
	for _, item := range input.Items {
		keyword := strings.TrimSpace(item.Keyword)
		if keyword == "" {
			continue
		}
		prior, ok := byKeyword[keyword]
		if !ok {
			item.Platform = input.Platform
			item.Country = input.Country
			item.Lang = input.Lang
			item.Keyword = keyword
			item.Source = strings.TrimSpace(item.Source)
			item.FirstSeenAt = defaultString(item.FirstSeenAt, input.SeenAt)
			item.LastSeenAt = defaultString(item.LastSeenAt, input.SeenAt)
			if item.HitCount <= 0 {
				item.HitCount = 1
			}
			byKeyword[keyword] = item
			continue
		}
		prior.Confirmed = prior.Confirmed || item.Confirmed
		if prior.Source == "" {
			prior.Source = strings.TrimSpace(item.Source)
		}
		byKeyword[keyword] = prior
	}
	keywords := make([]string, 0, len(byKeyword))
	for keyword := range byKeyword {
		keywords = append(keywords, keyword)
	}
	sort.Strings(keywords)
	input.Items = make([]KeywordCorpusItem, 0, len(keywords))
	for _, keyword := range keywords {
		input.Items = append(input.Items, byKeyword[keyword])
	}
	return input
}

func normalizeKeywordCorpusFilter(filter KeywordCorpusFilter) KeywordCorpusFilter {
	filter.Platform = defaultString(filter.Platform, dto.PlatformGooglePlay)
	filter.Country = strings.ToLower(defaultString(filter.Country, "us"))
	filter.Lang = strings.ToLower(defaultString(filter.Lang, "en"))
	if filter.Limit <= 0 {
		filter.Limit = 5000
	}
	return filter
}

func defaultString(value, fallback string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return fallback
	}
	return value
}
