package service

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"sort"
	"strings"
	"time"

	"github.com/catch-radar/storeintel/repo"
)

const (
	DefaultKeywordCorpusURL = "https://catch-radar-corpus.371066607.workers.dev"
	DefaultKeywordCorpusKey = "970907"
)

type KeywordCorpusCandidateRequest struct {
	Platform   string
	Country    string
	Lang       string
	SeedTokens map[string]struct{}
	Limit      int
}

type KeywordCorpusContributeRequest struct {
	Platform string
	Country  string
	Lang     string
	Items    []repo.KeywordCorpusItem
}

type HTTPKeywordCorpusClientConfig struct {
	BaseURL    string
	APIKey     string
	Timeout    time.Duration
	HTTPClient *http.Client
}

type HTTPKeywordCorpusClient struct {
	baseURL    string
	apiKey     string
	httpClient *http.Client
}

func NewHTTPKeywordCorpusClient(cfg HTTPKeywordCorpusClientConfig) *HTTPKeywordCorpusClient {
	baseURL := strings.TrimRight(strings.TrimSpace(cfg.BaseURL), "/")
	if baseURL == "" {
		return nil
	}
	client := cfg.HTTPClient
	if client == nil {
		timeout := cfg.Timeout
		if timeout <= 0 {
			timeout = 6 * time.Second
		}
		client = &http.Client{Timeout: timeout}
	}
	return &HTTPKeywordCorpusClient{
		baseURL:    baseURL,
		apiKey:     strings.TrimSpace(cfg.APIKey),
		httpClient: client,
	}
}

func (c *HTTPKeywordCorpusClient) Candidates(ctx context.Context, req KeywordCorpusCandidateRequest) ([]string, error) {
	if c == nil || c.baseURL == "" {
		return nil, nil
	}
	tokens := sortedTokenList(req.SeedTokens)
	if len(tokens) == 0 {
		return nil, nil
	}
	limit := req.Limit
	if limit <= 0 {
		limit = 80
	}
	values := url.Values{}
	values.Set("platform", strings.TrimSpace(req.Platform))
	values.Set("country", strings.TrimSpace(req.Country))
	values.Set("lang", strings.TrimSpace(req.Lang))
	values.Set("tokens", strings.Join(tokens, ","))
	values.Set("limit", fmt.Sprintf("%d", limit))
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodGet, c.baseURL+"/candidates?"+values.Encode(), nil)
	if err != nil {
		return nil, err
	}
	c.addHeaders(httpReq)
	resp, err := c.httpClient.Do(httpReq)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("keyword corpus candidates status %d", resp.StatusCode)
	}
	var payload struct {
		Keywords []string `json:"keywords"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return nil, err
	}
	out := make([]string, 0, len(payload.Keywords))
	for _, keyword := range payload.Keywords {
		if keyword = strings.TrimSpace(keyword); keyword != "" {
			out = append(out, keyword)
		}
	}
	return out, nil
}

func (c *HTTPKeywordCorpusClient) Contribute(ctx context.Context, req KeywordCorpusContributeRequest) error {
	if c == nil || c.baseURL == "" || len(req.Items) == 0 {
		return nil
	}
	items := make([]keywordCorpusContributeItem, 0, len(req.Items))
	for _, item := range req.Items {
		keyword := strings.TrimSpace(item.Keyword)
		if keyword == "" {
			continue
		}
		items = append(items, keywordCorpusContributeItem{
			Keyword:   keyword,
			Source:    strings.TrimSpace(item.Source),
			Confirmed: item.Confirmed,
		})
	}
	if len(items) == 0 {
		return nil
	}
	body, err := json.Marshal(keywordCorpusContributePayload{
		Platform: strings.TrimSpace(req.Platform),
		Country:  strings.TrimSpace(req.Country),
		Lang:     strings.TrimSpace(req.Lang),
		Items:    items,
	})
	if err != nil {
		return err
	}
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/contribute", bytes.NewReader(body))
	if err != nil {
		return err
	}
	c.addHeaders(httpReq)
	httpReq.Header.Set("content-type", "application/json")
	resp, err := c.httpClient.Do(httpReq)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("keyword corpus contribute status %d", resp.StatusCode)
	}
	return nil
}

func (c *HTTPKeywordCorpusClient) addHeaders(req *http.Request) {
	req.Header.Set("user-agent", "CatchRadar-corpus/1.0")
	if c.apiKey != "" {
		req.Header.Set("x-api-key", c.apiKey)
	}
}

func sortedTokenList(tokens map[string]struct{}) []string {
	if len(tokens) == 0 {
		return nil
	}
	out := make([]string, 0, len(tokens))
	for token := range tokens {
		token = strings.TrimSpace(token)
		if token != "" {
			out = append(out, token)
		}
	}
	sort.Strings(out)
	return out
}

type keywordCorpusContributePayload struct {
	Platform string                        `json:"platform"`
	Country  string                        `json:"country"`
	Lang     string                        `json:"lang"`
	Items    []keywordCorpusContributeItem `json:"items"`
}

type keywordCorpusContributeItem struct {
	Keyword   string `json:"keyword"`
	Source    string `json:"source"`
	Confirmed bool   `json:"confirmed"`
}

var _ KeywordCorpusClient = (*HTTPKeywordCorpusClient)(nil)
