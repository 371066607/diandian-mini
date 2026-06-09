package repo

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"github.com/diandian-mini/storeintel/dto"
)

type SQLRepo struct {
	db *sql.DB
}

func NewSQLRepo(db *sql.DB) StoreIntelRepo {
	return &SQLRepo{db: db}
}

func (r *SQLRepo) UpsertTrackedApp(ctx context.Context, input TrackedAppInput) (dto.TrackedApp, error) {
	if r == nil || r.db == nil {
		return dto.TrackedApp{}, ErrNotFound
	}
	identity := normalizeIdentity(input.Identity)
	frequency := coalesce(input.Frequency, "daily")
	now := input.NowISO
	_, err := r.db.ExecContext(ctx, `
INSERT INTO store_intel_tracked_apps (
  platform, app_id, country, lang, title, frequency, tag, enabled,
  last_synced_at, consecutive_failures, last_failed_at, created_at, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', 0, '', ?, ?)
ON DUPLICATE KEY UPDATE
  title = CASE WHEN ? = '' THEN title ELSE ? END,
  frequency = ?,
  tag = ?,
  enabled = ?,
  updated_at = ?`,
		identity.Platform, identity.AppID, identity.Country, identity.Lang,
		input.Title, frequency, input.Tag, boolInt(input.Enabled), now, now,
		input.Title, input.Title, frequency, input.Tag, boolInt(input.Enabled), now,
	)
	if err != nil {
		return dto.TrackedApp{}, err
	}
	return r.getTrackedApp(ctx, identity)
}

func (r *SQLRepo) ListTrackedApps(ctx context.Context, filter TrackedAppFilter) ([]dto.TrackedApp, error) {
	if r == nil || r.db == nil {
		return nil, ErrNotFound
	}
	query := `
SELECT id, platform, app_id, title, country, lang, frequency, tag, enabled,
       last_synced_at, consecutive_failures, last_failed_at, created_at, updated_at
FROM store_intel_tracked_apps`
	args := []any{}
	if filter.Enabled != nil {
		query += " WHERE enabled = ?"
		args = append(args, boolInt(*filter.Enabled))
	}
	query += " ORDER BY updated_at DESC, id DESC"
	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var items []dto.TrackedApp
	for rows.Next() {
		item, err := scanTrackedApp(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (r *SQLRepo) UpdateTrackedAppSyncSuccess(ctx context.Context, identity dto.AppIdentity, syncedAt string) error {
	if r == nil || r.db == nil {
		return ErrNotFound
	}
	identity = normalizeIdentity(identity)
	result, err := r.db.ExecContext(ctx, `
UPDATE store_intel_tracked_apps
SET last_synced_at = ?, consecutive_failures = 0, last_failed_at = '', updated_at = ?
WHERE platform = ? AND app_id = ? AND country = ? AND lang = ?`,
		syncedAt, syncedAt, identity.Platform, identity.AppID, identity.Country, identity.Lang,
	)
	return errOrNotFound(result, err)
}

func (r *SQLRepo) RecordTrackedAppFailure(ctx context.Context, identity dto.AppIdentity, failedAt, _ string) (int, error) {
	if r == nil || r.db == nil {
		return 0, ErrNotFound
	}
	identity = normalizeIdentity(identity)
	result, err := r.db.ExecContext(ctx, `
UPDATE store_intel_tracked_apps
SET consecutive_failures = consecutive_failures + 1, last_failed_at = ?, updated_at = ?
WHERE platform = ? AND app_id = ? AND country = ? AND lang = ?`,
		failedAt, failedAt, identity.Platform, identity.AppID, identity.Country, identity.Lang,
	)
	if err := errOrNotFound(result, err); err != nil {
		return 0, err
	}
	var count int
	err = r.db.QueryRowContext(ctx, `
SELECT consecutive_failures
FROM store_intel_tracked_apps
WHERE platform = ? AND app_id = ? AND country = ? AND lang = ?`,
		identity.Platform, identity.AppID, identity.Country, identity.Lang,
	).Scan(&count)
	if err != nil {
		return 0, normalizeSQLErr(err)
	}
	return count, nil
}

func (r *SQLRepo) UpsertAppSnapshot(ctx context.Context, input SnapshotUpsertInput) (SnapshotUpsertResult, error) {
	if r == nil || r.db == nil {
		return SnapshotUpsertResult{}, ErrNotFound
	}
	identity := normalizeIdentity(dto.AppIdentity{
		Platform: input.Detail.Platform,
		AppID:    input.Detail.AppID,
		Country:  input.Country,
		Lang:     input.Lang,
	})
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
	day := dayKey(input.CapturedAt)
	previous, err := r.previousSnapshot(ctx, identity, day)
	if err != nil && !errors.Is(err, ErrNotFound) {
		return SnapshotUpsertResult{}, err
	}
	var existingID uint64
	err = r.db.QueryRowContext(ctx, `
SELECT id FROM store_intel_app_snapshots
WHERE platform = ? AND app_id = ? AND country = ? AND lang = ? AND captured_day = ?
ORDER BY captured_at DESC LIMIT 1`,
		identity.Platform, identity.AppID, identity.Country, identity.Lang, day,
	).Scan(&existingID)
	if err != nil && !errors.Is(err, sql.ErrNoRows) {
		return SnapshotUpsertResult{}, err
	}
	rawJSON, err := json.Marshal(input.Detail)
	if err != nil {
		return SnapshotUpsertResult{}, err
	}
	if existingID > 0 {
		_, err = r.db.ExecContext(ctx, `
UPDATE store_intel_app_snapshots
SET captured_at = ?, captured_day = ?, title = ?, rating = ?, reviews_count = ?, installs = ?,
    min_installs = ?, raw_json = ?, updated_at = ?
WHERE id = ?`,
			input.CapturedAt, day, input.Detail.Title, nullableFloat(input.Detail.Rating),
			nullableInt64(input.Detail.ReviewsCount), input.Detail.Installs,
			nullableInt64(input.Detail.MinInstalls), string(rawJSON), input.CapturedAt, existingID,
		)
		if err != nil {
			return SnapshotUpsertResult{}, err
		}
		return SnapshotUpsertResult{Previous: previous, Current: current, FirstOfDay: false}, nil
	}
	_, err = r.db.ExecContext(ctx, `
INSERT INTO store_intel_app_snapshots (
  platform, app_id, country, lang, captured_at, captured_day, title, rating, reviews_count,
  installs, min_installs, raw_json, created_at, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		identity.Platform, identity.AppID, identity.Country, identity.Lang,
		input.CapturedAt, day, input.Detail.Title, nullableFloat(input.Detail.Rating),
		nullableInt64(input.Detail.ReviewsCount), input.Detail.Installs,
		nullableInt64(input.Detail.MinInstalls), string(rawJSON), input.CapturedAt, input.CapturedAt,
	)
	if err != nil {
		return SnapshotUpsertResult{}, err
	}
	return SnapshotUpsertResult{Previous: previous, Current: current, FirstOfDay: true}, nil
}

func (r *SQLRepo) CreateAlerts(ctx context.Context, alerts []dto.Alert) ([]dto.Alert, error) {
	if r == nil || r.db == nil {
		return nil, ErrNotFound
	}
	created := make([]dto.Alert, 0, len(alerts))
	for _, alert := range alerts {
		payloadJSON, err := json.Marshal(alert.Payload)
		if err != nil {
			return nil, err
		}
		result, err := r.db.ExecContext(ctx, `
INSERT INTO store_intel_alerts (
  type, severity, app_id, title, message, payload_json, is_read, created_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
			alert.Type, alert.Severity, alert.AppID, alert.Title, alert.Message,
			string(payloadJSON), boolInt(alert.IsRead), alert.CreatedAt,
		)
		if err != nil {
			return nil, err
		}
		id, _ := result.LastInsertId()
		alert.ID = uint64(id)
		created = append(created, alert)
	}
	return created, nil
}

func (r *SQLRepo) ListAlerts(ctx context.Context, filter AlertFilter) ([]dto.Alert, error) {
	if r == nil || r.db == nil {
		return nil, ErrNotFound
	}
	limit := filter.Limit
	if limit <= 0 || limit > 200 {
		limit = 200
	}
	query := `
SELECT id, type, severity, app_id, title, message, payload_json, is_read, created_at
FROM store_intel_alerts`
	where := []string{}
	args := []any{}
	if strings.TrimSpace(filter.AppID) != "" {
		where = append(where, "app_id = ?")
		args = append(args, strings.TrimSpace(filter.AppID))
	}
	if strings.TrimSpace(filter.Type) != "" {
		where = append(where, "type = ?")
		args = append(args, strings.TrimSpace(filter.Type))
	}
	if strings.TrimSpace(filter.Severity) != "" {
		where = append(where, "severity = ?")
		args = append(args, strings.TrimSpace(filter.Severity))
	}
	if filter.IsRead != nil {
		where = append(where, "is_read = ?")
		args = append(args, boolInt(*filter.IsRead))
	}
	if len(where) > 0 {
		query += " WHERE " + strings.Join(where, " AND ")
	}
	query += " ORDER BY created_at DESC, id DESC LIMIT ?"
	args = append(args, limit)
	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var alerts []dto.Alert
	for rows.Next() {
		alert, err := scanAlert(rows)
		if err != nil {
			return nil, err
		}
		alerts = append(alerts, alert)
	}
	return alerts, rows.Err()
}

func (r *SQLRepo) MarkAlertsRead(ctx context.Context, ids []uint64) (int, error) {
	if r == nil || r.db == nil {
		return 0, ErrNotFound
	}
	query := "UPDATE store_intel_alerts SET is_read = 1 WHERE is_read = 0"
	args := []any{}
	if len(ids) > 0 {
		placeholders := make([]string, 0, len(ids))
		for _, id := range ids {
			placeholders = append(placeholders, "?")
			args = append(args, id)
		}
		query += " AND id IN (" + strings.Join(placeholders, ",") + ")"
	}
	result, err := r.db.ExecContext(ctx, query, args...)
	if err != nil {
		return 0, err
	}
	count, _ := result.RowsAffected()
	return int(count), nil
}

func (r *SQLRepo) getTrackedApp(ctx context.Context, identity dto.AppIdentity) (dto.TrackedApp, error) {
	row := r.db.QueryRowContext(ctx, `
SELECT id, platform, app_id, title, country, lang, frequency, tag, enabled,
       last_synced_at, consecutive_failures, last_failed_at, created_at, updated_at
FROM store_intel_tracked_apps
WHERE platform = ? AND app_id = ? AND country = ? AND lang = ?`,
		identity.Platform, identity.AppID, identity.Country, identity.Lang,
	)
	return scanTrackedApp(row)
}

func (r *SQLRepo) previousSnapshot(ctx context.Context, identity dto.AppIdentity, day string) (*SnapshotRecord, error) {
	row := r.db.QueryRowContext(ctx, `
SELECT platform, app_id, country, lang, captured_at, title, rating, reviews_count,
       installs, min_installs, raw_json
FROM store_intel_app_snapshots
WHERE platform = ? AND app_id = ? AND country = ? AND lang = ? AND captured_day <> ?
ORDER BY captured_at DESC LIMIT 1`,
		identity.Platform, identity.AppID, identity.Country, identity.Lang, day,
	)
	record, err := scanSnapshot(row)
	if err != nil {
		return nil, err
	}
	return &record, nil
}

type rowScanner interface {
	Scan(dest ...any) error
}

func scanTrackedApp(row rowScanner) (dto.TrackedApp, error) {
	var item dto.TrackedApp
	var enabled int
	var title, tag, lastSyncedAt, lastFailedAt sql.NullString
	err := row.Scan(
		&item.ID, &item.Platform, &item.AppID, &title, &item.Country, &item.Lang,
		&item.Frequency, &tag, &enabled, &lastSyncedAt, &item.ConsecutiveFailures,
		&lastFailedAt, &item.CreatedAt, &item.UpdatedAt,
	)
	if err != nil {
		return dto.TrackedApp{}, normalizeSQLErr(err)
	}
	item.Title = title.String
	item.Tag = tag.String
	item.Enabled = enabled != 0
	item.LastSyncedAt = lastSyncedAt.String
	item.LastFailedAt = lastFailedAt.String
	return item, nil
}

func scanSnapshot(row rowScanner) (SnapshotRecord, error) {
	var record SnapshotRecord
	var rawJSON string
	var title, installs sql.NullString
	var rating sql.NullFloat64
	var reviewsCount, minInstalls sql.NullInt64
	err := row.Scan(
		&record.Identity.Platform, &record.Identity.AppID, &record.Identity.Country,
		&record.Identity.Lang, &record.CapturedAt, &title, &rating, &reviewsCount,
		&installs, &minInstalls, &rawJSON,
	)
	if err != nil {
		return SnapshotRecord{}, normalizeSQLErr(err)
	}
	record.Title = title.String
	if rating.Valid {
		record.Rating = &rating.Float64
	}
	if reviewsCount.Valid {
		record.ReviewsCount = &reviewsCount.Int64
	}
	record.Installs = installs.String
	if minInstalls.Valid {
		record.MinInstalls = &minInstalls.Int64
	}
	if rawJSON != "" {
		_ = json.Unmarshal([]byte(rawJSON), &record.Raw)
	}
	return record, nil
}

func scanAlert(row rowScanner) (dto.Alert, error) {
	var alert dto.Alert
	var appID, title, payloadJSON sql.NullString
	var isRead int
	err := row.Scan(
		&alert.ID, &alert.Type, &alert.Severity, &appID, &title, &alert.Message,
		&payloadJSON, &isRead, &alert.CreatedAt,
	)
	if err != nil {
		return dto.Alert{}, normalizeSQLErr(err)
	}
	alert.AppID = appID.String
	alert.Title = title.String
	alert.IsRead = isRead != 0
	if payloadJSON.String != "" {
		_ = json.Unmarshal([]byte(payloadJSON.String), &alert.Payload)
	}
	return alert, nil
}

func errOrNotFound(result sql.Result, err error) error {
	if err != nil {
		return err
	}
	if result == nil {
		return nil
	}
	count, err := result.RowsAffected()
	if err != nil {
		return nil
	}
	if count == 0 {
		return ErrNotFound
	}
	return nil
}

func normalizeSQLErr(err error) error {
	if errors.Is(err, sql.ErrNoRows) {
		return ErrNotFound
	}
	return err
}

func normalizeIdentity(identity dto.AppIdentity) dto.AppIdentity {
	identity.Platform = coalesce(identity.Platform, dto.PlatformGooglePlay)
	identity.Country = strings.ToLower(coalesce(identity.Country, "us"))
	identity.Lang = strings.ToLower(coalesce(identity.Lang, "en"))
	identity.AppID = strings.TrimSpace(identity.AppID)
	return identity
}

func nullableFloat(value *float64) any {
	if value == nil {
		return nil
	}
	return *value
}

func nullableInt64(value *int64) any {
	if value == nil {
		return nil
	}
	return *value
}

func boolInt(value bool) int {
	if value {
		return 1
	}
	return 0
}

func _formatSQLDebug(query string, args []any) string {
	return fmt.Sprintf("%s -- %v", query, args)
}
