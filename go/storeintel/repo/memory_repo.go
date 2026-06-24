package repo

import (
	"context"
	"sort"
	"strings"
	"sync"

	"github.com/catch-radar/storeintel/dto"
)

type MemoryRepo struct {
	mu               sync.Mutex
	nextTrackedID    uint64
	nextKeywordID    uint64
	nextChartAppID   uint64
	nextAlertID      uint64
	settings         map[string]string
	refreshJobs      map[string]dto.RefreshJobResponse
	refreshJobReqs   map[string]dto.RefreshJobRequest
	refreshJobLocks  map[string]string
	cachedApps       map[string]dto.AppSummary
	trackedApps      map[string]dto.TrackedApp
	trackedKeywords  map[string]dto.TrackedKeyword
	trackedChartApps map[string]dto.TrackedChartApp
	snapshots        map[string][]SnapshotRecord
	chartSnapshots   []dto.ChartItem
	chartRanks       []dto.ChartRankResponse
	keywordRanks     []dto.KeywordRankSnapshot
	keywordCorpus    map[string]KeywordCorpusItem
	keywordCoverage  []dto.KeywordCoverageResponse
	reviews          []dto.ReviewItem
	alerts           []dto.Alert
}

func NewMemoryRepo() *MemoryRepo {
	return &MemoryRepo{
		nextTrackedID:    1,
		nextKeywordID:    1,
		nextChartAppID:   1,
		nextAlertID:      1,
		settings:         map[string]string{},
		refreshJobs:      map[string]dto.RefreshJobResponse{},
		refreshJobReqs:   map[string]dto.RefreshJobRequest{},
		refreshJobLocks:  map[string]string{},
		cachedApps:       map[string]dto.AppSummary{},
		trackedApps:      map[string]dto.TrackedApp{},
		trackedKeywords:  map[string]dto.TrackedKeyword{},
		trackedChartApps: map[string]dto.TrackedChartApp{},
		snapshots:        map[string][]SnapshotRecord{},
		keywordCorpus:    map[string]KeywordCorpusItem{},
	}
}

func (r *MemoryRepo) ListSettings(_ context.Context) (map[string]string, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	values := make(map[string]string, len(r.settings))
	for key, value := range r.settings {
		values[key] = value
	}
	return values, nil
}

func (r *MemoryRepo) UpsertSettings(_ context.Context, values map[string]string, _ string) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	if r.settings == nil {
		r.settings = map[string]string{}
	}
	for key, value := range values {
		r.settings[key] = value
	}
	return nil
}

func (r *MemoryRepo) AcquireSettingValue(_ context.Context, key, value, _ string) (bool, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	key = strings.TrimSpace(key)
	if key == "" {
		return false, nil
	}
	if r.settings == nil {
		r.settings = map[string]string{}
	}
	if r.settings[key] == value {
		return false, nil
	}
	r.settings[key] = value
	return true, nil
}

func (r *MemoryRepo) CreateRefreshJob(_ context.Context, input RefreshJobCreateInput) (dto.RefreshJobResponse, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	if r.refreshJobs == nil {
		r.refreshJobs = map[string]dto.RefreshJobResponse{}
	}
	if r.refreshJobReqs == nil {
		r.refreshJobReqs = map[string]dto.RefreshJobRequest{}
	}
	job := input.Job
	if strings.TrimSpace(job.JobID) == "" {
		return dto.RefreshJobResponse{}, ErrNotFound
	}
	r.refreshJobs[job.JobID] = job
	r.refreshJobReqs[job.JobID] = input.Request
	return job, nil
}

func (r *MemoryRepo) UpdateRefreshJob(_ context.Context, input RefreshJobUpdateInput) (dto.RefreshJobResponse, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	if r.refreshJobs == nil {
		return dto.RefreshJobResponse{}, ErrNotFound
	}
	job, ok := r.refreshJobs[strings.TrimSpace(input.JobID)]
	if !ok {
		return dto.RefreshJobResponse{}, ErrNotFound
	}
	if strings.TrimSpace(input.Status) != "" {
		job.Status = strings.TrimSpace(input.Status)
	}
	job.Message = input.Message
	if strings.TrimSpace(input.StartedAt) != "" {
		job.StartedAt = strings.TrimSpace(input.StartedAt)
	}
	if strings.TrimSpace(input.FinishedAt) != "" {
		job.FinishedAt = strings.TrimSpace(input.FinishedAt)
	}
	if strings.TrimSpace(input.UpdatedAt) != "" {
		job.UpdatedAt = strings.TrimSpace(input.UpdatedAt)
	}
	r.refreshJobs[job.JobID] = job
	if job.Status == "completed" || job.Status == "failed" {
		delete(r.refreshJobLocks, job.JobID)
	}
	return job, nil
}

func (r *MemoryRepo) GetRefreshJob(_ context.Context, jobID string) (dto.RefreshJobResponse, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	if r.refreshJobs == nil {
		return dto.RefreshJobResponse{}, ErrNotFound
	}
	job, ok := r.refreshJobs[strings.TrimSpace(jobID)]
	if !ok {
		return dto.RefreshJobResponse{}, ErrNotFound
	}
	return job, nil
}

func (r *MemoryRepo) ListRefreshJobs(_ context.Context, filter RefreshJobListFilter) ([]dto.RefreshJobRecord, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	statuses := map[string]bool{}
	for _, status := range filter.Statuses {
		status = strings.TrimSpace(status)
		if status != "" {
			statuses[status] = true
		}
	}
	limit := filter.Limit
	if limit <= 0 {
		limit = 100
	}
	records := make([]dto.RefreshJobRecord, 0, len(r.refreshJobs))
	for jobID, job := range r.refreshJobs {
		if len(statuses) > 0 && !statuses[job.Status] {
			continue
		}
		records = append(records, dto.RefreshJobRecord{
			Job:     job,
			Request: r.refreshJobReqs[jobID],
		})
	}
	sort.Slice(records, func(i, j int) bool {
		left := records[i].Job.UpdatedAt
		if left == "" {
			left = records[i].Job.RequestedAt
		}
		right := records[j].Job.UpdatedAt
		if right == "" {
			right = records[j].Job.RequestedAt
		}
		return left < right
	})
	if len(records) > limit {
		records = records[:limit]
	}
	return records, nil
}

func (r *MemoryRepo) ClaimRefreshJob(_ context.Context, input RefreshJobClaimInput) (dto.RefreshJobResponse, bool, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	job, ok := r.refreshJobs[strings.TrimSpace(input.JobID)]
	if !ok {
		return dto.RefreshJobResponse{}, false, ErrNotFound
	}
	if job.Status != "queued" && job.Status != "running" {
		return job, false, nil
	}
	job.Status = "running"
	job.Message = "服务器正在后台刷新。"
	if strings.TrimSpace(input.StartedAt) != "" {
		job.StartedAt = strings.TrimSpace(input.StartedAt)
	}
	if strings.TrimSpace(input.UpdatedAt) != "" {
		job.UpdatedAt = strings.TrimSpace(input.UpdatedAt)
	}
	if r.refreshJobLocks == nil {
		r.refreshJobLocks = map[string]string{}
	}
	r.refreshJobLocks[job.JobID] = strings.TrimSpace(input.LockedUntil)
	r.refreshJobs[job.JobID] = job
	return job, true, nil
}

func (r *MemoryRepo) UpsertTrackedApp(_ context.Context, input TrackedAppInput) (dto.TrackedApp, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	key := identityKey(input.Identity)
	item, ok := r.trackedApps[key]
	if !ok {
		item = dto.TrackedApp{
			ID:        r.nextTrackedID,
			Platform:  input.Identity.Platform,
			AppID:     input.Identity.AppID,
			Country:   input.Identity.Country,
			Lang:      input.Identity.Lang,
			CreatedAt: input.NowISO,
		}
		r.nextTrackedID++
	}
	item.Title = coalesce(input.Title, item.Title)
	item.Frequency = coalesce(input.Frequency, item.Frequency, "daily")
	item.Tag = input.Tag
	item.Enabled = input.Enabled
	item.UpdatedAt = input.NowISO
	r.trackedApps[key] = item
	return item, nil
}

func (r *MemoryRepo) ListTrackedApps(_ context.Context, filter TrackedAppFilter) ([]dto.TrackedApp, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	items := make([]dto.TrackedApp, 0, len(r.trackedApps))
	for _, item := range r.trackedApps {
		if filter.Enabled != nil && item.Enabled != *filter.Enabled {
			continue
		}
		items = append(items, item)
	}
	sort.Slice(items, func(i, j int) bool {
		return items[i].CreatedAt > items[j].CreatedAt
	})
	return items, nil
}

func (r *MemoryRepo) RemoveTrackedApp(_ context.Context, identity dto.AppIdentity) (int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	key := identityKey(identity)
	if _, ok := r.trackedApps[key]; !ok {
		return 0, nil
	}
	delete(r.trackedApps, key)
	return 1, nil
}

func (r *MemoryRepo) SetTrackedAppEnabled(_ context.Context, identity dto.AppIdentity, enabled bool, updatedAt string) (bool, int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	key := identityKey(identity)
	item, ok := r.trackedApps[key]
	if !ok {
		return enabled, 0, nil
	}
	item.Enabled = enabled
	item.UpdatedAt = updatedAt
	r.trackedApps[key] = item
	return item.Enabled, 1, nil
}

func (r *MemoryRepo) SetTrackedAppFrequency(_ context.Context, identity dto.AppIdentity, frequency, updatedAt string) (string, int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	key := identityKey(identity)
	item, ok := r.trackedApps[key]
	if !ok {
		return frequency, 0, nil
	}
	item.Frequency = frequency
	item.UpdatedAt = updatedAt
	r.trackedApps[key] = item
	return item.Frequency, 1, nil
}

func (r *MemoryRepo) SetTrackedAppTag(_ context.Context, identity dto.AppIdentity, tag, updatedAt string) (string, int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	key := identityKey(identity)
	item, ok := r.trackedApps[key]
	if !ok {
		return "", 0, nil
	}
	item.Tag = strings.TrimSpace(tag)
	item.UpdatedAt = updatedAt
	r.trackedApps[key] = item
	return item.Tag, 1, nil
}

func (r *MemoryRepo) UpdateTrackedAppSyncSuccess(_ context.Context, identity dto.AppIdentity, syncedAt string) (int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	key := identityKey(identity)
	item, ok := r.trackedApps[key]
	if !ok {
		return 0, ErrNotFound
	}
	priorFailures := item.ConsecutiveFailures
	item.LastSyncedAt = syncedAt
	item.ConsecutiveFailures = 0
	item.LastFailedAt = ""
	item.UpdatedAt = syncedAt
	r.trackedApps[key] = item
	return priorFailures, nil
}

func (r *MemoryRepo) RecordTrackedAppFailure(_ context.Context, identity dto.AppIdentity, failedAt, _ string) (int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	key := identityKey(identity)
	item, ok := r.trackedApps[key]
	if !ok {
		return 0, ErrNotFound
	}
	item.ConsecutiveFailures++
	item.LastFailedAt = failedAt
	item.UpdatedAt = failedAt
	r.trackedApps[key] = item
	return item.ConsecutiveFailures, nil
}

func (r *MemoryRepo) UpsertCachedApps(_ context.Context, input CachedAppsUpsertInput) (int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	if r.cachedApps == nil {
		r.cachedApps = map[string]dto.AppSummary{}
	}
	platform := coalesce(input.Platform, dto.PlatformGooglePlay)
	country := strings.ToLower(coalesce(input.Country, "us"))
	lang := strings.ToLower(coalesce(input.Lang, "en"))
	saved := 0
	for _, item := range input.Items {
		item.Platform = coalesce(item.Platform, platform)
		item.AppID = strings.TrimSpace(item.AppID)
		if item.AppID == "" {
			continue
		}
		item.Raw = ensureRawWithCachedLocale(item.Raw, country, lang, input.UpdatedAt)
		r.cachedApps[cachedAppKey(item.Platform, item.AppID, country, lang)] = item
		saved++
	}
	return saved, nil
}

func (r *MemoryRepo) SearchCachedApps(_ context.Context, filter CachedAppSearchFilter) ([]dto.AppSummary, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	filter.Platform = coalesce(filter.Platform, dto.PlatformGooglePlay)
	filter.Query = strings.ToLower(strings.TrimSpace(filter.Query))
	filter.Country = strings.ToLower(coalesce(filter.Country, "us"))
	filter.Lang = strings.ToLower(coalesce(filter.Lang, "en"))
	if filter.Limit <= 0 {
		filter.Limit = 50
	}
	items := make([]dto.AppSummary, 0, len(r.cachedApps))
	for key, item := range r.cachedApps {
		if !strings.HasPrefix(key, filter.Platform+"|") || !strings.HasSuffix(key, "|"+filter.Country+"|"+filter.Lang) {
			continue
		}
		identity := normalizeIdentity(dto.AppIdentity{
			Platform: item.Platform,
			AppID:    item.AppID,
			Country:  filter.Country,
			Lang:     filter.Lang,
		})
		history := r.snapshots[identityKey(identity)]
		if len(history) > 0 {
			latest := history[0]
			for _, record := range history[1:] {
				if record.CapturedAt > latest.CapturedAt {
					latest = record
				}
			}
			item = mergeCachedAppSnapshot(item, latest, filter.Country, filter.Lang)
		}
		if !appSummaryMatches(item, filter.Query) {
			continue
		}
		items = append(items, item)
	}
	sort.Slice(items, func(i, j int) bool {
		left := cachedUpdatedAt(items[i])
		right := cachedUpdatedAt(items[j])
		if left == right {
			return items[i].Title < items[j].Title
		}
		return left > right
	})
	if len(items) > filter.Limit {
		items = items[:filter.Limit]
	}
	return items, nil
}

func (r *MemoryRepo) UpsertTrackedKeyword(_ context.Context, input TrackedKeywordInput) (dto.TrackedKeyword, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	input = normalizeTrackedKeywordInput(input)
	key := trackedKeywordKey(input)
	item, ok := r.trackedKeywords[key]
	if !ok {
		item = dto.TrackedKeyword{
			ID:        r.nextKeywordID,
			Platform:  input.Platform,
			Keyword:   input.Keyword,
			AppID:     input.AppID,
			Country:   input.Country,
			Lang:      input.Lang,
			CreatedAt: input.NowISO,
		}
		r.nextKeywordID++
	}
	item.Frequency = coalesce(input.Frequency, item.Frequency, "daily")
	item.Enabled = input.Enabled
	item.UpdatedAt = input.NowISO
	r.trackedKeywords[key] = item
	return item, nil
}

func (r *MemoryRepo) ListTrackedKeywords(_ context.Context, filter TrackedMonitorFilter) ([]dto.TrackedKeyword, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	items := make([]dto.TrackedKeyword, 0, len(r.trackedKeywords))
	for _, item := range r.trackedKeywords {
		if filter.Enabled != nil && item.Enabled != *filter.Enabled {
			continue
		}
		items = append(items, item)
	}
	sort.Slice(items, func(i, j int) bool {
		return items[i].UpdatedAt > items[j].UpdatedAt
	})
	return items, nil
}

func (r *MemoryRepo) RemoveTrackedKeyword(_ context.Context, input TrackedKeywordInput) (int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	key := trackedKeywordKey(normalizeTrackedKeywordInput(input))
	if _, ok := r.trackedKeywords[key]; !ok {
		return 0, nil
	}
	delete(r.trackedKeywords, key)
	return 1, nil
}

func (r *MemoryRepo) SetTrackedKeywordEnabled(_ context.Context, input TrackedKeywordInput, enabled bool, updatedAt string) (bool, int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	key := trackedKeywordKey(normalizeTrackedKeywordInput(input))
	item, ok := r.trackedKeywords[key]
	if !ok {
		return enabled, 0, nil
	}
	item.Enabled = enabled
	item.UpdatedAt = updatedAt
	r.trackedKeywords[key] = item
	return item.Enabled, 1, nil
}

func (r *MemoryRepo) SetTrackedKeywordFrequency(_ context.Context, input TrackedKeywordInput, frequency, updatedAt string) (string, int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	key := trackedKeywordKey(normalizeTrackedKeywordInput(input))
	item, ok := r.trackedKeywords[key]
	if !ok {
		return frequency, 0, nil
	}
	item.Frequency = frequency
	item.UpdatedAt = updatedAt
	r.trackedKeywords[key] = item
	return item.Frequency, 1, nil
}

func (r *MemoryRepo) UpdateTrackedKeywordSyncSuccess(_ context.Context, input TrackedKeywordInput, syncedAt string) (int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	key := trackedKeywordKey(normalizeTrackedKeywordInput(input))
	item, ok := r.trackedKeywords[key]
	if !ok {
		return 0, ErrNotFound
	}
	priorFailures := item.ConsecutiveFailures
	item.LastSyncedAt = syncedAt
	item.ConsecutiveFailures = 0
	item.LastFailedAt = ""
	item.UpdatedAt = syncedAt
	r.trackedKeywords[key] = item
	return priorFailures, nil
}

func (r *MemoryRepo) RecordTrackedKeywordFailure(_ context.Context, input TrackedKeywordInput, failedAt, _ string) (int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	key := trackedKeywordKey(normalizeTrackedKeywordInput(input))
	item, ok := r.trackedKeywords[key]
	if !ok {
		return 0, ErrNotFound
	}
	item.ConsecutiveFailures++
	item.LastFailedAt = failedAt
	item.UpdatedAt = failedAt
	r.trackedKeywords[key] = item
	return item.ConsecutiveFailures, nil
}

func (r *MemoryRepo) UpsertTrackedChartApp(_ context.Context, input TrackedChartAppInput) (dto.TrackedChartApp, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	input = normalizeTrackedChartAppInput(input)
	key := trackedChartAppKey(input)
	item, ok := r.trackedChartApps[key]
	if !ok {
		item = dto.TrackedChartApp{
			ID:         r.nextChartAppID,
			Platform:   input.Platform,
			AppID:      input.AppID,
			Collection: input.Collection,
			Category:   input.Category,
			Country:    input.Country,
			Lang:       input.Lang,
			CreatedAt:  input.NowISO,
		}
		r.nextChartAppID++
	}
	item.Frequency = coalesce(input.Frequency, item.Frequency, "daily")
	item.Enabled = input.Enabled
	item.UpdatedAt = input.NowISO
	r.trackedChartApps[key] = item
	return item, nil
}

func (r *MemoryRepo) ListTrackedChartApps(_ context.Context, filter TrackedMonitorFilter) ([]dto.TrackedChartApp, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	items := make([]dto.TrackedChartApp, 0, len(r.trackedChartApps))
	for _, item := range r.trackedChartApps {
		if filter.Enabled != nil && item.Enabled != *filter.Enabled {
			continue
		}
		items = append(items, item)
	}
	sort.Slice(items, func(i, j int) bool {
		return items[i].UpdatedAt > items[j].UpdatedAt
	})
	return items, nil
}

func (r *MemoryRepo) RemoveTrackedChartApp(_ context.Context, input TrackedChartAppInput) (int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	key := trackedChartAppKey(normalizeTrackedChartAppInput(input))
	if _, ok := r.trackedChartApps[key]; !ok {
		return 0, nil
	}
	delete(r.trackedChartApps, key)
	return 1, nil
}

func (r *MemoryRepo) SetTrackedChartAppEnabled(_ context.Context, input TrackedChartAppInput, enabled bool, updatedAt string) (bool, int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	key := trackedChartAppKey(normalizeTrackedChartAppInput(input))
	item, ok := r.trackedChartApps[key]
	if !ok {
		return enabled, 0, nil
	}
	item.Enabled = enabled
	item.UpdatedAt = updatedAt
	r.trackedChartApps[key] = item
	return item.Enabled, 1, nil
}

func (r *MemoryRepo) UpdateTrackedChartAppSyncSuccess(_ context.Context, input TrackedChartAppInput, syncedAt string) (int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	key := trackedChartAppKey(normalizeTrackedChartAppInput(input))
	item, ok := r.trackedChartApps[key]
	if !ok {
		return 0, ErrNotFound
	}
	priorFailures := item.ConsecutiveFailures
	item.LastSyncedAt = syncedAt
	item.ConsecutiveFailures = 0
	item.LastFailedAt = ""
	item.UpdatedAt = syncedAt
	r.trackedChartApps[key] = item
	return priorFailures, nil
}

func (r *MemoryRepo) RecordTrackedChartAppFailure(_ context.Context, input TrackedChartAppInput, failedAt, _ string) (int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	key := trackedChartAppKey(normalizeTrackedChartAppInput(input))
	item, ok := r.trackedChartApps[key]
	if !ok {
		return 0, ErrNotFound
	}
	item.ConsecutiveFailures++
	item.LastFailedAt = failedAt
	item.UpdatedAt = failedAt
	r.trackedChartApps[key] = item
	return item.ConsecutiveFailures, nil
}

func (r *MemoryRepo) UpsertAppSnapshot(_ context.Context, input SnapshotUpsertInput) (SnapshotUpsertResult, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	identity := normalizeIdentity(dto.AppIdentity{
		Platform: coalesce(input.Detail.Platform, dto.PlatformGooglePlay),
		AppID:    input.Detail.AppID,
		Country:  input.Country,
		Lang:     input.Lang,
	})
	key := identityKey(identity)
	day := dayKey(input.CapturedAt)
	current := SnapshotRecord{
		Identity:     identity,
		CapturedAt:   input.CapturedAt,
		Title:        input.Detail.Title,
		Rating:       input.Detail.Rating,
		RatingsCount: input.Detail.RatingsCount,
		ReviewsCount: input.Detail.ReviewsCount,
		Installs:     input.Detail.Installs,
		MinInstalls:  input.Detail.MinInstalls,
		RealInstalls: input.Detail.RealInstalls,
		Version:      input.Detail.Version,
		Raw:          input.Detail,
	}
	history := r.snapshots[key]
	var previous *SnapshotRecord
	firstOfDay := true
	for i := len(history) - 1; i >= 0; i-- {
		if previous == nil && dayKey(history[i].CapturedAt) != day {
			copy := history[i]
			previous = &copy
		}
		if dayKey(history[i].CapturedAt) == day {
			history[i] = current
			firstOfDay = false
			r.snapshots[key] = history
			return SnapshotUpsertResult{Previous: previous, Current: current, FirstOfDay: firstOfDay}, nil
		}
	}
	history = append(history, current)
	r.snapshots[key] = history
	return SnapshotUpsertResult{Previous: previous, Current: current, FirstOfDay: firstOfDay}, nil
}

func (r *MemoryRepo) LatestAppSnapshot(_ context.Context, filter LatestAppSnapshotFilter) (SnapshotRecord, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	identity := normalizeIdentity(dto.AppIdentity{
		Platform: filter.Platform,
		AppID:    strings.TrimSpace(filter.AppID),
		Country:  filter.Country,
		Lang:     filter.Lang,
	})
	history := append([]SnapshotRecord{}, r.snapshots[identityKey(identity)]...)
	if len(history) == 0 {
		return SnapshotRecord{}, ErrNotFound
	}
	sort.Slice(history, func(i, j int) bool {
		return history[i].CapturedAt > history[j].CapturedAt
	})
	return history[0], nil
}

func (r *MemoryRepo) ListAppSnapshotHistory(_ context.Context, filter AppSnapshotHistoryFilter) ([]dto.AppSnapshot, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	identity := normalizeIdentity(dto.AppIdentity{
		Platform: filter.Platform,
		AppID:    strings.TrimSpace(filter.AppID),
		Country:  filter.Country,
		Lang:     filter.Lang,
	})
	history := append([]SnapshotRecord{}, r.snapshots[identityKey(identity)]...)
	sort.Slice(history, func(i, j int) bool {
		return history[i].CapturedAt < history[j].CapturedAt
	})
	if filter.Limit > 0 && len(history) > filter.Limit {
		history = history[len(history)-filter.Limit:]
	}
	items := make([]dto.AppSnapshot, 0, len(history))
	for _, record := range history {
		items = append(items, record.DTO())
	}
	return items, nil
}

func (r *MemoryRepo) ListRecentAppSnapshots(_ context.Context, filter AppSnapshotRecentFilter) ([]dto.AppSnapshot, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	records := make([]SnapshotRecord, 0)
	for _, history := range r.snapshots {
		records = append(records, history...)
	}
	sort.Slice(records, func(i, j int) bool {
		return records[i].CapturedAt > records[j].CapturedAt
	})
	if filter.Limit > 0 && len(records) > filter.Limit {
		records = records[:filter.Limit]
	}
	items := make([]dto.AppSnapshot, 0, len(records))
	for _, record := range records {
		items = append(items, record.DTO())
	}
	return items, nil
}

func (r *MemoryRepo) CountAppSnapshots(_ context.Context) (int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	total := 0
	for _, history := range r.snapshots {
		total += len(history)
	}
	return total, nil
}

func (r *MemoryRepo) SaveChartSnapshot(_ context.Context, input SaveChartSnapshotInput) (int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	for _, item := range input.Items {
		item.Platform = coalesce(item.Platform, dto.PlatformGooglePlay)
		item.ChartType = coalesce(item.ChartType, input.ChartType)
		item.Category = input.Category
		item.Country = strings.ToLower(coalesce(item.Country, input.Country, "us"))
		item.Lang = strings.ToLower(coalesce(item.Lang, input.Lang, "en"))
		item.Raw = ensureRawWithCapturedAt(item.Raw, input.CapturedAt)
		r.chartSnapshots = append(r.chartSnapshots, item)
	}
	return len(input.Items), nil
}

func (r *MemoryRepo) ListLatestChartSnapshot(_ context.Context, filter LatestChartSnapshotFilter) ([]dto.ChartItem, string, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	filter.Platform = coalesce(filter.Platform, dto.PlatformGooglePlay)
	filter.ChartType = coalesce(filter.ChartType, "top_free")
	filter.Category = strings.TrimSpace(filter.Category)
	filter.Country = strings.ToLower(coalesce(filter.Country, "us"))
	filter.Lang = strings.ToLower(coalesce(filter.Lang, "en"))
	if filter.Limit <= 0 {
		filter.Limit = 100
	}
	latest := ""
	for _, item := range r.chartSnapshots {
		if item.Platform != filter.Platform ||
			item.ChartType != filter.ChartType ||
			item.Category != filter.Category ||
			item.Country != filter.Country ||
			item.Lang != filter.Lang {
			continue
		}
		if captured := rawString(item.Raw, "captured_at"); captured > latest {
			latest = captured
		}
	}
	if latest == "" {
		return nil, "", ErrNotFound
	}
	items := []dto.ChartItem{}
	for _, item := range r.chartSnapshots {
		if item.Platform != filter.Platform ||
			item.ChartType != filter.ChartType ||
			item.Category != filter.Category ||
			item.Country != filter.Country ||
			item.Lang != filter.Lang ||
			rawString(item.Raw, "captured_at") != latest {
			continue
		}
		items = append(items, item)
	}
	sort.Slice(items, func(i, j int) bool {
		return items[i].Rank < items[j].Rank
	})
	if len(items) > filter.Limit {
		items = items[:filter.Limit]
	}
	return items, latest, nil
}

func (r *MemoryRepo) UpsertChartRank(_ context.Context, input ChartRankUpsertInput) (dto.ChartRankResponse, bool, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	current := chartRankSnapshot(input)
	for index, item := range r.chartRanks {
		if chartRankSameDay(item, current, input.CapturedDay) {
			r.chartRanks[index] = current
			return current, false, nil
		}
	}
	r.chartRanks = append(r.chartRanks, current)
	return current, true, nil
}

func (r *MemoryRepo) ListChartRankHistory(_ context.Context, filter ChartRankHistoryFilter) ([]dto.ChartRankResponse, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	filter.Platform = coalesce(filter.Platform, dto.PlatformGooglePlay)
	filter.Collection = coalesce(filter.Collection, "top_free")
	filter.Category = coalesce(filter.Category, "APPLICATION")
	filter.Country = strings.ToLower(coalesce(filter.Country, "us"))
	filter.Lang = strings.ToLower(coalesce(filter.Lang, "en"))
	items := make([]dto.ChartRankResponse, 0, len(r.chartRanks))
	for _, item := range r.chartRanks {
		if item.Platform != filter.Platform ||
			item.AppID != filter.AppID ||
			item.Collection != filter.Collection ||
			item.Category != filter.Category ||
			item.Country != filter.Country ||
			item.Lang != filter.Lang {
			continue
		}
		items = append(items, item)
	}
	sort.Slice(items, func(i, j int) bool {
		return items[i].CapturedAt < items[j].CapturedAt
	})
	if filter.Limit > 0 && len(items) > filter.Limit {
		items = items[len(items)-filter.Limit:]
	}
	return items, nil
}

func (r *MemoryRepo) UpsertKeywordRank(_ context.Context, input KeywordRankUpsertInput) (KeywordRankUpsertResult, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	current := keywordRankSnapshot(input)
	for index, item := range r.keywordRanks {
		if keywordRankSameDay(item, current, input.CapturedDay) {
			r.keywordRanks[index] = current
			return KeywordRankUpsertResult{Current: current, FirstOfDay: false}, nil
		}
	}
	r.keywordRanks = append(r.keywordRanks, current)
	return KeywordRankUpsertResult{Current: current, FirstOfDay: true}, nil
}

func (r *MemoryRepo) ListKeywordRankHistory(_ context.Context, filter KeywordRankHistoryFilter) ([]dto.KeywordRankSnapshot, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	filter.Platform = coalesce(filter.Platform, dto.PlatformGooglePlay)
	filter.Country = strings.ToLower(coalesce(filter.Country, "us"))
	filter.Lang = strings.ToLower(coalesce(filter.Lang, "en"))
	items := make([]dto.KeywordRankSnapshot, 0, len(r.keywordRanks))
	for _, item := range r.keywordRanks {
		if item.Platform != filter.Platform ||
			item.Keyword != filter.Keyword ||
			item.AppID != filter.AppID ||
			item.Country != filter.Country ||
			item.Lang != filter.Lang {
			continue
		}
		items = append(items, item)
	}
	sort.Slice(items, func(i, j int) bool {
		return items[i].CapturedAt < items[j].CapturedAt
	})
	if filter.Limit > 0 && len(items) > filter.Limit {
		items = items[len(items)-filter.Limit:]
	}
	return items, nil
}

func (r *MemoryRepo) ListRecentKeywordRanks(_ context.Context, filter KeywordRankRecentFilter) ([]dto.KeywordRankSnapshot, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	filter.Platform = coalesce(filter.Platform, dto.PlatformGooglePlay)
	filter.AppID = strings.TrimSpace(filter.AppID)
	filter.Country = strings.ToLower(strings.TrimSpace(filter.Country))
	filter.Lang = strings.ToLower(strings.TrimSpace(filter.Lang))
	items := make([]dto.KeywordRankSnapshot, 0, len(r.keywordRanks))
	for _, item := range r.keywordRanks {
		if item.Platform != filter.Platform {
			continue
		}
		if filter.AppID != "" && item.AppID != filter.AppID {
			continue
		}
		if filter.Country != "" && item.Country != filter.Country {
			continue
		}
		if filter.Lang != "" && item.Lang != filter.Lang {
			continue
		}
		items = append(items, item)
	}
	sort.Slice(items, func(i, j int) bool {
		return items[i].CapturedAt > items[j].CapturedAt
	})
	if filter.Limit > 0 && len(items) > filter.Limit {
		items = items[:filter.Limit]
	}
	return items, nil
}

func (r *MemoryRepo) RecordKeywordCorpus(_ context.Context, input KeywordCorpusRecordInput) (int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	input = normalizeKeywordCorpusRecordInput(input)
	if r.keywordCorpus == nil {
		r.keywordCorpus = map[string]KeywordCorpusItem{}
	}
	added := 0
	for _, item := range input.Items {
		key := keywordCorpusKey(item.Platform, item.Country, item.Lang, item.Keyword)
		existing, ok := r.keywordCorpus[key]
		if !ok {
			item.HitCount = 1
			item.FirstSeenAt = input.SeenAt
			item.LastSeenAt = input.SeenAt
			r.keywordCorpus[key] = item
			added++
			continue
		}
		existing.HitCount++
		existing.LastSeenAt = input.SeenAt
		if item.Confirmed {
			existing.Confirmed = true
		}
		r.keywordCorpus[key] = existing
	}
	return added, nil
}

func (r *MemoryRepo) ListKeywordCorpus(_ context.Context, filter KeywordCorpusFilter) ([]KeywordCorpusItem, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	filter = normalizeKeywordCorpusFilter(filter)
	items := make([]KeywordCorpusItem, 0, len(r.keywordCorpus))
	for _, item := range r.keywordCorpus {
		if item.Platform != filter.Platform ||
			item.Country != filter.Country ||
			item.Lang != filter.Lang {
			continue
		}
		items = append(items, item)
	}
	sort.Slice(items, func(i, j int) bool {
		if items[i].Confirmed != items[j].Confirmed {
			return items[i].Confirmed
		}
		if items[i].HitCount != items[j].HitCount {
			return items[i].HitCount > items[j].HitCount
		}
		if items[i].LastSeenAt != items[j].LastSeenAt {
			return items[i].LastSeenAt > items[j].LastSeenAt
		}
		return items[i].Keyword < items[j].Keyword
	})
	if len(items) > filter.Limit {
		items = items[:filter.Limit]
	}
	return items, nil
}

func (r *MemoryRepo) UpsertKeywordCoverage(_ context.Context, input KeywordCoverageUpsertInput) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	result := input.Result
	result.Platform = coalesce(result.Platform, dto.PlatformGooglePlay)
	result.AppID = strings.TrimSpace(result.AppID)
	result.Country = strings.ToLower(coalesce(result.Country, "us"))
	result.Lang = strings.ToLower(coalesce(result.Lang, "en"))
	result.CapturedAt = coalesce(input.CapturedAt, result.CapturedAt)
	if result.CandidateCount == 0 {
		result.CandidateCount = len(result.Candidates)
	}
	for index, existing := range r.keywordCoverage {
		if existing.Platform == result.Platform &&
			existing.AppID == result.AppID &&
			existing.Country == result.Country &&
			existing.Lang == result.Lang &&
			existing.Deep == result.Deep {
			r.keywordCoverage[index] = result
			return nil
		}
	}
	r.keywordCoverage = append(r.keywordCoverage, result)
	return nil
}

func (r *MemoryRepo) LatestKeywordCoverage(_ context.Context, filter KeywordCoverageLatestFilter) (dto.KeywordCoverageResponse, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	filter.Platform = coalesce(filter.Platform, dto.PlatformGooglePlay)
	filter.AppID = strings.TrimSpace(filter.AppID)
	filter.Country = strings.ToLower(coalesce(filter.Country, "us"))
	filter.Lang = strings.ToLower(coalesce(filter.Lang, "en"))
	var latest *dto.KeywordCoverageResponse
	for index := range r.keywordCoverage {
		item := &r.keywordCoverage[index]
		if item.Platform != filter.Platform ||
			item.AppID != filter.AppID ||
			item.Country != filter.Country ||
			item.Lang != filter.Lang ||
			item.Deep != filter.Deep {
			continue
		}
		if latest == nil || item.CapturedAt > latest.CapturedAt {
			latest = item
		}
	}
	if latest == nil {
		return dto.KeywordCoverageResponse{}, ErrNotFound
	}
	return *latest, nil
}

func (r *MemoryRepo) ExistingReviewIDs(_ context.Context, filter ExistingReviewsFilter) (map[string]bool, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	identity := normalizeMemoryIdentity(filter.Identity)
	wanted := map[string]bool{}
	for _, reviewID := range filter.ReviewIDs {
		reviewID = strings.TrimSpace(reviewID)
		if reviewID != "" {
			wanted[reviewID] = true
		}
	}
	existing := map[string]bool{}
	if len(wanted) == 0 {
		return existing, nil
	}
	for _, item := range r.reviews {
		if item.AppID != identity.AppID || item.Platform != identity.Platform {
			continue
		}
		if wanted[item.ReviewID] {
			existing[item.ReviewID] = true
		}
	}
	return existing, nil
}

func (r *MemoryRepo) SaveReviews(_ context.Context, input SaveReviewsInput) (int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	identity := normalizeMemoryIdentity(input.Identity)
	existing := map[string]bool{}
	for _, item := range r.reviews {
		if item.ReviewID == "" {
			continue
		}
		if reviewKey(item.Platform, item.AppID, item.ReviewID) != "" {
			existing[reviewKey(item.Platform, item.AppID, item.ReviewID)] = true
		}
	}
	saved := 0
	for _, item := range input.Items {
		item.Platform = coalesce(item.Platform, identity.Platform)
		item.AppID = coalesce(item.AppID, identity.AppID)
		item.Country = coalesce(item.Country, identity.Country)
		item.Lang = coalesce(item.Lang, identity.Lang)
		item.CapturedAt = input.CapturedAt
		key := reviewKey(item.Platform, item.AppID, item.ReviewID)
		if key != "" && existing[key] {
			continue
		}
		r.reviews = append(r.reviews, item)
		if key != "" {
			existing[key] = true
		}
		saved++
	}
	return saved, nil
}

func (r *MemoryRepo) ListReviews(_ context.Context, filter ListReviewsFilter) ([]dto.ReviewItem, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	limit := filter.Limit
	if limit <= 0 {
		limit = 100
	}
	items := make([]dto.ReviewItem, 0, len(r.reviews))
	for _, item := range r.reviews {
		if item.AppID != filter.AppID {
			continue
		}
		items = append(items, item)
	}
	sort.Slice(items, func(i, j int) bool {
		left := coalesce(items[i].ReviewCreatedAt, items[i].CapturedAt)
		right := coalesce(items[j].ReviewCreatedAt, items[j].CapturedAt)
		if left == right {
			return items[i].ReviewID > items[j].ReviewID
		}
		return left > right
	})
	if len(items) > limit {
		items = items[:limit]
	}
	return items, nil
}

func (r *MemoryRepo) CreateAlerts(_ context.Context, alerts []dto.Alert) ([]dto.Alert, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	created := make([]dto.Alert, 0, len(alerts))
	for _, alert := range alerts {
		alert.ID = r.nextAlertID
		r.nextAlertID++
		r.alerts = append(r.alerts, alert)
		created = append(created, alert)
	}
	return created, nil
}

func (r *MemoryRepo) ListAlerts(_ context.Context, filter AlertFilter) ([]dto.Alert, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	limit := filter.Limit
	if limit <= 0 || limit > 200 {
		limit = 200
	}
	items := make([]dto.Alert, 0, len(r.alerts))
	for i := len(r.alerts) - 1; i >= 0; i-- {
		alert := r.alerts[i]
		if filter.AppID != "" && alert.AppID != filter.AppID {
			continue
		}
		if filter.Type != "" && alert.Type != filter.Type {
			continue
		}
		if filter.Severity != "" && alert.Severity != filter.Severity {
			continue
		}
		if filter.IsRead != nil && alert.IsRead != *filter.IsRead {
			continue
		}
		items = append(items, alert)
		if len(items) >= limit {
			break
		}
	}
	return items, nil
}

func (r *MemoryRepo) MarkAlertsRead(_ context.Context, ids []uint64) (int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	wanted := map[uint64]bool{}
	for _, id := range ids {
		wanted[id] = true
	}
	updated := 0
	for i := range r.alerts {
		if len(wanted) > 0 && !wanted[r.alerts[i].ID] {
			continue
		}
		if !r.alerts[i].IsRead {
			r.alerts[i].IsRead = true
			updated++
		}
	}
	return updated, nil
}

func (r *MemoryRepo) CleanupHistory(_ context.Context, input HistoryRetentionCleanupInput) (dto.HistoryRetentionCleanupResponse, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	var result dto.HistoryRetentionCleanupResponse
	for key, history := range r.snapshots {
		kept, deleted := cleanupSnapshotHistory(history, input.SnapshotCutoff, input.MinKeep)
		result.Snapshots += deleted
		if len(kept) == 0 {
			delete(r.snapshots, key)
			continue
		}
		r.snapshots[key] = kept
	}
	r.keywordRanks, result.Keywords = cleanupKeywordRankHistory(r.keywordRanks, input.KeywordCutoff, input.MinKeep)
	r.chartRanks, result.Charts = cleanupChartRankHistory(r.chartRanks, input.ChartCutoff, input.MinKeep)
	r.alerts, result.Alerts = cleanupAlertHistory(r.alerts, input.AlertCutoff, input.MinKeep)
	r.reviews, result.Reviews = cleanupReviewHistory(r.reviews, input.ReviewCutoff, input.MinKeep)
	return result, nil
}

func identityKey(identity dto.AppIdentity) string {
	identity = normalizeMemoryIdentity(identity)
	return strings.Join([]string{
		identity.Platform,
		identity.AppID,
		identity.Country,
		identity.Lang,
	}, "\x1f")
}

func trackedKeywordKey(input TrackedKeywordInput) string {
	input = normalizeTrackedKeywordInput(input)
	return strings.Join([]string{
		input.Platform,
		input.Keyword,
		input.AppID,
		input.Country,
		input.Lang,
	}, "\x1f")
}

func trackedChartAppKey(input TrackedChartAppInput) string {
	input = normalizeTrackedChartAppInput(input)
	return strings.Join([]string{
		input.Platform,
		input.AppID,
		input.Collection,
		input.Category,
		input.Country,
		input.Lang,
	}, "\x1f")
}

func reviewKey(platform, appID, reviewID string) string {
	if strings.TrimSpace(reviewID) == "" {
		return ""
	}
	return strings.Join([]string{
		coalesce(platform, dto.PlatformGooglePlay),
		strings.TrimSpace(appID),
		strings.TrimSpace(reviewID),
	}, "\x1f")
}

func keywordCorpusKey(platform, country, lang, keyword string) string {
	return strings.Join([]string{
		coalesce(platform, dto.PlatformGooglePlay),
		strings.ToLower(coalesce(country, "us")),
		strings.ToLower(coalesce(lang, "en")),
		strings.TrimSpace(keyword),
	}, "\x1f")
}

func normalizeMemoryIdentity(identity dto.AppIdentity) dto.AppIdentity {
	identity.Platform = coalesce(identity.Platform, dto.PlatformGooglePlay)
	identity.AppID = strings.TrimSpace(identity.AppID)
	identity.Country = strings.ToLower(coalesce(identity.Country, "us"))
	identity.Lang = strings.ToLower(coalesce(identity.Lang, "en"))
	return identity
}

func normalizeTrackedKeywordInput(input TrackedKeywordInput) TrackedKeywordInput {
	input.Platform = coalesce(input.Platform, dto.PlatformGooglePlay)
	input.Keyword = strings.TrimSpace(input.Keyword)
	input.AppID = strings.TrimSpace(input.AppID)
	input.Country = strings.ToLower(coalesce(input.Country, "us"))
	input.Lang = strings.ToLower(coalesce(input.Lang, "en"))
	input.Frequency = coalesce(input.Frequency, "daily")
	return input
}

func normalizeTrackedChartAppInput(input TrackedChartAppInput) TrackedChartAppInput {
	input.Platform = coalesce(input.Platform, dto.PlatformGooglePlay)
	input.AppID = strings.TrimSpace(input.AppID)
	input.Collection = coalesce(input.Collection, "top_free")
	input.Category = coalesce(input.Category, "APPLICATION")
	input.Country = strings.ToLower(coalesce(input.Country, "us"))
	input.Lang = strings.ToLower(coalesce(input.Lang, "en"))
	input.Frequency = coalesce(input.Frequency, "daily")
	return input
}

func dayKey(iso string) string {
	if len(iso) >= 10 {
		return iso[:10]
	}
	return iso
}

func chartRankSnapshot(input ChartRankUpsertInput) dto.ChartRankResponse {
	result := input.Result
	return dto.ChartRankResponse{
		Platform:     coalesce(result.Platform, dto.PlatformGooglePlay),
		AppID:        strings.TrimSpace(result.AppID),
		Collection:   coalesce(result.Collection, "top_free"),
		Category:     coalesce(result.Category, "APPLICATION"),
		Country:      strings.ToLower(coalesce(result.Country, "us")),
		Lang:         strings.ToLower(coalesce(result.Lang, "en")),
		Found:        result.Found,
		Rank:         result.Rank,
		CheckedLimit: result.CheckedLimit,
		CapturedAt:   input.CapturedAt,
	}
}

func chartRankSameDay(left, right dto.ChartRankResponse, day string) bool {
	return left.Platform == right.Platform &&
		left.AppID == right.AppID &&
		left.Collection == right.Collection &&
		left.Category == right.Category &&
		left.Country == right.Country &&
		left.Lang == right.Lang &&
		dayKey(left.CapturedAt) == day
}

func keywordRankSnapshot(input KeywordRankUpsertInput) dto.KeywordRankSnapshot {
	result := input.Result
	return dto.KeywordRankSnapshot{
		Platform:     coalesce(result.Platform, dto.PlatformGooglePlay),
		Keyword:      strings.TrimSpace(result.Keyword),
		AppID:        strings.TrimSpace(result.AppID),
		Country:      strings.ToLower(coalesce(result.Country, "us")),
		Lang:         strings.ToLower(coalesce(result.Lang, "en")),
		Found:        result.Found,
		Rank:         result.Rank,
		CheckedLimit: result.CheckedLimit,
		CapturedAt:   input.CapturedAt,
	}
}

func keywordRankSameDay(left, right dto.KeywordRankSnapshot, day string) bool {
	return left.Platform == right.Platform &&
		left.Keyword == right.Keyword &&
		left.AppID == right.AppID &&
		left.Country == right.Country &&
		left.Lang == right.Lang &&
		dayKey(left.CapturedAt) == day
}

func cleanupSnapshotHistory(items []SnapshotRecord, cutoff string, minKeep int) ([]SnapshotRecord, int) {
	alwaysKeep := newestSnapshotIndexes(items, minKeep)
	kept := make([]SnapshotRecord, 0, len(items))
	deleted := 0
	for index, item := range items {
		if !alwaysKeep[index] && item.CapturedAt < cutoff {
			deleted++
			continue
		}
		kept = append(kept, item)
	}
	return kept, deleted
}

func newestSnapshotIndexes(items []SnapshotRecord, minKeep int) map[int]bool {
	indexes := make([]int, 0, len(items))
	for index := range items {
		indexes = append(indexes, index)
	}
	sort.Slice(indexes, func(i, j int) bool {
		return items[indexes[i]].CapturedAt > items[indexes[j]].CapturedAt
	})
	return newestIndexSet(indexes, minKeep)
}

func cleanupKeywordRankHistory(items []dto.KeywordRankSnapshot, cutoff string, minKeep int) ([]dto.KeywordRankSnapshot, int) {
	groups := map[string][]int{}
	for index, item := range items {
		key := strings.Join([]string{
			item.Platform,
			item.Keyword,
			item.AppID,
			item.Country,
			item.Lang,
		}, "\x1f")
		groups[key] = append(groups[key], index)
	}
	alwaysKeep := newestGroupedIndexes(groups, minKeep, func(index int) string {
		return items[index].CapturedAt
	})
	kept := make([]dto.KeywordRankSnapshot, 0, len(items))
	deleted := 0
	for index, item := range items {
		if !alwaysKeep[index] && item.CapturedAt < cutoff {
			deleted++
			continue
		}
		kept = append(kept, item)
	}
	return kept, deleted
}

func cleanupChartRankHistory(items []dto.ChartRankResponse, cutoff string, minKeep int) ([]dto.ChartRankResponse, int) {
	groups := map[string][]int{}
	for index, item := range items {
		key := strings.Join([]string{
			item.Platform,
			item.AppID,
			item.Collection,
			item.Category,
			item.Country,
			item.Lang,
		}, "\x1f")
		groups[key] = append(groups[key], index)
	}
	alwaysKeep := newestGroupedIndexes(groups, minKeep, func(index int) string {
		return items[index].CapturedAt
	})
	kept := make([]dto.ChartRankResponse, 0, len(items))
	deleted := 0
	for index, item := range items {
		if !alwaysKeep[index] && item.CapturedAt < cutoff {
			deleted++
			continue
		}
		kept = append(kept, item)
	}
	return kept, deleted
}

func cleanupAlertHistory(items []dto.Alert, cutoff string, minKeep int) ([]dto.Alert, int) {
	groups := map[string][]int{}
	for index, item := range items {
		groups[item.AppID] = append(groups[item.AppID], index)
	}
	alwaysKeep := newestGroupedIndexes(groups, minKeep, func(index int) string {
		return items[index].CreatedAt
	})
	kept := make([]dto.Alert, 0, len(items))
	deleted := 0
	for index, item := range items {
		if !alwaysKeep[index] && item.IsRead && item.CreatedAt < cutoff {
			deleted++
			continue
		}
		kept = append(kept, item)
	}
	return kept, deleted
}

func cleanupReviewHistory(items []dto.ReviewItem, cutoff string, minKeep int) ([]dto.ReviewItem, int) {
	groups := map[string][]int{}
	for index, item := range items {
		groups[item.AppID] = append(groups[item.AppID], index)
	}
	alwaysKeep := newestGroupedIndexes(groups, minKeep, func(index int) string {
		return items[index].CapturedAt
	})
	kept := make([]dto.ReviewItem, 0, len(items))
	deleted := 0
	for index, item := range items {
		if !alwaysKeep[index] && item.CapturedAt < cutoff {
			deleted++
			continue
		}
		kept = append(kept, item)
	}
	return kept, deleted
}

func newestGroupedIndexes(groups map[string][]int, minKeep int, capturedAt func(int) string) map[int]bool {
	alwaysKeep := map[int]bool{}
	for _, indexes := range groups {
		sort.Slice(indexes, func(i, j int) bool {
			return capturedAt(indexes[i]) > capturedAt(indexes[j])
		})
		for index := range newestIndexSet(indexes, minKeep) {
			alwaysKeep[index] = true
		}
	}
	return alwaysKeep
}

func newestIndexSet(indexes []int, minKeep int) map[int]bool {
	alwaysKeep := map[int]bool{}
	for order, index := range indexes {
		if order >= minKeep {
			break
		}
		alwaysKeep[index] = true
	}
	return alwaysKeep
}

func ensureRawWithCapturedAt(raw map[string]any, capturedAt string) map[string]any {
	if raw == nil {
		raw = map[string]any{}
	}
	raw["captured_at"] = capturedAt
	return raw
}

func ensureRawWithCachedLocale(raw map[string]any, country, lang, updatedAt string) map[string]any {
	if raw == nil {
		raw = map[string]any{}
	}
	raw["country"] = country
	raw["lang"] = lang
	raw["updated_at"] = updatedAt
	return raw
}

func rawString(raw map[string]any, key string) string {
	if raw == nil {
		return ""
	}
	value, _ := raw[key].(string)
	return value
}

func cachedAppKey(platform, appID, country, lang string) string {
	return coalesce(platform, dto.PlatformGooglePlay) + "|" + strings.TrimSpace(appID) + "|" + strings.ToLower(coalesce(country, "us")) + "|" + strings.ToLower(coalesce(lang, "en"))
}

func appSummaryMatches(item dto.AppSummary, query string) bool {
	if query == "" {
		return true
	}
	haystack := strings.ToLower(strings.Join([]string{
		item.AppID,
		item.Title,
		item.Developer,
		item.DeveloperID,
		item.Category,
		item.Summary,
	}, " "))
	return strings.Contains(haystack, query)
}

func cachedUpdatedAt(item dto.AppSummary) string {
	return rawString(item.Raw, "updated_at")
}

func mergeCachedAppSnapshot(item dto.AppSummary, record SnapshotRecord, country, lang string) dto.AppSummary {
	detail := record.Raw
	item.Platform = coalesce(detail.Platform, record.Identity.Platform, item.Platform, dto.PlatformGooglePlay)
	item.AppID = coalesce(detail.AppID, record.Identity.AppID, item.AppID)
	item.Title = coalesce(detail.Title, record.Title, item.Title, item.AppID)
	item.Developer = coalesce(detail.Developer, item.Developer)
	item.DeveloperID = coalesce(detail.DeveloperID, item.DeveloperID)
	item.Category = coalesce(detail.Category, item.Category)
	item.Summary = coalesce(detail.Summary, item.Summary)
	item.Rating = coalesceFloat64Ptr(detail.Rating, record.Rating, item.Rating)
	item.RatingsCount = coalesceInt64Ptr(detail.RatingsCount, record.RatingsCount, item.RatingsCount)
	item.ReviewsCount = coalesceInt64Ptr(detail.ReviewsCount, record.ReviewsCount, item.ReviewsCount)
	item.Installs = coalesce(detail.Installs, record.Installs, item.Installs)
	item.MinInstalls = coalesceInt64Ptr(detail.MinInstalls, record.MinInstalls, item.MinInstalls)
	item.Price = coalesce(detail.Price, item.Price)
	item.Currency = coalesce(detail.Currency, item.Currency)
	item.Free = coalesceBoolPtr(detail.Free, item.Free)
	item.HasIAP = coalesceBoolPtr(detail.HasIAP, item.HasIAP)
	item.IconURL = coalesce(detail.IconURL, item.IconURL)
	item.StoreURL = coalesce(detail.StoreURL, item.StoreURL)
	item.Raw = ensureRawWithCachedLocale(item.Raw, country, lang, cachedUpdatedAt(item))
	if item.Raw == nil {
		item.Raw = map[string]any{}
	}
	if record.CapturedAt != "" {
		item.Raw["captured_at"] = record.CapturedAt
	}
	return item
}

func coalesceFloat64Ptr(values ...*float64) *float64 {
	for _, value := range values {
		if value != nil {
			return value
		}
	}
	return nil
}

func coalesceInt64Ptr(values ...*int64) *int64 {
	for _, value := range values {
		if value != nil {
			return value
		}
	}
	return nil
}

func coalesceBoolPtr(values ...*bool) *bool {
	for _, value := range values {
		if value != nil {
			return value
		}
	}
	return nil
}

func coalesce(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return strings.TrimSpace(value)
		}
	}
	return ""
}
