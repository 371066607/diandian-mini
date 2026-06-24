package gateway

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"

	"github.com/catch-radar/storeintel/dto"
	"github.com/catch-radar/storeintel/service"
)

const maxRequestBodyBytes = 1 << 20

type HTTPHandler struct {
	service service.StoreIntelService
	jobs    *refreshJobManager
}

type HandlerOption func(*handlerOptions)

type handlerOptions struct {
	refreshQueue RefreshJobQueue
}

func WithRefreshJobQueue(queue RefreshJobQueue) HandlerOption {
	return func(opts *handlerOptions) {
		opts.refreshQueue = queue
	}
}

func NewHandler(storeService service.StoreIntelService, opts ...HandlerOption) http.Handler {
	options := handlerOptions{}
	for _, opt := range opts {
		if opt != nil {
			opt(&options)
		}
	}
	return &HTTPHandler{
		service: storeService,
		jobs:    newRefreshJobManager(storeService, options.refreshQueue),
	}
}

func (h *HTTPHandler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path == "/healthz" {
		writeJSON(w, http.StatusOK, Success(map[string]string{"status": "ok"}))
		return
	}
	if h.service == nil {
		writeJSON(w, http.StatusBadGateway, Failure(ErrorCodeInternalFailure, "store intel service is not configured", "STORE_INTEL_SERVICE_NOT_CONFIGURED"))
		return
	}
	switch {
	case r.Method == http.MethodGet && r.URL.Path == "/api/store-intel/apps/search/cache":
		h.searchCachedApps(w, r)
	case r.Method == http.MethodGet && r.URL.Path == "/api/store-intel/apps/search":
		h.searchApps(w, r)
	case r.Method == http.MethodGet && appCachePath(r.URL.Path):
		h.getCachedAppDetail(w, r)
	case r.Method == http.MethodGet && appReviewsPathKind(r.URL.Path) == "cache":
		h.listCachedReviews(w, r)
	case r.Method == http.MethodGet && appReviewsPathKind(r.URL.Path) == "reviews":
		h.fetchReviews(w, r)
	case r.Method == http.MethodPost && appReviewsPathKind(r.URL.Path) == "reviews":
		h.saveReviews(w, r)
	case r.Method == http.MethodGet && appSimilarPath(r.URL.Path):
		h.similarApps(w, r)
	case r.Method == http.MethodGet && appPermissionsPath(r.URL.Path):
		h.appPermissions(w, r)
	case r.Method == http.MethodGet && strings.HasPrefix(r.URL.Path, "/api/store-intel/apps/"):
		h.getAppDetail(w, r)
	case r.Method == http.MethodGet && r.URL.Path == "/api/store-intel/charts/cache":
		h.fetchCachedChart(w, r)
	case r.Method == http.MethodGet && r.URL.Path == "/api/store-intel/charts":
		h.fetchChart(w, r)
	case r.Method == http.MethodPost && r.URL.Path == "/api/store-intel/charts/snapshot":
		h.saveChartSnapshot(w, r)
	case r.Method == http.MethodGet && r.URL.Path == "/api/store-intel/app-snapshots/history":
		h.appSnapshotHistory(w, r)
	case r.Method == http.MethodGet && r.URL.Path == "/api/store-intel/app-snapshots/recent":
		h.recentAppSnapshots(w, r)
	case r.Method == http.MethodGet && r.URL.Path == "/api/store-intel/app-snapshots/count":
		h.countAppSnapshots(w, r)
	case r.Method == http.MethodPost && r.URL.Path == "/api/store-intel/chart-rank":
		h.rankChart(w, r)
	case r.Method == http.MethodGet && r.URL.Path == "/api/store-intel/chart-rank/history":
		h.chartRankHistory(w, r)
	case r.Method == http.MethodPost && r.URL.Path == "/api/store-intel/keyword-rank":
		h.rankKeyword(w, r)
	case r.Method == http.MethodGet && r.URL.Path == "/api/store-intel/keyword-rank/history":
		h.keywordRankHistory(w, r)
	case r.Method == http.MethodGet && r.URL.Path == "/api/store-intel/keyword-rank/recent":
		h.recentKeywordRanks(w, r)
	case r.Method == http.MethodGet && r.URL.Path == "/api/store-intel/keyword-coverage/cache":
		h.cachedKeywordCoverage(w, r)
	case r.Method == http.MethodPost && r.URL.Path == "/api/store-intel/keyword-coverage":
		h.keywordCoverage(w, r)
	case r.Method == http.MethodPost && r.URL.Path == "/api/store-intel/keyword-coverage/stream":
		h.keywordCoverageStream(w, r)
	case r.Method == http.MethodGet && r.URL.Path == "/api/store-intel/tracking/apps":
		h.listTrackedApps(w, r)
	case r.Method == http.MethodPost && r.URL.Path == "/api/store-intel/tracking/apps":
		h.addTrackedApp(w, r)
	case r.Method == http.MethodPost && r.URL.Path == "/api/store-intel/tracking/apps/remove":
		h.removeTrackedApp(w, r)
	case r.Method == http.MethodPost && r.URL.Path == "/api/store-intel/tracking/apps/enabled":
		h.setTrackedAppEnabled(w, r)
	case r.Method == http.MethodPost && r.URL.Path == "/api/store-intel/tracking/apps/frequency":
		h.setTrackedAppFrequency(w, r)
	case r.Method == http.MethodPost && r.URL.Path == "/api/store-intel/tracking/apps/tag":
		h.setTrackedAppTag(w, r)
	case r.Method == http.MethodPost && r.URL.Path == "/api/store-intel/tracking/apps/sync":
		h.syncAppNow(w, r)
	case r.Method == http.MethodGet && r.URL.Path == "/api/store-intel/tracking/keywords":
		h.listTrackedKeywords(w, r)
	case r.Method == http.MethodPost && r.URL.Path == "/api/store-intel/tracking/keywords":
		h.addTrackedKeyword(w, r)
	case r.Method == http.MethodPost && r.URL.Path == "/api/store-intel/tracking/keywords/remove":
		h.removeTrackedKeyword(w, r)
	case r.Method == http.MethodPost && r.URL.Path == "/api/store-intel/tracking/keywords/enabled":
		h.setTrackedKeywordEnabled(w, r)
	case r.Method == http.MethodPost && r.URL.Path == "/api/store-intel/tracking/keywords/frequency":
		h.setTrackedKeywordFrequency(w, r)
	case r.Method == http.MethodPost && r.URL.Path == "/api/store-intel/tracking/keywords/sync":
		h.syncTrackedKeyword(w, r)
	case r.Method == http.MethodGet && r.URL.Path == "/api/store-intel/tracking/chart-apps":
		h.listTrackedChartApps(w, r)
	case r.Method == http.MethodPost && r.URL.Path == "/api/store-intel/tracking/chart-apps":
		h.addTrackedChartApp(w, r)
	case r.Method == http.MethodPost && r.URL.Path == "/api/store-intel/tracking/chart-apps/remove":
		h.removeTrackedChartApp(w, r)
	case r.Method == http.MethodPost && r.URL.Path == "/api/store-intel/tracking/chart-apps/enabled":
		h.setTrackedChartAppEnabled(w, r)
	case r.Method == http.MethodPost && r.URL.Path == "/api/store-intel/tracking/chart-apps/sync":
		h.syncTrackedChartApp(w, r)
	case r.Method == http.MethodPost && r.URL.Path == "/api/store-intel/tracking/sync-all":
		h.syncAll(w, r)
	case r.Method == http.MethodGet && r.URL.Path == "/api/store-intel/alerts":
		h.listAlerts(w, r)
	case r.Method == http.MethodPost && r.URL.Path == "/api/store-intel/alerts/read":
		h.markAlertsRead(w, r)
	case r.Method == http.MethodPost && r.URL.Path == "/api/store-intel/history/cleanup":
		h.cleanupHistory(w, r)
	case r.Method == http.MethodPost && r.URL.Path == "/api/store-intel/refresh-jobs":
		h.requestRefreshJob(w, r)
	case r.Method == http.MethodGet && strings.HasPrefix(r.URL.Path, "/api/store-intel/refresh-jobs/"):
		h.getRefreshJob(w, r)
	case r.Method == http.MethodGet && r.URL.Path == "/api/store-intel/settings":
		h.getSettings(w, r)
	case r.Method == http.MethodPost && r.URL.Path == "/api/store-intel/settings":
		h.setSettings(w, r)
	default:
		writeJSON(w, http.StatusNotFound, Failure(ErrorCodeNotFound, "not found", "STORE_INTEL_ROUTE_NOT_FOUND"))
	}
}

func (h *HTTPHandler) searchApps(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query()
	req := dto.SearchAppsRequest{
		Query:   coalesceQuery(query, "query", "q"),
		Country: query.Get("country"),
		Lang:    query.Get("lang"),
		Limit:   parseInt(query.Get("limit")),
	}
	result, err := h.service.SearchApps(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) searchCachedApps(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query()
	req := dto.SearchAppsRequest{
		Query:   coalesceQuery(query, "query", "q"),
		Country: query.Get("country"),
		Lang:    query.Get("lang"),
		Limit:   parseInt(query.Get("limit")),
	}
	result, err := h.service.SearchCachedApps(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) getAppDetail(w http.ResponseWriter, r *http.Request) {
	appID := strings.TrimPrefix(r.URL.Path, "/api/store-intel/apps/")
	appID, err := url.PathUnescape(appID)
	if err != nil || strings.TrimSpace(appID) == "" || strings.Contains(appID, "/") {
		writeJSON(w, http.StatusBadRequest, Failure(ErrorCodeBadRequest, "invalid app_id", "STORE_INTEL_REQUEST_INVALID"))
		return
	}
	query := r.URL.Query()
	result, err := h.service.GetAppDetail(r.Context(), dto.GetAppDetailRequest{
		AppID:   appID,
		Country: query.Get("country"),
		Lang:    query.Get("lang"),
	})
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) getCachedAppDetail(w http.ResponseWriter, r *http.Request) {
	appID, ok := appPathAppID(w, r, "cache")
	if !ok {
		return
	}
	query := r.URL.Query()
	result, err := h.service.GetCachedAppDetail(r.Context(), dto.GetAppDetailRequest{
		AppID:   appID,
		Country: query.Get("country"),
		Lang:    query.Get("lang"),
	})
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) rankKeyword(w http.ResponseWriter, r *http.Request) {
	var req dto.KeywordRankRequest
	if !decodeBody(w, r, &req) {
		return
	}
	result, err := h.service.RankKeyword(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) fetchChart(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query()
	result, err := h.service.FetchChart(r.Context(), dto.FetchChartRequest{
		ChartType: coalesceQuery(query, "chart_type", "collection"),
		Category:  query.Get("category"),
		Country:   query.Get("country"),
		Lang:      query.Get("lang"),
		Limit:     parseInt(query.Get("limit")),
	})
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) fetchCachedChart(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query()
	result, err := h.service.FetchCachedChart(r.Context(), dto.FetchChartRequest{
		ChartType: coalesceQuery(query, "chart_type", "collection"),
		Category:  query.Get("category"),
		Country:   query.Get("country"),
		Lang:      query.Get("lang"),
		Limit:     parseInt(query.Get("limit")),
	})
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) saveChartSnapshot(w http.ResponseWriter, r *http.Request) {
	var req dto.SaveChartSnapshotRequest
	if !decodeBody(w, r, &req) {
		return
	}
	result, err := h.service.SaveChartSnapshot(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) appSnapshotHistory(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query()
	result, err := h.service.ListAppSnapshotHistory(r.Context(), dto.ListAppSnapshotsRequest{
		AppID:   query.Get("app_id"),
		Country: query.Get("country"),
		Lang:    query.Get("lang"),
		Limit:   parseInt(query.Get("limit")),
	})
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) recentAppSnapshots(w http.ResponseWriter, r *http.Request) {
	result, err := h.service.ListRecentAppSnapshots(r.Context(), dto.ListRecentAppSnapshotsRequest{
		Limit: parseInt(r.URL.Query().Get("limit")),
	})
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) countAppSnapshots(w http.ResponseWriter, r *http.Request) {
	result, err := h.service.CountAppSnapshots(r.Context())
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) rankChart(w http.ResponseWriter, r *http.Request) {
	var req dto.ChartRankRequest
	if !decodeBody(w, r, &req) {
		return
	}
	result, err := h.service.RankChart(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) chartRankHistory(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query()
	result, err := h.service.ListChartRankHistory(r.Context(), dto.ChartRankHistoryRequest{
		AppID:      query.Get("app_id"),
		Collection: coalesceQuery(query, "collection", "chart_type"),
		Category:   query.Get("category"),
		Country:    query.Get("country"),
		Lang:       query.Get("lang"),
		Limit:      parseInt(query.Get("limit")),
	})
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) keywordRankHistory(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query()
	result, err := h.service.ListKeywordRankHistory(r.Context(), dto.KeywordRankHistoryRequest{
		Keyword: coalesceQuery(query, "keyword", "q"),
		AppID:   query.Get("app_id"),
		Country: query.Get("country"),
		Lang:    query.Get("lang"),
		Limit:   parseInt(query.Get("limit")),
	})
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) recentKeywordRanks(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query()
	result, err := h.service.ListRecentKeywordRanks(r.Context(), dto.KeywordRankRecentRequest{
		AppID:   query.Get("app_id"),
		Country: query.Get("country"),
		Lang:    query.Get("lang"),
		Limit:   parseInt(query.Get("limit")),
	})
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) keywordCoverage(w http.ResponseWriter, r *http.Request) {
	var req dto.KeywordCoverageRequest
	if !decodeBody(w, r, &req) {
		return
	}
	result, err := h.service.AnalyzeKeywordCoverage(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) cachedKeywordCoverage(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query()
	deep, _, err := parseBoolPtr(query.Get("deep"))
	if err != nil {
		writeJSON(w, http.StatusBadRequest, Failure(ErrorCodeBadRequest, "invalid deep", "STORE_INTEL_REQUEST_INVALID"))
		return
	}
	req := dto.KeywordCoverageRequest{
		AppID:   query.Get("app_id"),
		Country: query.Get("country"),
		Lang:    query.Get("lang"),
	}
	if deep != nil {
		req.Deep = *deep
	}
	result, err := h.service.LatestKeywordCoverage(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) keywordCoverageStream(w http.ResponseWriter, r *http.Request) {
	var req dto.KeywordCoverageRequest
	if !decodeBody(w, r, &req) {
		return
	}
	flusher, ok := w.(http.Flusher)
	if !ok {
		writeJSON(w, http.StatusInternalServerError, Failure(ErrorCodeInternalFailure, "streaming is not supported", "STORE_INTEL_STREAM_UNSUPPORTED"))
		return
	}
	w.Header().Set("Content-Type", "application/x-ndjson; charset=utf-8")
	w.Header().Set("Cache-Control", "no-cache")

	type resultEvent struct {
		result dto.KeywordCoverageResponse
		err    error
	}
	progressCh := make(chan coverageStreamEvent, 32)
	resultCh := make(chan resultEvent, 1)
	go func() {
		result, err := h.service.AnalyzeKeywordCoverageWithProgress(
			r.Context(),
			req,
			func(message string, fraction float64) {
				select {
				case progressCh <- coverageStreamEvent{Type: "progress", Message: message, Fraction: fraction}:
				case <-r.Context().Done():
				}
			},
		)
		close(progressCh)
		resultCh <- resultEvent{result: result, err: err}
	}()

	for {
		select {
		case event, ok := <-progressCh:
			if ok {
				writeCoverageStreamEvent(w, flusher, event)
			} else {
				progressCh = nil
			}
		case result := <-resultCh:
			if progressCh != nil {
				for event := range progressCh {
					writeCoverageStreamEvent(w, flusher, event)
				}
			}
			if result.err != nil {
				writeCoverageStreamEvent(w, flusher, coverageStreamEvent{
					Type:    "error",
					Message: result.err.Error(),
				})
			} else {
				writeCoverageStreamEvent(w, flusher, coverageStreamEvent{
					Type: "result",
					Data: &result.result,
				})
			}
			return
		case <-r.Context().Done():
			return
		}
	}
}

func (h *HTTPHandler) fetchReviews(w http.ResponseWriter, r *http.Request) {
	appID, ok := reviewPathAppID(w, r)
	if !ok {
		return
	}
	query := r.URL.Query()
	result, err := h.service.FetchReviews(r.Context(), dto.FetchReviewsRequest{
		AppID:             appID,
		Country:           query.Get("country"),
		Lang:              query.Get("lang"),
		Sort:              query.Get("sort"),
		Limit:             parseInt(query.Get("limit")),
		ContinuationToken: coalesceQuery(query, "continuation_token", "next_token"),
	})
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) saveReviews(w http.ResponseWriter, r *http.Request) {
	appID, ok := reviewPathAppID(w, r)
	if !ok {
		return
	}
	var req dto.SaveReviewsRequest
	if !decodeBody(w, r, &req) {
		return
	}
	req.AppID = appID
	result, err := h.service.SaveReviews(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) listCachedReviews(w http.ResponseWriter, r *http.Request) {
	appID, ok := reviewPathAppID(w, r)
	if !ok {
		return
	}
	result, err := h.service.ListCachedReviews(r.Context(), dto.ListCachedReviewsRequest{
		AppID: appID,
		Limit: parseInt(r.URL.Query().Get("limit")),
	})
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) similarApps(w http.ResponseWriter, r *http.Request) {
	appID, ok := reviewPathAppID(w, r)
	if !ok {
		return
	}
	query := r.URL.Query()
	result, err := h.service.SimilarApps(r.Context(), dto.SimilarAppsRequest{
		AppID:   appID,
		Country: query.Get("country"),
		Lang:    query.Get("lang"),
		Limit:   parseInt(query.Get("limit")),
	})
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) appPermissions(w http.ResponseWriter, r *http.Request) {
	appID, ok := reviewPathAppID(w, r)
	if !ok {
		return
	}
	query := r.URL.Query()
	result, err := h.service.GetAppPermissions(r.Context(), dto.AppPermissionsRequest{
		AppID:   appID,
		Country: query.Get("country"),
		Lang:    query.Get("lang"),
	})
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) listTrackedApps(w http.ResponseWriter, r *http.Request) {
	enabled, ok, err := parseBoolPtr(r.URL.Query().Get("enabled"))
	if err != nil {
		writeJSON(w, http.StatusBadRequest, Failure(ErrorCodeBadRequest, "invalid enabled", "STORE_INTEL_REQUEST_INVALID"))
		return
	}
	req := dto.ListTrackedAppsRequest{}
	if ok {
		req.Enabled = enabled
	}
	result, err := h.service.ListTrackedApps(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) addTrackedApp(w http.ResponseWriter, r *http.Request) {
	var req dto.AddTrackedAppRequest
	if !decodeBody(w, r, &req) {
		return
	}
	result, err := h.service.AddTrackedApp(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) removeTrackedApp(w http.ResponseWriter, r *http.Request) {
	var req dto.RemoveTrackedAppRequest
	if !decodeBody(w, r, &req) {
		return
	}
	result, err := h.service.RemoveTrackedApp(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) setTrackedAppEnabled(w http.ResponseWriter, r *http.Request) {
	var req dto.SetTrackedAppEnabledRequest
	if !decodeBody(w, r, &req) {
		return
	}
	result, err := h.service.SetTrackedAppEnabled(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) setTrackedAppFrequency(w http.ResponseWriter, r *http.Request) {
	var req dto.SetTrackedAppFrequencyRequest
	if !decodeBody(w, r, &req) {
		return
	}
	result, err := h.service.SetTrackedAppFrequency(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) setTrackedAppTag(w http.ResponseWriter, r *http.Request) {
	var req dto.SetTrackedAppTagRequest
	if !decodeBody(w, r, &req) {
		return
	}
	result, err := h.service.SetTrackedAppTag(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) listTrackedKeywords(w http.ResponseWriter, r *http.Request) {
	enabled, ok, err := parseBoolPtr(r.URL.Query().Get("enabled"))
	if err != nil {
		writeJSON(w, http.StatusBadRequest, Failure(ErrorCodeBadRequest, "invalid enabled", "STORE_INTEL_REQUEST_INVALID"))
		return
	}
	req := dto.ListTrackedKeywordsRequest{}
	if ok {
		req.Enabled = enabled
	}
	result, err := h.service.ListTrackedKeywords(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) addTrackedKeyword(w http.ResponseWriter, r *http.Request) {
	var req dto.AddTrackedKeywordRequest
	if !decodeBody(w, r, &req) {
		return
	}
	result, err := h.service.AddTrackedKeyword(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) removeTrackedKeyword(w http.ResponseWriter, r *http.Request) {
	var req dto.RemoveTrackedKeywordRequest
	if !decodeBody(w, r, &req) {
		return
	}
	result, err := h.service.RemoveTrackedKeyword(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) setTrackedKeywordEnabled(w http.ResponseWriter, r *http.Request) {
	var req dto.SetTrackedKeywordEnabledRequest
	if !decodeBody(w, r, &req) {
		return
	}
	result, err := h.service.SetTrackedKeywordEnabled(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) setTrackedKeywordFrequency(w http.ResponseWriter, r *http.Request) {
	var req dto.SetTrackedKeywordFrequencyRequest
	if !decodeBody(w, r, &req) {
		return
	}
	result, err := h.service.SetTrackedKeywordFrequency(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) syncTrackedKeyword(w http.ResponseWriter, r *http.Request) {
	var req dto.SyncTrackedKeywordRequest
	if !decodeBody(w, r, &req) {
		return
	}
	result, err := h.service.SyncTrackedKeywordNow(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) listTrackedChartApps(w http.ResponseWriter, r *http.Request) {
	enabled, ok, err := parseBoolPtr(r.URL.Query().Get("enabled"))
	if err != nil {
		writeJSON(w, http.StatusBadRequest, Failure(ErrorCodeBadRequest, "invalid enabled", "STORE_INTEL_REQUEST_INVALID"))
		return
	}
	req := dto.ListTrackedChartAppsRequest{}
	if ok {
		req.Enabled = enabled
	}
	result, err := h.service.ListTrackedChartApps(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) addTrackedChartApp(w http.ResponseWriter, r *http.Request) {
	var req dto.AddTrackedChartAppRequest
	if !decodeBody(w, r, &req) {
		return
	}
	result, err := h.service.AddTrackedChartApp(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) removeTrackedChartApp(w http.ResponseWriter, r *http.Request) {
	var req dto.RemoveTrackedChartAppRequest
	if !decodeBody(w, r, &req) {
		return
	}
	result, err := h.service.RemoveTrackedChartApp(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) setTrackedChartAppEnabled(w http.ResponseWriter, r *http.Request) {
	var req dto.SetTrackedChartAppEnabledRequest
	if !decodeBody(w, r, &req) {
		return
	}
	result, err := h.service.SetTrackedChartAppEnabled(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) syncTrackedChartApp(w http.ResponseWriter, r *http.Request) {
	var req dto.SyncTrackedChartAppRequest
	if !decodeBody(w, r, &req) {
		return
	}
	result, err := h.service.SyncTrackedChartAppNow(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) syncAppNow(w http.ResponseWriter, r *http.Request) {
	var req dto.SyncAppNowRequest
	if !decodeBody(w, r, &req) {
		return
	}
	result, err := h.service.SyncAppNow(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) syncAll(w http.ResponseWriter, r *http.Request) {
	var req dto.SyncAllRequest
	if !decodeBody(w, r, &req) {
		return
	}
	result, err := h.service.SyncAll(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) listAlerts(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query()
	isRead, ok, err := parseBoolPtr(query.Get("is_read"))
	if err != nil {
		writeJSON(w, http.StatusBadRequest, Failure(ErrorCodeBadRequest, "invalid is_read", "STORE_INTEL_REQUEST_INVALID"))
		return
	}
	req := dto.ListAlertsRequest{
		AppID:    query.Get("app_id"),
		Type:     query.Get("type"),
		Severity: query.Get("severity"),
		Limit:    parseInt(query.Get("limit")),
	}
	if ok {
		req.IsRead = isRead
	}
	result, err := h.service.ListAlerts(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) markAlertsRead(w http.ResponseWriter, r *http.Request) {
	var req dto.MarkAlertsReadRequest
	if !decodeBody(w, r, &req) {
		return
	}
	result, err := h.service.MarkAlertsRead(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) cleanupHistory(w http.ResponseWriter, r *http.Request) {
	result, err := h.service.CleanupHistory(r.Context())
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) requestRefreshJob(w http.ResponseWriter, r *http.Request) {
	var req dto.RefreshJobRequest
	if !decodeBody(w, r, &req) {
		return
	}
	if h.jobs == nil {
		h.respond(w, r, nil, service.ErrServiceUnavailable)
		return
	}
	result, err := h.jobs.Enqueue(r.Context(), req)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) getRefreshJob(w http.ResponseWriter, r *http.Request) {
	if h.jobs == nil {
		h.respond(w, r, nil, service.ErrServiceUnavailable)
		return
	}
	jobID := strings.TrimPrefix(r.URL.Path, "/api/store-intel/refresh-jobs/")
	result, err := h.jobs.Get(r.Context(), jobID)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) getSettings(w http.ResponseWriter, r *http.Request) {
	result, err := h.service.GetSettings(r.Context())
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) setSettings(w http.ResponseWriter, r *http.Request) {
	values, ok := decodeSettingsBody(w, r)
	if !ok {
		return
	}
	result, err := h.service.SetSettings(r.Context(), values)
	h.respond(w, r, result, err)
}

func (h *HTTPHandler) respond(w http.ResponseWriter, r *http.Request, data any, err error) {
	ctx := requestContext(r)
	if err != nil {
		httpStatus, code, message, errorCode := MapServiceError(err)
		writeJSON(w, httpStatus, FailureWithContext(code, message, errorCode, ctx))
		return
	}
	writeJSON(w, http.StatusOK, SuccessWithContext(data, ctx))
}

func decodeBody(w http.ResponseWriter, r *http.Request, dst any) bool {
	defer r.Body.Close()
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, maxRequestBodyBytes))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(dst); err != nil && !errors.Is(err, io.EOF) {
		writeJSON(w, http.StatusBadRequest, Failure(ErrorCodeBadRequest, "invalid json body", "STORE_INTEL_REQUEST_INVALID"))
		return false
	}
	return true
}

func decodeSettingsBody(w http.ResponseWriter, r *http.Request) (map[string]string, bool) {
	defer r.Body.Close()
	var raw map[string]any
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, maxRequestBodyBytes))
	if err := decoder.Decode(&raw); err != nil {
		if errors.Is(err, io.EOF) {
			return map[string]string{}, true
		}
		writeJSON(w, http.StatusBadRequest, Failure(ErrorCodeBadRequest, "invalid json body", "STORE_INTEL_REQUEST_INVALID"))
		return nil, false
	}
	if nested, ok := raw["values"]; ok && len(raw) == 1 {
		nestedMap, ok := nested.(map[string]any)
		if !ok {
			writeJSON(w, http.StatusBadRequest, Failure(ErrorCodeBadRequest, "invalid settings values", "STORE_INTEL_REQUEST_INVALID"))
			return nil, false
		}
		raw = nestedMap
	}
	values := make(map[string]string, len(raw))
	for key, value := range raw {
		switch typed := value.(type) {
		case nil:
			values[key] = ""
		case string:
			values[key] = typed
		default:
			writeJSON(w, http.StatusBadRequest, Failure(ErrorCodeBadRequest, "settings values must be strings", "STORE_INTEL_REQUEST_INVALID"))
			return nil, false
		}
	}
	return values, true
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

type coverageStreamEvent struct {
	Type     string                       `json:"type"`
	Message  string                       `json:"message,omitempty"`
	Fraction float64                      `json:"fraction,omitempty"`
	Data     *dto.KeywordCoverageResponse `json:"data,omitempty"`
}

func writeCoverageStreamEvent(w http.ResponseWriter, flusher http.Flusher, event coverageStreamEvent) {
	_ = json.NewEncoder(w).Encode(event)
	flusher.Flush()
}

func requestContext(r *http.Request) dto.RequestContext {
	return dto.RequestContext{
		RequestID: r.Header.Get("X-Request-ID"),
		TraceID:   r.Header.Get("X-Trace-ID"),
	}
}

func parseInt(value string) int {
	parsed, err := strconv.Atoi(strings.TrimSpace(value))
	if err != nil {
		return 0
	}
	return parsed
}

func parseBoolPtr(value string) (*bool, bool, error) {
	value = strings.TrimSpace(value)
	if value == "" {
		return nil, false, nil
	}
	parsed, err := strconv.ParseBool(value)
	if err != nil {
		return nil, false, err
	}
	return &parsed, true, nil
}

func coalesceQuery(query url.Values, keys ...string) string {
	for _, key := range keys {
		if value := strings.TrimSpace(query.Get(key)); value != "" {
			return value
		}
	}
	return ""
}

func appReviewsPathKind(path string) string {
	const prefix = "/api/store-intel/apps/"
	if !strings.HasPrefix(path, prefix) {
		return ""
	}
	parts := strings.Split(strings.TrimPrefix(path, prefix), "/")
	if len(parts) == 2 && parts[0] != "" && parts[1] == "reviews" {
		return "reviews"
	}
	if len(parts) == 3 && parts[0] != "" && parts[1] == "reviews" && parts[2] == "cache" {
		return "cache"
	}
	return ""
}

func appSimilarPath(path string) bool {
	const prefix = "/api/store-intel/apps/"
	if !strings.HasPrefix(path, prefix) {
		return false
	}
	parts := strings.Split(strings.TrimPrefix(path, prefix), "/")
	return len(parts) == 2 && parts[0] != "" && parts[1] == "similar"
}

func appPermissionsPath(path string) bool {
	const prefix = "/api/store-intel/apps/"
	if !strings.HasPrefix(path, prefix) {
		return false
	}
	parts := strings.Split(strings.TrimPrefix(path, prefix), "/")
	return len(parts) == 2 && parts[0] != "" && parts[1] == "permissions"
}

func appCachePath(path string) bool {
	const prefix = "/api/store-intel/apps/"
	if !strings.HasPrefix(path, prefix) {
		return false
	}
	parts := strings.Split(strings.TrimPrefix(path, prefix), "/")
	return len(parts) == 2 && parts[0] != "" && parts[1] == "cache"
}

func appPathAppID(w http.ResponseWriter, r *http.Request, suffix string) (string, bool) {
	const prefix = "/api/store-intel/apps/"
	parts := strings.Split(strings.TrimPrefix(r.URL.Path, prefix), "/")
	if len(parts) != 2 || parts[0] == "" || parts[1] != suffix {
		writeJSON(w, http.StatusBadRequest, Failure(ErrorCodeBadRequest, "invalid app_id", "STORE_INTEL_REQUEST_INVALID"))
		return "", false
	}
	appID, err := url.PathUnescape(parts[0])
	if err != nil || strings.TrimSpace(appID) == "" {
		writeJSON(w, http.StatusBadRequest, Failure(ErrorCodeBadRequest, "invalid app_id", "STORE_INTEL_REQUEST_INVALID"))
		return "", false
	}
	return appID, true
}

func reviewPathAppID(w http.ResponseWriter, r *http.Request) (string, bool) {
	const prefix = "/api/store-intel/apps/"
	parts := strings.Split(strings.TrimPrefix(r.URL.Path, prefix), "/")
	if len(parts) < 2 || parts[0] == "" {
		writeJSON(w, http.StatusBadRequest, Failure(ErrorCodeBadRequest, "invalid app_id", "STORE_INTEL_REQUEST_INVALID"))
		return "", false
	}
	appID, err := url.PathUnescape(parts[0])
	if err != nil || strings.TrimSpace(appID) == "" {
		writeJSON(w, http.StatusBadRequest, Failure(ErrorCodeBadRequest, "invalid app_id", "STORE_INTEL_REQUEST_INVALID"))
		return "", false
	}
	return appID, true
}
