package googleplay

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"html"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"time"

	"github.com/diandian-mini/storeintel/dto"
)

const defaultBaseURL = "https://play.google.com"

var (
	ErrEmptyResult = errors.New("google play returned empty result")
	ErrNotFound    = errors.New("google play app not found")
)

type Client struct {
	baseURL    string
	httpClient *http.Client
	userAgent  string
}

type Option func(*Client)

func NewClient(opts ...Option) *Client {
	client := &Client{
		baseURL: defaultBaseURL,
		httpClient: &http.Client{
			Timeout: 15 * time.Second,
		},
		userAgent: "Mozilla/5.0 (compatible; StoreIntel/0.1)",
	}
	for _, opt := range opts {
		if opt != nil {
			opt(client)
		}
	}
	return client
}

func WithBaseURL(baseURL string) Option {
	return func(c *Client) {
		if strings.TrimSpace(baseURL) != "" {
			c.baseURL = strings.TrimRight(strings.TrimSpace(baseURL), "/")
		}
	}
}

func WithHTTPClient(httpClient *http.Client) Option {
	return func(c *Client) {
		if httpClient != nil {
			c.httpClient = httpClient
		}
	}
}

func WithUserAgent(userAgent string) Option {
	return func(c *Client) {
		if strings.TrimSpace(userAgent) != "" {
			c.userAgent = strings.TrimSpace(userAgent)
		}
	}
}

func (c *Client) SearchApps(ctx context.Context, req dto.SearchAppsRequest) ([]dto.AppSummary, error) {
	if strings.TrimSpace(req.Query) == "" {
		return nil, fmt.Errorf("query is required")
	}
	limit := req.Limit
	if limit <= 0 || limit > 100 {
		limit = 20
	}
	u, err := url.Parse(c.baseURL + "/store/search")
	if err != nil {
		return nil, err
	}
	q := u.Query()
	q.Set("q", req.Query)
	q.Set("c", "apps")
	q.Set("hl", defaultString(req.Lang, "en"))
	q.Set("gl", strings.ToUpper(defaultString(req.Country, "us")))
	u.RawQuery = q.Encode()

	body, err := c.get(ctx, u.String())
	if err != nil {
		return nil, err
	}
	appIDs := extractAppIDs(body)
	if len(appIDs) == 0 {
		return nil, ErrEmptyResult
	}
	if len(appIDs) > limit {
		appIDs = appIDs[:limit]
	}
	items := make([]dto.AppSummary, 0, len(appIDs))
	for _, appID := range appIDs {
		items = append(items, dto.AppSummary{
			Platform: dto.PlatformGooglePlay,
			AppID:    appID,
			StoreURL: storeURL(c.baseURL, appID, req.Country, req.Lang),
		})
	}
	return items, nil
}

func (c *Client) GetAppDetail(ctx context.Context, req dto.GetAppDetailRequest) (dto.AppDetail, error) {
	appID := strings.TrimSpace(req.AppID)
	if appID == "" {
		return dto.AppDetail{}, fmt.Errorf("app_id is required")
	}
	u, err := url.Parse(c.baseURL + "/store/apps/details")
	if err != nil {
		return dto.AppDetail{}, err
	}
	q := u.Query()
	q.Set("id", appID)
	q.Set("hl", defaultString(req.Lang, "en"))
	q.Set("gl", strings.ToUpper(defaultString(req.Country, "us")))
	u.RawQuery = q.Encode()

	body, err := c.get(ctx, u.String())
	if err != nil {
		return dto.AppDetail{}, err
	}
	detail, err := parseDetailJSONLD(body)
	if err != nil {
		if errors.Is(err, ErrNotFound) {
			return dto.AppDetail{}, err
		}
		detail = dto.AppDetail{}
	}
	detail.Platform = dto.PlatformGooglePlay
	detail.AppID = appID
	detail.StoreURL = storeURL(c.baseURL, appID, req.Country, req.Lang)
	if detail.Title == "" {
		detail.Title = parseHTMLTitle(body)
	}
	if detail.Description == "" {
		detail.Description = parseMetaContent(body, "description")
	}
	if detail.IconURL == "" {
		detail.IconURL = parseMetaProperty(body, "og:image")
	}
	detail.Raw = map[string]any{"source": "google_play_web"}
	return detail, nil
}

func (c *Client) get(ctx context.Context, targetURL string) (string, error) {
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodGet, targetURL, nil)
	if err != nil {
		return "", err
	}
	httpReq.Header.Set("User-Agent", c.userAgent)
	httpReq.Header.Set("Accept-Language", "en-US,en;q=0.9")
	resp, err := c.httpClient.Do(httpReq)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusNotFound {
		return "", ErrNotFound
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return "", fmt.Errorf("google play status %d", resp.StatusCode)
	}
	data, err := io.ReadAll(io.LimitReader(resp.Body, 8<<20))
	if err != nil {
		return "", err
	}
	return string(data), nil
}

var appIDPattern = regexp.MustCompile(`/store/apps/details\?id=([A-Za-z0-9_\.]+)`)

func extractAppIDs(body string) []string {
	matches := appIDPattern.FindAllStringSubmatch(body, -1)
	items := make([]string, 0, len(matches))
	seen := map[string]bool{}
	for _, match := range matches {
		if len(match) < 2 {
			continue
		}
		appID := strings.TrimSpace(html.UnescapeString(match[1]))
		if appID == "" || seen[appID] {
			continue
		}
		seen[appID] = true
		items = append(items, appID)
	}
	return items
}

type jsonLDSoftwareApplication struct {
	Name                string `json:"name"`
	Description         string `json:"description"`
	ApplicationCategory string `json:"applicationCategory"`
	OperatingSystem     string `json:"operatingSystem"`
	Image               string `json:"image"`
	Offers              struct {
		Price         any    `json:"price"`
		PriceCurrency string `json:"priceCurrency"`
	} `json:"offers"`
	AggregateRating struct {
		RatingValue any `json:"ratingValue"`
		RatingCount any `json:"ratingCount"`
		ReviewCount any `json:"reviewCount"`
	} `json:"aggregateRating"`
}

var jsonLDPattern = regexp.MustCompile(`(?is)<script[^>]+type=["']application/ld\+json["'][^>]*>(.*?)</script>`)

func parseDetailJSONLD(body string) (dto.AppDetail, error) {
	matches := jsonLDPattern.FindAllStringSubmatch(body, -1)
	for _, match := range matches {
		if len(match) < 2 {
			continue
		}
		raw := strings.TrimSpace(html.UnescapeString(match[1]))
		var parsed jsonLDSoftwareApplication
		if err := json.Unmarshal([]byte(raw), &parsed); err != nil {
			continue
		}
		if parsed.Name == "" {
			continue
		}
		rating := parseFloatPtr(parsed.AggregateRating.RatingValue)
		ratingsCount := parseInt64Ptr(parsed.AggregateRating.RatingCount)
		reviewsCount := parseInt64Ptr(parsed.AggregateRating.ReviewCount)
		price := stringifyAny(parsed.Offers.Price)
		free := (*bool)(nil)
		if price != "" {
			value := price == "0" || price == "0.0" || price == "0.00"
			free = &value
		}
		return dto.AppDetail{
			AppSummary: dto.AppSummary{
				Platform:     dto.PlatformGooglePlay,
				Title:        parsed.Name,
				Summary:      parsed.Description,
				Category:     parsed.ApplicationCategory,
				Rating:       rating,
				RatingsCount: ratingsCount,
				ReviewsCount: reviewsCount,
				Price:        price,
				Currency:     parsed.Offers.PriceCurrency,
				Free:         free,
				IconURL:      parsed.Image,
			},
			Description:    parsed.Description,
			AndroidVersion: parsed.OperatingSystem,
		}, nil
	}
	return dto.AppDetail{}, ErrNotFound
}

var titlePattern = regexp.MustCompile(`(?is)<title[^>]*>(.*?)</title>`)

func parseHTMLTitle(body string) string {
	match := titlePattern.FindStringSubmatch(body)
	if len(match) < 2 {
		return ""
	}
	title := strings.TrimSpace(html.UnescapeString(stripTags(match[1])))
	return strings.TrimSuffix(title, " - Apps on Google Play")
}

func parseMetaContent(body, name string) string {
	pattern := regexp.MustCompile(`(?is)<meta[^>]+name=["']` + regexp.QuoteMeta(name) + `["'][^>]+content=["']([^"']*)["']`)
	match := pattern.FindStringSubmatch(body)
	if len(match) < 2 {
		return ""
	}
	return strings.TrimSpace(html.UnescapeString(match[1]))
}

func parseMetaProperty(body, property string) string {
	pattern := regexp.MustCompile(`(?is)<meta[^>]+property=["']` + regexp.QuoteMeta(property) + `["'][^>]+content=["']([^"']*)["']`)
	match := pattern.FindStringSubmatch(body)
	if len(match) < 2 {
		return ""
	}
	return strings.TrimSpace(html.UnescapeString(match[1]))
}

var tagPattern = regexp.MustCompile(`(?is)<[^>]+>`)

func stripTags(value string) string {
	return tagPattern.ReplaceAllString(value, "")
}

func parseFloatPtr(value any) *float64 {
	raw := stringifyAny(value)
	if raw == "" {
		return nil
	}
	parsed, err := strconv.ParseFloat(strings.ReplaceAll(raw, ",", ""), 64)
	if err != nil {
		return nil
	}
	return &parsed
}

func parseInt64Ptr(value any) *int64 {
	raw := stringifyAny(value)
	if raw == "" {
		return nil
	}
	parsed, err := strconv.ParseInt(strings.ReplaceAll(raw, ",", ""), 10, 64)
	if err != nil {
		return nil
	}
	return &parsed
}

func stringifyAny(value any) string {
	switch v := value.(type) {
	case nil:
		return ""
	case string:
		return strings.TrimSpace(v)
	case float64:
		return strconv.FormatFloat(v, 'f', -1, 64)
	case int:
		return strconv.Itoa(v)
	case int64:
		return strconv.FormatInt(v, 10)
	default:
		return strings.TrimSpace(fmt.Sprint(v))
	}
}

func storeURL(baseURL, appID, country, lang string) string {
	u, _ := url.Parse(strings.TrimRight(baseURL, "/") + "/store/apps/details")
	q := u.Query()
	q.Set("id", appID)
	q.Set("hl", defaultString(lang, "en"))
	q.Set("gl", strings.ToUpper(defaultString(country, "us")))
	u.RawQuery = q.Encode()
	return u.String()
}

func defaultString(value, fallback string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return fallback
	}
	return value
}
