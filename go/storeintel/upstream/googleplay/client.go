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
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/catch-radar/storeintel/dto"
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

	var body string
	if strings.TrimSpace(req.Proxy) != "" {
		body, err = c.getWithProxy(ctx, u.String(), req.Proxy)
	} else {
		body, err = c.get(ctx, u.String())
	}
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

func (c *Client) Suggest(ctx context.Context, req dto.SuggestRequest) ([]string, error) {
	term := strings.TrimSpace(req.Term)
	if term == "" {
		return nil, fmt.Errorf("term is required")
	}
	count := req.Count
	if count <= 0 || count > 20 {
		count = 8
	}
	u, err := url.Parse(c.baseURL + "/_/PlayStoreUi/data/batchexecute")
	if err != nil {
		return nil, err
	}
	q := u.Query()
	q.Set("rpcids", "IJ4APc")
	q.Set("f.sid", "-697906427155521722")
	q.Set("bl", "boq_playuiserver_20190903.08_p0")
	q.Set("hl", defaultString(req.Lang, "en"))
	q.Set("gl", strings.ToUpper(defaultString(req.Country, "us")))
	q.Set("authuser", "")
	q.Set("soc-app", "121")
	q.Set("soc-platform", "1")
	q.Set("soc-device", "1")
	q.Set("_reqid", "1065213")
	u.RawQuery = q.Encode()

	body, err := c.post(ctx, u.String(), buildSuggestForm(term, max(count, 10)))
	if err != nil {
		return nil, err
	}
	return parseSuggestBatchResponse(body, count)
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

func (c *Client) SimilarApps(ctx context.Context, req dto.SimilarAppsRequest) ([]dto.AppSummary, error) {
	appID := strings.TrimSpace(req.AppID)
	if appID == "" {
		return nil, fmt.Errorf("app_id is required")
	}
	limit := req.Limit
	if limit <= 0 || limit > 100 {
		limit = 20
	}
	u, err := url.Parse(c.baseURL + "/store/apps/details")
	if err != nil {
		return nil, err
	}
	q := u.Query()
	q.Set("id", appID)
	q.Set("hl", defaultString(req.Lang, "en"))
	q.Set("gl", strings.ToUpper(defaultString(req.Country, "us")))
	u.RawQuery = q.Encode()

	body, err := c.get(ctx, u.String())
	if err != nil {
		return nil, err
	}
	appIDs := extractAppIDs(body)
	items := make([]dto.AppSummary, 0, min(len(appIDs), limit))
	for _, candidate := range appIDs {
		if sameAppID(candidate, appID) {
			continue
		}
		items = append(items, dto.AppSummary{
			Platform: dto.PlatformGooglePlay,
			AppID:    candidate,
			StoreURL: storeURL(c.baseURL, candidate, req.Country, req.Lang),
			Raw:      map[string]any{"source": "google_play_web_similar"},
		})
		if len(items) >= limit {
			break
		}
	}
	if len(items) == 0 {
		return nil, ErrEmptyResult
	}
	return items, nil
}

func (c *Client) GetAppPermissions(ctx context.Context, req dto.AppPermissionsRequest) (map[string][]string, error) {
	appID := strings.TrimSpace(req.AppID)
	if appID == "" {
		return nil, fmt.Errorf("app_id is required")
	}
	u, err := url.Parse(c.baseURL + "/_/PlayStoreUi/data/batchexecute")
	if err != nil {
		return nil, err
	}
	q := u.Query()
	q.Set("hl", defaultString(req.Lang, "en"))
	q.Set("gl", strings.ToUpper(defaultString(req.Country, "us")))
	u.RawQuery = q.Encode()

	body, err := c.post(ctx, u.String(), buildPermissionsForm(appID))
	if err != nil {
		return nil, err
	}
	groups, err := parsePermissionsBatchResponse(body)
	if err != nil {
		return nil, err
	}
	return groups, nil
}

func (c *Client) FetchChart(ctx context.Context, req dto.FetchChartRequest) (dto.FetchChartResponse, error) {
	limit := req.Limit
	if limit <= 0 || limit > 200 {
		limit = 100
	}
	chartType := defaultString(req.ChartType, "top_free")
	country := strings.ToLower(defaultString(req.Country, "us"))
	lang := strings.ToLower(defaultString(req.Lang, "en"))

	var lastErr error
	for _, targetURL := range c.chartURLs(chartType, req.Category, country, lang) {
		body, err := c.get(ctx, targetURL)
		if err != nil {
			lastErr = err
			continue
		}
		appIDs := extractAppIDs(body)
		if len(appIDs) == 0 {
			lastErr = ErrEmptyResult
			continue
		}
		if len(appIDs) > limit {
			appIDs = appIDs[:limit]
		}
		items := make([]dto.ChartItem, 0, len(appIDs))
		for index, appID := range appIDs {
			items = append(items, dto.ChartItem{
				AppSummary: dto.AppSummary{
					Platform: dto.PlatformGooglePlay,
					AppID:    appID,
					StoreURL: storeURL(c.baseURL, appID, country, lang),
					Raw: map[string]any{
						"source":     "google_play_web_chart",
						"chart_type": chartType,
						"category":   strings.TrimSpace(req.Category),
					},
				},
				Rank:      index + 1,
				ChartType: chartType,
				Category:  strings.TrimSpace(req.Category),
				Country:   country,
				Lang:      lang,
			})
		}
		return dto.FetchChartResponse{Items: items, Total: len(items)}, nil
	}
	if lastErr != nil {
		return dto.FetchChartResponse{}, lastErr
	}
	return dto.FetchChartResponse{}, ErrEmptyResult
}

func (c *Client) FetchReviews(ctx context.Context, req dto.FetchReviewsRequest) (dto.FetchReviewsResponse, error) {
	appID := strings.TrimSpace(req.AppID)
	if appID == "" {
		return dto.FetchReviewsResponse{}, fmt.Errorf("app_id is required")
	}
	u, err := url.Parse(c.baseURL + "/_/PlayStoreUi/data/batchexecute")
	if err != nil {
		return dto.FetchReviewsResponse{}, err
	}
	q := u.Query()
	q.Set("hl", defaultString(req.Lang, "en"))
	q.Set("gl", strings.ToUpper(defaultString(req.Country, "us")))
	u.RawQuery = q.Encode()

	limit := req.Limit
	if limit <= 0 || limit > 200 {
		limit = 20
	}
	body, err := c.post(ctx, u.String(), buildReviewsForm(appID, reviewSortValue(req.Sort), limit, req.ContinuationToken))
	if err != nil {
		return dto.FetchReviewsResponse{}, err
	}
	items, nextToken, err := parseReviewsBatchResponse(body, appID, req.Country, req.Lang)
	if err != nil {
		return dto.FetchReviewsResponse{}, err
	}
	return dto.FetchReviewsResponse{Items: items, Total: len(items), NextToken: nextToken}, nil
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

func (c *Client) getWithProxy(ctx context.Context, targetURL, proxyURL string) (string, error) {
	proxyURL = strings.TrimSpace(proxyURL)
	if proxyURL == "" {
		return c.get(ctx, targetURL)
	}
	parsed, err := url.Parse(proxyURL)
	if err != nil {
		return "", err
	}
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.Proxy = http.ProxyURL(parsed)
	client := &http.Client{
		Timeout:   c.httpClient.Timeout,
		Transport: transport,
	}
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodGet, targetURL, nil)
	if err != nil {
		return "", err
	}
	httpReq.Header.Set("User-Agent", c.userAgent)
	httpReq.Header.Set("Accept-Language", "en-US,en;q=0.9")
	resp, err := client.Do(httpReq)
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

func (c *Client) post(ctx context.Context, targetURL, body string) (string, error) {
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, targetURL, strings.NewReader(body))
	if err != nil {
		return "", err
	}
	httpReq.Header.Set("User-Agent", c.userAgent)
	httpReq.Header.Set("Accept-Language", "en-US,en;q=0.9")
	httpReq.Header.Set("Content-Type", "application/x-www-form-urlencoded")
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

func (c *Client) chartURLs(chartType, category, country, lang string) []string {
	values := []string{}
	primary, _ := url.Parse(c.baseURL + "/store/apps/top")
	q := primary.Query()
	q.Set("hl", defaultString(lang, "en"))
	q.Set("gl", strings.ToUpper(defaultString(country, "us")))
	q.Set("c", "apps")
	q.Set("chart", defaultString(chartType, "top_free"))
	if strings.TrimSpace(category) != "" {
		q.Set("category", strings.TrimSpace(category))
	}
	primary.RawQuery = q.Encode()
	values = append(values, primary.String())

	collection := chartCollection(defaultString(chartType, "top_free"))
	if collection != "" {
		secondary, _ := url.Parse(c.baseURL + "/store/apps/collection/" + collection)
		sq := secondary.Query()
		sq.Set("hl", defaultString(lang, "en"))
		sq.Set("gl", strings.ToUpper(defaultString(country, "us")))
		secondary.RawQuery = sq.Encode()
		values = append(values, secondary.String())
	}
	return values
}

func chartCollection(chartType string) string {
	switch strings.ToLower(strings.TrimSpace(chartType)) {
	case "top_paid":
		return "topselling_paid"
	case "top_grossing":
		return "topgrossing"
	default:
		return "topselling_free"
	}
}

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
	Offers              any    `json:"offers"`
	AggregateRating     struct {
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
		price, currency := parseJSONLDOffer(parsed.Offers)
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
				Currency:     currency,
				Free:         free,
				IconURL:      parsed.Image,
			},
			Description:    parsed.Description,
			AndroidVersion: parsed.OperatingSystem,
		}, nil
	}
	return dto.AppDetail{}, ErrNotFound
}

func parseJSONLDOffer(value any) (string, string) {
	switch offers := value.(type) {
	case []any:
		for _, item := range offers {
			price, currency := parseJSONLDOffer(item)
			if price != "" || currency != "" {
				return price, currency
			}
		}
	case map[string]any:
		return stringifyAny(offers["price"]), stringifyAny(offers["priceCurrency"])
	}
	return "", ""
}

func buildReviewsForm(appID string, sort, count int, continuationToken string) string {
	countArgs := []any{count}
	if strings.TrimSpace(continuationToken) != "" {
		countArgs = []any{count, nil, strings.TrimSpace(continuationToken)}
	}
	inner := []any{
		nil,
		[]any{2, sort, countArgs, nil, []any{nil, nil, nil, nil, nil, nil, nil, nil, nil}},
		[]any{appID, 7},
	}
	innerJSON, _ := json.Marshal(inner)
	outer := []any{[]any{[]any{"oCPfdb", string(innerJSON), nil, "generic"}}}
	outerJSON, _ := json.Marshal(outer)
	return url.Values{"f.req": []string{string(outerJSON) + "\n"}}.Encode()
}

func buildPermissionsForm(appID string) string {
	inner := []any{[]any{nil, []any{strings.TrimSpace(appID), 7}, []any{}}}
	innerJSON, _ := json.Marshal(inner)
	outer := []any{[]any{[]any{"xdSrCf", string(innerJSON), nil, "1"}}}
	outerJSON, _ := json.Marshal(outer)
	return url.Values{"f.req": []string{string(outerJSON)}}.Encode()
}

func buildSuggestForm(term string, count int) string {
	inner := []any{[]any{nil, []any{strings.TrimSpace(term)}, []any{count}, []any{2}, 4}}
	innerJSON, _ := json.Marshal(inner)
	outer := []any{[]any{[]any{"IJ4APc", string(innerJSON)}}}
	outerJSON, _ := json.Marshal(outer)
	return url.Values{"f.req": []string{string(outerJSON)}}.Encode()
}

func reviewSortValue(sort string) int {
	switch strings.ToLower(strings.TrimSpace(sort)) {
	case "rating":
		return 3
	case "helpfulness", "most_relevant":
		return 1
	default:
		return 2
	}
}

func parseReviewsBatchResponse(body, appID, country, lang string) ([]dto.ReviewItem, string, error) {
	payloadText, err := reviewsPayloadText(body)
	if err != nil {
		return nil, "", err
	}
	var payload any
	if err := json.Unmarshal([]byte(payloadText), &payload); err != nil {
		return nil, "", err
	}
	reviewItems, _ := arrayAt(payload, 0)
	items := make([]dto.ReviewItem, 0, len(reviewItems))
	for _, raw := range reviewItems {
		review, ok := raw.([]any)
		if !ok {
			continue
		}
		items = append(items, reviewItemFromArray(review, appID, country, lang))
	}
	return items, reviewsNextToken(payload), nil
}

func parseSuggestBatchResponse(body string, count int) ([]string, error) {
	payloadText, err := suggestPayloadText(body)
	if err != nil {
		return nil, err
	}
	var payload any
	if err := json.Unmarshal([]byte(payloadText), &payload); err != nil {
		return nil, err
	}
	top, ok := arrayAt(payload, 0)
	if !ok {
		return []string{}, nil
	}
	rows, ok := arrayAt(top, 0)
	if !ok {
		return []string{}, nil
	}
	items := make([]string, 0, min(len(rows), count))
	seen := map[string]bool{}
	for _, rawRow := range rows {
		suggestion := strings.TrimSpace(stringAtPath(rawRow, 0))
		if suggestion == "" || seen[suggestion] {
			continue
		}
		seen[suggestion] = true
		items = append(items, suggestion)
		if len(items) >= count {
			break
		}
	}
	return items, nil
}

func suggestPayloadText(body string) (string, error) {
	body = strings.TrimSpace(body)
	if strings.HasPrefix(body, ")]}'") {
		if index := strings.Index(body, "\n\n"); index >= 0 {
			body = strings.TrimSpace(body[index+2:])
		} else {
			body = strings.TrimSpace(strings.TrimPrefix(body, ")]}'"))
		}
	}
	var outer any
	if err := json.Unmarshal([]byte(body), &outer); err != nil {
		return "", err
	}
	if payload := stringAtPath(outer, 0, 2); payload != "" {
		return payload, nil
	}
	if payload := stringAtPath(outer, 0, 0, 2); payload != "" {
		return payload, nil
	}
	return "", ErrEmptyResult
}

func reviewsPayloadText(body string) (string, error) {
	body = strings.TrimSpace(body)
	if strings.HasPrefix(body, ")]}'") {
		if index := strings.Index(body, "\n\n"); index >= 0 {
			body = strings.TrimSpace(body[index+2:])
		} else {
			body = strings.TrimSpace(strings.TrimPrefix(body, ")]}'"))
		}
	}
	var outer any
	if err := json.Unmarshal([]byte(body), &outer); err != nil {
		return "", err
	}
	if payload := stringAtPath(outer, 0, 2); payload != "" {
		return payload, nil
	}
	if payload := stringAtPath(outer, 0, 0, 2); payload != "" {
		return payload, nil
	}
	return "", ErrEmptyResult
}

func reviewItemFromArray(review []any, appID, country, lang string) dto.ReviewItem {
	return dto.ReviewItem{
		Platform:        dto.PlatformGooglePlay,
		AppID:           appID,
		Country:         strings.ToLower(defaultString(country, "us")),
		Lang:            strings.ToLower(defaultString(lang, "en")),
		ReviewID:        stringAtPath(review, 0),
		UserName:        stringAtPath(review, 1, 0),
		Rating:          intPtrAt(review, 2),
		Content:         stringAtPath(review, 4),
		AppVersion:      stringAtPath(review, 10),
		HelpfulCount:    int64PtrAt(review, 6),
		ReviewCreatedAt: reviewTimestampAt(review, 5, 0),
		Raw:             map[string]any{"source": "google_play_batchexecute", "item": review},
	}
}

func reviewsNextToken(payload any) string {
	items, ok := payload.([]any)
	if !ok || len(items) < 2 {
		return ""
	}
	return stringAtPath(items, len(items)-2, -1)
}

func parsePermissionsBatchResponse(body string) (map[string][]string, error) {
	payloadText, err := permissionsPayloadText(body)
	if err != nil {
		return nil, err
	}
	var container any
	if err := json.Unmarshal([]byte(payloadText), &container); err != nil {
		return nil, err
	}
	groups := map[string][]string{}
	for _, rawGroup := range permissionGroupContainers(container) {
		group, items := permissionGroup(rawGroup)
		if group == "" || len(items) == 0 {
			continue
		}
		groups[group] = items
	}
	if len(groups) == 0 {
		return nil, ErrEmptyResult
	}
	return groups, nil
}

func permissionsPayloadText(body string) (string, error) {
	body = strings.TrimSpace(body)
	if strings.HasPrefix(body, ")]}'") {
		if index := strings.Index(body, "\n\n"); index >= 0 {
			body = strings.TrimSpace(body[index+2:])
		} else {
			body = strings.TrimSpace(strings.TrimPrefix(body, ")]}'"))
		}
	}
	var outer any
	if err := json.Unmarshal([]byte(body), &outer); err != nil {
		return "", err
	}
	if payload := stringAtPath(outer, 0, 2); payload != "" {
		return payload, nil
	}
	if payload := stringAtPath(outer, 0, 0, 2); payload != "" {
		return payload, nil
	}
	return "", ErrEmptyResult
}

func permissionGroupContainers(container any) []any {
	rows, ok := container.([]any)
	if !ok {
		return nil
	}
	result := []any{}
	for _, row := range rows {
		items, ok := row.([]any)
		if !ok || len(items) == 0 {
			continue
		}
		first, firstOK := items[0].([]any)
		if firstOK && len(first) == 2 {
			result = append(result, []any{"Uncategorized", nil, items, nil})
			continue
		}
		result = append(result, items...)
	}
	return result
}

func permissionGroup(raw any) (string, []string) {
	groupItems, ok := raw.([]any)
	if !ok {
		return "", nil
	}
	group := stringAtPath(groupItems, 0)
	permissionRows, ok := arrayAt(groupItems, 2)
	if !ok {
		return group, nil
	}
	items := make([]string, 0, len(permissionRows))
	seen := map[string]bool{}
	for _, rawPermission := range permissionRows {
		name := stringAtPath(rawPermission, 1)
		if name == "" || seen[name] {
			continue
		}
		seen[name] = true
		items = append(items, name)
	}
	sort.Strings(items)
	return group, items
}

func stringAtPath(value any, path ...int) string {
	current := value
	for _, index := range path {
		items, ok := current.([]any)
		if !ok || len(items) == 0 {
			return ""
		}
		if index < 0 {
			index = len(items) + index
		}
		if index < 0 || index >= len(items) {
			return ""
		}
		current = items[index]
	}
	return stringifyAny(current)
}

func arrayAt(value any, index int) ([]any, bool) {
	items, ok := value.([]any)
	if !ok || index < 0 || index >= len(items) {
		return nil, false
	}
	array, ok := items[index].([]any)
	return array, ok
}

func intPtrAt(value any, path ...int) *int {
	raw := stringAtPath(value, path...)
	if raw == "" {
		return nil
	}
	parsed, err := strconv.Atoi(raw)
	if err != nil {
		return nil
	}
	return &parsed
}

func int64PtrAt(value any, path ...int) *int64 {
	raw := stringAtPath(value, path...)
	if raw == "" {
		return nil
	}
	parsed, err := strconv.ParseInt(raw, 10, 64)
	if err != nil {
		return nil
	}
	return &parsed
}

func reviewTimestampAt(value any, path ...int) string {
	raw := stringAtPath(value, path...)
	if raw == "" {
		return ""
	}
	parsed, err := strconv.ParseInt(raw, 10, 64)
	if err != nil {
		return raw
	}
	return time.Unix(parsed, 0).UTC().Format(time.RFC3339)
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

func sameAppID(left, right string) bool {
	return strings.EqualFold(strings.TrimSpace(left), strings.TrimSpace(right))
}

func defaultString(value, fallback string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return fallback
	}
	return value
}
