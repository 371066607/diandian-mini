package repo

import (
	"context"
	"sort"
	"strings"
	"sync"

	"github.com/diandian-mini/storeintel/dto"
)

type MemoryRepo struct {
	mu            sync.Mutex
	nextTrackedID uint64
	nextAlertID   uint64
	trackedApps   map[string]dto.TrackedApp
	snapshots     map[string][]SnapshotRecord
	alerts        []dto.Alert
}

func NewMemoryRepo() *MemoryRepo {
	return &MemoryRepo{
		nextTrackedID: 1,
		nextAlertID:   1,
		trackedApps:   map[string]dto.TrackedApp{},
		snapshots:     map[string][]SnapshotRecord{},
	}
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

func (r *MemoryRepo) UpdateTrackedAppSyncSuccess(_ context.Context, identity dto.AppIdentity, syncedAt string) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	key := identityKey(identity)
	item, ok := r.trackedApps[key]
	if !ok {
		return ErrNotFound
	}
	item.LastSyncedAt = syncedAt
	item.ConsecutiveFailures = 0
	item.LastFailedAt = ""
	item.UpdatedAt = syncedAt
	r.trackedApps[key] = item
	return nil
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

func (r *MemoryRepo) UpsertAppSnapshot(_ context.Context, input SnapshotUpsertInput) (SnapshotUpsertResult, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	identity := dto.AppIdentity{
		Platform: coalesce(input.Detail.Platform, dto.PlatformGooglePlay),
		AppID:    input.Detail.AppID,
		Country:  input.Country,
		Lang:     input.Lang,
	}
	key := identityKey(identity)
	day := dayKey(input.CapturedAt)
	current := SnapshotRecord{
		Identity:     identity,
		CapturedAt:   input.CapturedAt,
		Title:        input.Detail.Title,
		Rating:       input.Detail.Rating,
		ReviewsCount: input.Detail.ReviewsCount,
		Installs:     input.Detail.Installs,
		MinInstalls:  input.Detail.MinInstalls,
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

func identityKey(identity dto.AppIdentity) string {
	return strings.Join([]string{
		coalesce(identity.Platform, dto.PlatformGooglePlay),
		identity.AppID,
		coalesce(identity.Country, "us"),
		coalesce(identity.Lang, "en"),
	}, "\x1f")
}

func dayKey(iso string) string {
	if len(iso) >= 10 {
		return iso[:10]
	}
	return iso
}

func coalesce(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return strings.TrimSpace(value)
		}
	}
	return ""
}
