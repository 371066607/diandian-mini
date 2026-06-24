package dto

const PlatformGooglePlay = "google_play"

var DefaultSettings = map[string]string{
	"default_country":                     "us",
	"default_lang":                        "en",
	"default_limit":                       "50",
	"scheduler_enabled":                   "true",
	"daily_sync_time":                     "09:00",
	"request_delay_seconds":               "1",
	"database_path":                       "./data/catch_radar.sqlite3",
	"proxy":                               "",
	"theme":                               "slate",
	"coverage_proxies":                    "",
	"coverage_concurrency":                "6",
	"alert_rating_drop":                   "0.2",
	"alert_growth_percent":                "10",
	"alert_keyword_top_band":              "10",
	"alert_keyword_move":                  "5",
	"alert_negative_review_surge_percent": "20",
	"alert_positive_ratio_drop":           "5",
	"desktop_notifications":               "true",
	"notify_min_severity":                 "high",
	"alert_fetch_escalate_after":          "3",
	"retention_enabled":                   "true",
	"snapshot_retention_days":             "180",
	"keyword_retention_days":              "180",
	"alert_retention_days":                "365",
	"review_retention_days":               "180",
	"retention_min_keep":                  "30",
	"review_monitor_enabled":              "true",
	"review_monitor_limit":                "50",
	"review_alert_max_rating":             "2",
	"review_alert_min_count":              "3",
}

type RequestContext struct {
	RequestID string `json:"request_id,omitempty"`
	TraceID   string `json:"trace_id,omitempty"`
	AppID     string `json:"app_id,omitempty"`
	Platform  string `json:"platform,omitempty"`
	UserID    int64  `json:"user_id,omitempty"`
	DeviceID  string `json:"device_id,omitempty"`
	CallerID  string `json:"caller_id,omitempty"`
	AuthType  string `json:"auth_type,omitempty"`
}

type AppIdentity struct {
	Platform string `json:"platform"`
	AppID    string `json:"app_id"`
	Country  string `json:"country"`
	Lang     string `json:"lang"`
}

type AppSummary struct {
	Platform     string         `json:"platform"`
	AppID        string         `json:"app_id"`
	Title        string         `json:"title,omitempty"`
	Developer    string         `json:"developer,omitempty"`
	DeveloperID  string         `json:"developer_id,omitempty"`
	Category     string         `json:"category,omitempty"`
	Summary      string         `json:"summary,omitempty"`
	Rating       *float64       `json:"rating,omitempty"`
	ScoreText    string         `json:"score_text,omitempty"`
	RatingsCount *int64         `json:"ratings_count,omitempty"`
	ReviewsCount *int64         `json:"reviews_count,omitempty"`
	Installs     string         `json:"installs,omitempty"`
	MinInstalls  *int64         `json:"min_installs,omitempty"`
	Price        string         `json:"price,omitempty"`
	Currency     string         `json:"currency,omitempty"`
	Free         *bool          `json:"free,omitempty"`
	HasIAP       *bool          `json:"has_iap,omitempty"`
	IconURL      string         `json:"icon_url,omitempty"`
	StoreURL     string         `json:"store_url,omitempty"`
	Raw          map[string]any `json:"raw,omitempty"`
}

type AppDetail struct {
	AppSummary
	Version                  string         `json:"version,omitempty"`
	Updated                  string         `json:"updated,omitempty"`
	Released                 string         `json:"released,omitempty"`
	AndroidVersion           string         `json:"android_version,omitempty"`
	ContentRating            string         `json:"content_rating,omitempty"`
	Description              string         `json:"description,omitempty"`
	Changelog                string         `json:"changelog,omitempty"`
	Screenshots              []string       `json:"screenshots,omitempty"`
	RealInstalls             *int64         `json:"real_installs,omitempty"`
	Histogram                []int64        `json:"histogram,omitempty"`
	ContainsAds              *bool          `json:"contains_ads,omitempty"`
	IAPPriceRange            string         `json:"iap_price_range,omitempty"`
	DeveloperEmail           string         `json:"developer_email,omitempty"`
	DeveloperWebsite         string         `json:"developer_website,omitempty"`
	PrivacyPolicy            string         `json:"privacy_policy,omitempty"`
	HeaderImage              string         `json:"header_image,omitempty"`
	GenreID                  string         `json:"genre_id,omitempty"`
	Categories               []string       `json:"categories,omitempty"`
	Available                *bool          `json:"available,omitempty"`
	AppAgeDays               *int64         `json:"app_age_days,omitempty"`
	Video                    string         `json:"video,omitempty"`
	VideoImage               string         `json:"video_image,omitempty"`
	DailyInstalls            *int64         `json:"daily_installs,omitempty"`
	MinDailyInstalls         *int64         `json:"min_daily_installs,omitempty"`
	RealDailyInstalls        *int64         `json:"real_daily_installs,omitempty"`
	MonthlyInstalls          *int64         `json:"monthly_installs,omitempty"`
	MinMonthlyInstalls       *int64         `json:"min_monthly_installs,omitempty"`
	RealMonthlyInstalls      *int64         `json:"real_monthly_installs,omitempty"`
	AdSupported              *bool          `json:"ad_supported,omitempty"`
	MaxAndroidAPI            *int64         `json:"max_android_api,omitempty"`
	MinAndroidAPI            *int64         `json:"min_android_api,omitempty"`
	AppBundle                string         `json:"app_bundle,omitempty"`
	ContentRatingDescription string         `json:"content_rating_description,omitempty"`
	Permissions              map[string]any `json:"permissions,omitempty"`
	DataSafety               []any          `json:"data_safety,omitempty"`
	Sale                     *bool          `json:"sale,omitempty"`
	OriginalPrice            *float64       `json:"original_price,omitempty"`
	DeveloperAddress         string         `json:"developer_address,omitempty"`
	DeveloperPhone           string         `json:"developer_phone,omitempty"`
	PublisherCountry         string         `json:"publisher_country,omitempty"`
}

type AppSnapshot struct {
	Platform     string   `json:"platform"`
	AppID        string   `json:"app_id"`
	Country      string   `json:"country"`
	Lang         string   `json:"lang"`
	CapturedAt   string   `json:"captured_at"`
	Title        string   `json:"title,omitempty"`
	Rating       *float64 `json:"rating,omitempty"`
	RatingsCount *int64   `json:"ratings_count,omitempty"`
	ReviewsCount *int64   `json:"reviews_count,omitempty"`
	Installs     string   `json:"installs,omitempty"`
	MinInstalls  *int64   `json:"min_installs,omitempty"`
	RealInstalls *int64   `json:"real_installs,omitempty"`
	Version      string   `json:"version,omitempty"`
}

type ListAppSnapshotsRequest struct {
	AppID   string `json:"app_id"`
	Country string `json:"country"`
	Lang    string `json:"lang"`
	Limit   int    `json:"limit"`
}

type ListRecentAppSnapshotsRequest struct {
	Limit int `json:"limit"`
}

type ListAppSnapshotsResponse struct {
	Items []AppSnapshot `json:"items"`
	Total int           `json:"total"`
}

type AppSnapshotCountResponse struct {
	Total int `json:"total"`
}

type SearchAppsRequest struct {
	Query   string `json:"query"`
	Country string `json:"country"`
	Lang    string `json:"lang"`
	Limit   int    `json:"limit"`
	Proxy   string `json:"proxy,omitempty"`
}

type SearchAppsResponse struct {
	Items []AppSummary `json:"items"`
	Total int          `json:"total"`
}

type CachedAppDetailResponse struct {
	Detail     AppDetail `json:"detail"`
	Cached     bool      `json:"cached"`
	Stale      bool      `json:"stale,omitempty"`
	CapturedAt string    `json:"captured_at,omitempty"`
}

type GetAppDetailRequest struct {
	AppID   string `json:"app_id"`
	Country string `json:"country"`
	Lang    string `json:"lang"`
}

type SimilarAppsRequest struct {
	AppID   string `json:"app_id"`
	Country string `json:"country"`
	Lang    string `json:"lang"`
	Limit   int    `json:"limit"`
}

type SimilarAppsResponse struct {
	Items []AppSummary `json:"items"`
	Total int          `json:"total"`
}

type AppPermissionsRequest struct {
	AppID   string `json:"app_id"`
	Country string `json:"country"`
	Lang    string `json:"lang"`
}

type AppPermissionsResponse struct {
	Groups map[string][]string `json:"groups"`
}

type ChartItem struct {
	AppSummary
	Rank        int      `json:"rank"`
	ChartType   string   `json:"chart_type"`
	Category    string   `json:"category,omitempty"`
	Country     string   `json:"country"`
	Lang        string   `json:"lang"`
	Screenshots []string `json:"screenshots,omitempty"`
	Description string   `json:"description,omitempty"`
}

type FetchChartRequest struct {
	ChartType string `json:"chart_type"`
	Category  string `json:"category,omitempty"`
	Country   string `json:"country"`
	Lang      string `json:"lang"`
	Limit     int    `json:"limit"`
}

type FetchChartResponse struct {
	Items      []ChartItem `json:"items"`
	Total      int         `json:"total"`
	Cached     bool        `json:"cached,omitempty"`
	CapturedAt string      `json:"captured_at,omitempty"`
}

type SaveChartSnapshotRequest struct {
	ChartType string      `json:"chart_type"`
	Category  string      `json:"category,omitempty"`
	Country   string      `json:"country"`
	Lang      string      `json:"lang"`
	Items     []ChartItem `json:"items"`
}

type SaveChartSnapshotResponse struct {
	Saved      int    `json:"saved"`
	CapturedAt string `json:"captured_at"`
}

type ChartRankRequest struct {
	AppID      string `json:"app_id"`
	Collection string `json:"collection"`
	Category   string `json:"category,omitempty"`
	Country    string `json:"country"`
	Lang       string `json:"lang"`
	Limit      int    `json:"limit"`
}

type ChartRankResponse struct {
	Platform     string `json:"platform"`
	AppID        string `json:"app_id"`
	Collection   string `json:"collection"`
	Category     string `json:"category,omitempty"`
	Country      string `json:"country"`
	Lang         string `json:"lang"`
	Found        bool   `json:"found"`
	Rank         *int   `json:"rank,omitempty"`
	CheckedLimit int    `json:"checked_limit"`
	CapturedAt   string `json:"captured_at"`
}

type ChartRankHistoryRequest struct {
	AppID      string `json:"app_id"`
	Collection string `json:"collection"`
	Category   string `json:"category,omitempty"`
	Country    string `json:"country"`
	Lang       string `json:"lang"`
	Limit      int    `json:"limit"`
}

type ChartRankHistoryResponse struct {
	Items []ChartRankResponse `json:"items"`
	Total int                 `json:"total"`
}

type KeywordRankRequest struct {
	Keyword string `json:"keyword"`
	AppID   string `json:"app_id"`
	Country string `json:"country"`
	Lang    string `json:"lang"`
	Limit   int    `json:"limit"`
}

type KeywordRankResponse struct {
	Platform     string       `json:"platform"`
	Keyword      string       `json:"keyword"`
	AppID        string       `json:"app_id"`
	Country      string       `json:"country"`
	Lang         string       `json:"lang"`
	Found        bool         `json:"found"`
	Rank         *int         `json:"rank,omitempty"`
	CheckedLimit int          `json:"checked_limit"`
	CapturedAt   string       `json:"captured_at"`
	Results      []AppSummary `json:"results"`
}

type KeywordRankSnapshot struct {
	Platform     string `json:"platform"`
	Keyword      string `json:"keyword"`
	AppID        string `json:"app_id"`
	Country      string `json:"country"`
	Lang         string `json:"lang"`
	Found        bool   `json:"found"`
	Rank         *int   `json:"rank,omitempty"`
	CheckedLimit int    `json:"checked_limit"`
	CapturedAt   string `json:"captured_at"`
}

type KeywordRankHistoryRequest struct {
	Keyword string `json:"keyword"`
	AppID   string `json:"app_id"`
	Country string `json:"country"`
	Lang    string `json:"lang"`
	Limit   int    `json:"limit"`
}

type KeywordRankRecentRequest struct {
	AppID   string `json:"app_id,omitempty"`
	Country string `json:"country,omitempty"`
	Lang    string `json:"lang,omitempty"`
	Limit   int    `json:"limit"`
}

type KeywordRankHistoryResponse struct {
	Items []KeywordRankSnapshot `json:"items"`
	Total int                   `json:"total"`
}

type SuggestRequest struct {
	Term    string `json:"term"`
	Country string `json:"country"`
	Lang    string `json:"lang"`
	Count   int    `json:"count"`
}

type KeywordCoverageRequest struct {
	AppID          string   `json:"app_id"`
	Country        string   `json:"country"`
	Lang           string   `json:"lang"`
	Limit          int      `json:"limit"`
	MaxCandidates  int      `json:"max_candidates,omitempty"`
	Deep           bool     `json:"deep,omitempty"`
	Candidates     []string `json:"candidates,omitempty"`
	CanonicalAppID string   `json:"canonical_app_id,omitempty"`
}

type KeywordCoverageHit struct {
	Keyword string `json:"keyword"`
	Rank    int    `json:"rank"`
}

type KeywordCoverageResponse struct {
	Platform       string               `json:"platform"`
	AppID          string               `json:"app_id"`
	CanonicalAppID string               `json:"canonical_app_id,omitempty"`
	Country        string               `json:"country"`
	Lang           string               `json:"lang"`
	Deep           bool                 `json:"deep,omitempty"`
	Candidates     []string             `json:"candidates"`
	CandidateCount int                  `json:"candidate_count"`
	Covered        []KeywordCoverageHit `json:"covered"`
	CheckedLimit   int                  `json:"checked_limit"`
	CapturedAt     string               `json:"captured_at,omitempty"`
}

type ReviewItem struct {
	Platform        string         `json:"platform,omitempty"`
	AppID           string         `json:"app_id,omitempty"`
	Country         string         `json:"country,omitempty"`
	Lang            string         `json:"lang,omitempty"`
	ReviewID        string         `json:"review_id,omitempty"`
	UserName        string         `json:"user_name,omitempty"`
	Rating          *int           `json:"rating,omitempty"`
	Content         string         `json:"content,omitempty"`
	AppVersion      string         `json:"app_version,omitempty"`
	HelpfulCount    *int64         `json:"helpful_count,omitempty"`
	ReviewCreatedAt string         `json:"review_created_at,omitempty"`
	CapturedAt      string         `json:"captured_at,omitempty"`
	Raw             map[string]any `json:"raw,omitempty"`
}

type FetchReviewsRequest struct {
	AppID             string `json:"app_id"`
	Country           string `json:"country"`
	Lang              string `json:"lang"`
	Sort              string `json:"sort"`
	Limit             int    `json:"limit"`
	ContinuationToken string `json:"continuation_token,omitempty"`
}

type FetchReviewsResponse struct {
	Items     []ReviewItem `json:"items"`
	Total     int          `json:"total"`
	NextToken string       `json:"next_token,omitempty"`
}

type SaveReviewsRequest struct {
	AppID   string       `json:"app_id"`
	Country string       `json:"country"`
	Lang    string       `json:"lang"`
	Items   []ReviewItem `json:"items"`
}

type SaveReviewsResponse struct {
	Saved int `json:"saved"`
}

type ListCachedReviewsRequest struct {
	AppID string `json:"app_id"`
	Limit int    `json:"limit"`
}

type ListCachedReviewsResponse struct {
	Items []ReviewItem `json:"items"`
	Total int          `json:"total"`
}

type AddTrackedAppRequest struct {
	AppID     string `json:"app_id"`
	Country   string `json:"country"`
	Lang      string `json:"lang"`
	Frequency string `json:"frequency"`
	Tag       string `json:"tag"`
}

type AddTrackedKeywordRequest struct {
	Keyword  string `json:"keyword"`
	AppID    string `json:"app_id"`
	Country  string `json:"country"`
	Lang     string `json:"lang"`
	Platform string `json:"platform,omitempty"`
}

type AddTrackedChartAppRequest struct {
	AppID      string `json:"app_id"`
	Collection string `json:"collection"`
	Category   string `json:"category,omitempty"`
	Country    string `json:"country"`
	Lang       string `json:"lang"`
	Frequency  string `json:"frequency,omitempty"`
}

type RemoveTrackedAppRequest struct {
	AppID   string `json:"app_id"`
	Country string `json:"country"`
	Lang    string `json:"lang"`
}

type SetTrackedAppEnabledRequest struct {
	AppID   string `json:"app_id"`
	Country string `json:"country"`
	Lang    string `json:"lang"`
	Enabled bool   `json:"enabled"`
}

type SetTrackedAppFrequencyRequest struct {
	AppID     string `json:"app_id"`
	Country   string `json:"country"`
	Lang      string `json:"lang"`
	Frequency string `json:"frequency"`
}

type SetTrackedAppTagRequest struct {
	AppID   string `json:"app_id"`
	Country string `json:"country"`
	Lang    string `json:"lang"`
	Tag     string `json:"tag"`
}

type RemoveTrackedKeywordRequest struct {
	Keyword  string `json:"keyword"`
	AppID    string `json:"app_id"`
	Country  string `json:"country"`
	Lang     string `json:"lang"`
	Platform string `json:"platform,omitempty"`
}

type SetTrackedKeywordEnabledRequest struct {
	Keyword  string `json:"keyword"`
	AppID    string `json:"app_id"`
	Country  string `json:"country"`
	Lang     string `json:"lang"`
	Platform string `json:"platform,omitempty"`
	Enabled  bool   `json:"enabled"`
}

type SetTrackedKeywordFrequencyRequest struct {
	Keyword   string `json:"keyword"`
	AppID     string `json:"app_id"`
	Country   string `json:"country"`
	Lang      string `json:"lang"`
	Platform  string `json:"platform,omitempty"`
	Frequency string `json:"frequency"`
}

type RemoveTrackedChartAppRequest struct {
	AppID      string `json:"app_id"`
	Collection string `json:"collection"`
	Category   string `json:"category,omitempty"`
	Country    string `json:"country"`
	Lang       string `json:"lang"`
}

type SetTrackedChartAppEnabledRequest struct {
	AppID      string `json:"app_id"`
	Collection string `json:"collection"`
	Category   string `json:"category,omitempty"`
	Country    string `json:"country"`
	Lang       string `json:"lang"`
	Enabled    bool   `json:"enabled"`
}

type ListTrackedAppsRequest struct {
	Enabled *bool `json:"enabled,omitempty"`
}

type ListTrackedKeywordsRequest struct {
	Enabled *bool `json:"enabled,omitempty"`
}

type ListTrackedChartAppsRequest struct {
	Enabled *bool `json:"enabled,omitempty"`
}

type TrackedApp struct {
	ID                  uint64 `json:"id"`
	Platform            string `json:"platform"`
	AppID               string `json:"app_id"`
	Title               string `json:"title,omitempty"`
	Country             string `json:"country"`
	Lang                string `json:"lang"`
	Frequency           string `json:"frequency"`
	Tag                 string `json:"tag,omitempty"`
	Enabled             bool   `json:"enabled"`
	LastSyncedAt        string `json:"last_synced_at,omitempty"`
	ConsecutiveFailures int    `json:"consecutive_failures"`
	LastFailedAt        string `json:"last_failed_at,omitempty"`
	CreatedAt           string `json:"created_at"`
	UpdatedAt           string `json:"updated_at"`
}

type TrackedKeyword struct {
	ID                  uint64 `json:"id"`
	Platform            string `json:"platform"`
	Keyword             string `json:"keyword"`
	AppID               string `json:"app_id"`
	Country             string `json:"country"`
	Lang                string `json:"lang"`
	Frequency           string `json:"frequency"`
	Enabled             bool   `json:"enabled"`
	LastSyncedAt        string `json:"last_synced_at,omitempty"`
	ConsecutiveFailures int    `json:"consecutive_failures"`
	LastFailedAt        string `json:"last_failed_at,omitempty"`
	CreatedAt           string `json:"created_at"`
	UpdatedAt           string `json:"updated_at"`
}

type TrackedChartApp struct {
	ID                  uint64 `json:"id"`
	Platform            string `json:"platform"`
	AppID               string `json:"app_id"`
	Collection          string `json:"collection"`
	Category            string `json:"category,omitempty"`
	Country             string `json:"country"`
	Lang                string `json:"lang"`
	Frequency           string `json:"frequency"`
	Enabled             bool   `json:"enabled"`
	LastSyncedAt        string `json:"last_synced_at,omitempty"`
	ConsecutiveFailures int    `json:"consecutive_failures"`
	LastFailedAt        string `json:"last_failed_at,omitempty"`
	CreatedAt           string `json:"created_at"`
	UpdatedAt           string `json:"updated_at"`
}

type ListTrackedAppsResponse struct {
	Items []TrackedApp `json:"items"`
	Total int          `json:"total"`
}

type ListTrackedKeywordsResponse struct {
	Items []TrackedKeyword `json:"items"`
	Total int              `json:"total"`
}

type ListTrackedChartAppsResponse struct {
	Items []TrackedChartApp `json:"items"`
	Total int               `json:"total"`
}

type TrackingMutationResponse struct {
	Updated   int    `json:"updated"`
	Enabled   *bool  `json:"enabled,omitempty"`
	Frequency string `json:"frequency,omitempty"`
	Tag       string `json:"tag,omitempty"`
}

type SyncAppNowRequest struct {
	AppID   string `json:"app_id"`
	Country string `json:"country"`
	Lang    string `json:"lang"`
}

type SyncTrackedKeywordRequest struct {
	Keyword  string `json:"keyword"`
	AppID    string `json:"app_id"`
	Country  string `json:"country"`
	Lang     string `json:"lang"`
	Platform string `json:"platform,omitempty"`
	Limit    int    `json:"limit"`
}

type SyncTrackedChartAppRequest struct {
	AppID      string `json:"app_id"`
	Collection string `json:"collection"`
	Category   string `json:"category,omitempty"`
	Country    string `json:"country"`
	Lang       string `json:"lang"`
	Limit      int    `json:"limit"`
}

type SyncAppNowResponse struct {
	Detail    AppDetail `json:"detail"`
	Alerts    []Alert   `json:"alerts"`
	FirstSync bool      `json:"first_sync"`
}

type SyncTrackedKeywordResponse struct {
	Rank   KeywordRankResponse `json:"rank"`
	Alerts []Alert             `json:"alerts,omitempty"`
}

type SyncTrackedChartAppResponse struct {
	Rank   ChartRankResponse `json:"rank"`
	Alerts []Alert           `json:"alerts,omitempty"`
}

type SyncAllRequest struct {
	DueOnly bool `json:"due_only"`
}

type SyncAllResponse struct {
	AppsSynced     int `json:"apps_synced"`
	AppsFailed     int `json:"apps_failed"`
	KeywordsSynced int `json:"keywords_synced"`
	KeywordsFailed int `json:"keywords_failed"`
	ChartsSynced   int `json:"charts_synced"`
	ChartsFailed   int `json:"charts_failed"`
	Alerts         int `json:"alerts"`
}

type RefreshJobRequest struct {
	Kind       string `json:"kind"`
	DueOnly    bool   `json:"due_only,omitempty"`
	AppID      string `json:"app_id,omitempty"`
	Country    string `json:"country,omitempty"`
	Lang       string `json:"lang,omitempty"`
	Keyword    string `json:"keyword,omitempty"`
	Collection string `json:"collection,omitempty"`
	Category   string `json:"category,omitempty"`
	Limit      int    `json:"limit,omitempty"`
	Query      string `json:"query,omitempty"`
	Deep       bool   `json:"deep,omitempty"`
}

type RefreshJobResponse struct {
	JobID       string `json:"job_id"`
	Kind        string `json:"kind"`
	Status      string `json:"status"`
	Message     string `json:"message,omitempty"`
	RequestedAt string `json:"requested_at"`
	StartedAt   string `json:"started_at,omitempty"`
	FinishedAt  string `json:"finished_at,omitempty"`
	UpdatedAt   string `json:"updated_at,omitempty"`
}

type RefreshJobRecord struct {
	Job     RefreshJobResponse
	Request RefreshJobRequest
}

type Alert struct {
	ID        uint64         `json:"id"`
	Type      string         `json:"type"`
	Severity  string         `json:"severity"`
	AppID     string         `json:"app_id,omitempty"`
	Title     string         `json:"title,omitempty"`
	Message   string         `json:"message"`
	Payload   map[string]any `json:"payload,omitempty"`
	IsRead    bool           `json:"is_read"`
	CreatedAt string         `json:"created_at"`
}

type ListAlertsRequest struct {
	AppID    string `json:"app_id,omitempty"`
	Type     string `json:"type,omitempty"`
	Severity string `json:"severity,omitempty"`
	IsRead   *bool  `json:"is_read,omitempty"`
	Limit    int    `json:"limit"`
}

type ListAlertsResponse struct {
	Items []Alert `json:"items"`
	Total int     `json:"total"`
}

type MarkAlertsReadRequest struct {
	IDs []uint64 `json:"ids"`
}

type MarkAlertsReadResponse struct {
	Updated int `json:"updated"`
}

type HistoryRetentionCleanupResponse struct {
	Snapshots int `json:"snapshots"`
	Keywords  int `json:"keywords"`
	Charts    int `json:"charts"`
	Alerts    int `json:"alerts"`
	Reviews   int `json:"reviews"`
}

type SetSettingsRequest struct {
	Values map[string]string `json:"values"`
}
