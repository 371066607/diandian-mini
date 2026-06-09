package repo

import (
	"context"
	"errors"

	"github.com/diandian-mini/storeintel/dto"
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

type TrackedAppFilter struct {
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
	ReviewsCount *int64
	Installs     string
	MinInstalls  *int64
	Raw          dto.AppDetail
}

type SnapshotUpsertResult struct {
	Previous   *SnapshotRecord
	Current    SnapshotRecord
	FirstOfDay bool
}

type AlertFilter struct {
	AppID    string
	Type     string
	Severity string
	IsRead   *bool
	Limit    int
}

type StoreIntelRepo interface {
	UpsertTrackedApp(ctx context.Context, input TrackedAppInput) (dto.TrackedApp, error)
	ListTrackedApps(ctx context.Context, filter TrackedAppFilter) ([]dto.TrackedApp, error)
	UpdateTrackedAppSyncSuccess(ctx context.Context, identity dto.AppIdentity, syncedAt string) error
	RecordTrackedAppFailure(ctx context.Context, identity dto.AppIdentity, failedAt, message string) (int, error)
	UpsertAppSnapshot(ctx context.Context, input SnapshotUpsertInput) (SnapshotUpsertResult, error)
	CreateAlerts(ctx context.Context, alerts []dto.Alert) ([]dto.Alert, error)
	ListAlerts(ctx context.Context, filter AlertFilter) ([]dto.Alert, error)
	MarkAlertsRead(ctx context.Context, ids []uint64) (int, error)
}
