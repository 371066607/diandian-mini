package service_test

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/catch-radar/storeintel/dto"
	"github.com/catch-radar/storeintel/repo"
	"github.com/catch-radar/storeintel/service"
)

func TestHTTPKeywordCorpusClientCandidatesAndContribute(t *testing.T) {
	var sawCandidates bool
	var sawContribute bool
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("user-agent") != "CatchRadar-corpus/1.0" ||
			r.Header.Get("x-api-key") != "secret" {
			t.Fatalf("missing corpus headers: %+v", r.Header)
		}
		switch r.URL.Path {
		case "/candidates":
			sawCandidates = true
			if r.Method != http.MethodGet {
				t.Fatalf("unexpected candidates method: %s", r.Method)
			}
			q := r.URL.Query()
			if q.Get("platform") != dto.PlatformGooglePlay || q.Get("country") != "us" ||
				q.Get("lang") != "en" || q.Get("tokens") != "editor,photo" ||
				q.Get("limit") != "2" {
				t.Fatalf("unexpected candidates query: %s", r.URL.RawQuery)
			}
			_ = json.NewEncoder(w).Encode(map[string][]string{
				"keywords": {" photo remote ", ""},
			})
		case "/contribute":
			sawContribute = true
			if r.Method != http.MethodPost {
				t.Fatalf("unexpected contribute method: %s", r.Method)
			}
			var payload struct {
				Platform string `json:"platform"`
				Country  string `json:"country"`
				Lang     string `json:"lang"`
				Items    []struct {
					Keyword   string `json:"keyword"`
					Source    string `json:"source"`
					Confirmed bool   `json:"confirmed"`
				} `json:"items"`
			}
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				t.Fatalf("decode contribute payload: %v", err)
			}
			if payload.Platform != dto.PlatformGooglePlay || payload.Country != "us" ||
				payload.Lang != "en" || len(payload.Items) != 1 ||
				payload.Items[0].Keyword != "photo remote" ||
				payload.Items[0].Source != "covered" || !payload.Items[0].Confirmed {
				t.Fatalf("unexpected contribute payload: %+v", payload)
			}
			_, _ = w.Write([]byte(`{"ok":true}`))
		default:
			t.Fatalf("unexpected corpus path: %s", r.URL.Path)
		}
	}))
	defer server.Close()

	client := service.NewHTTPKeywordCorpusClient(service.HTTPKeywordCorpusClientConfig{
		BaseURL: server.URL,
		APIKey:  "secret",
	})
	keywords, err := client.Candidates(context.Background(), service.KeywordCorpusCandidateRequest{
		Platform: dto.PlatformGooglePlay,
		Country:  "us",
		Lang:     "en",
		SeedTokens: map[string]struct{}{
			"photo":  {},
			"editor": {},
		},
		Limit: 2,
	})
	if err != nil {
		t.Fatalf("Candidates returned error: %v", err)
	}
	if len(keywords) != 1 || keywords[0] != "photo remote" {
		t.Fatalf("unexpected keywords: %+v", keywords)
	}
	if err := client.Contribute(context.Background(), service.KeywordCorpusContributeRequest{
		Platform: dto.PlatformGooglePlay,
		Country:  "us",
		Lang:     "en",
		Items: []repo.KeywordCorpusItem{{
			Keyword:   " photo remote ",
			Source:    "covered",
			Confirmed: true,
		}},
	}); err != nil {
		t.Fatalf("Contribute returned error: %v", err)
	}
	if !sawCandidates || !sawContribute {
		t.Fatalf("expected candidates and contribute calls, saw candidates=%v contribute=%v", sawCandidates, sawContribute)
	}
}
