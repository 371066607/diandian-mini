package dto

const PlatformGooglePlay = "google_play"

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

type SearchAppsRequest struct {
	Query   string `json:"query"`
	Country string `json:"country"`
	Lang    string `json:"lang"`
	Limit   int    `json:"limit"`
}

type SearchAppsResponse struct {
	Items []AppSummary `json:"items"`
	Total int          `json:"total"`
}

type GetAppDetailRequest struct {
	AppID   string `json:"app_id"`
	Country string `json:"country"`
	Lang    string `json:"lang"`
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

type AddTrackedAppRequest struct {
	AppID     string `json:"app_id"`
	Country   string `json:"country"`
	Lang      string `json:"lang"`
	Frequency string `json:"frequency"`
	Tag       string `json:"tag"`
}

type ListTrackedAppsRequest struct {
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

type ListTrackedAppsResponse struct {
	Items []TrackedApp `json:"items"`
	Total int          `json:"total"`
}

type SyncAppNowRequest struct {
	AppID   string `json:"app_id"`
	Country string `json:"country"`
	Lang    string `json:"lang"`
}

type SyncAppNowResponse struct {
	Detail    AppDetail `json:"detail"`
	Alerts    []Alert   `json:"alerts"`
	FirstSync bool      `json:"first_sync"`
}

type SyncAllRequest struct {
	DueOnly bool `json:"due_only"`
}

type SyncAllResponse struct {
	AppsSynced int `json:"apps_synced"`
	AppsFailed int `json:"apps_failed"`
	Alerts     int `json:"alerts"`
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
