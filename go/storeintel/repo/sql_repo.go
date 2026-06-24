package repo

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"reflect"
	"strings"

	"github.com/catch-radar/storeintel/dto"
)

type SQLRepo struct {
	db *sql.DB
}

var appSnapshotColumns = []string{
	"platform",
	"app_id",
	"country",
	"lang",
	"captured_at",
	"captured_day",
	"title",
	"developer",
	"category",
	"rating",
	"ratings_count",
	"reviews_count",
	"installs",
	"min_installs",
	"max_installs",
	"real_installs",
	"price",
	"free",
	"has_iap",
	"version",
	"updated",
	"released",
	"android_version",
	"content_rating",
	"description",
	"summary",
	"changelog",
	"icon_url",
	"screenshots_json",
	"contains_ads",
	"ad_supported",
	"daily_installs",
	"min_daily_installs",
	"real_daily_installs",
	"monthly_installs",
	"min_monthly_installs",
	"real_monthly_installs",
	"app_age_days",
	"genre_id",
	"developer_id",
	"currency",
	"sale",
	"original_price",
	"developer_email",
	"developer_website",
	"developer_address",
	"developer_phone",
	"publisher_country",
	"privacy_policy",
	"header_image",
	"video",
	"content_rating_description",
	"available",
	"max_android_api",
	"min_android_api",
	"app_bundle",
	"histogram_json",
	"categories_json",
	"permissions_json",
	"data_safety_json",
	"raw_json",
}

var appSnapshotSelectColumns = []string{
	"platform",
	"app_id",
	"country",
	"lang",
	"captured_at",
	"title",
	"developer",
	"category",
	"rating",
	"ratings_count",
	"reviews_count",
	"installs",
	"min_installs",
	"real_installs",
	"price",
	"free",
	"has_iap",
	"version",
	"updated",
	"released",
	"android_version",
	"content_rating",
	"description",
	"summary",
	"changelog",
	"icon_url",
	"screenshots_json",
	"contains_ads",
	"ad_supported",
	"daily_installs",
	"min_daily_installs",
	"real_daily_installs",
	"monthly_installs",
	"min_monthly_installs",
	"real_monthly_installs",
	"app_age_days",
	"genre_id",
	"developer_id",
	"currency",
	"sale",
	"original_price",
	"developer_email",
	"developer_website",
	"developer_address",
	"developer_phone",
	"publisher_country",
	"privacy_policy",
	"header_image",
	"video",
	"content_rating_description",
	"available",
	"max_android_api",
	"min_android_api",
	"app_bundle",
	"histogram_json",
	"categories_json",
	"permissions_json",
	"data_safety_json",
	"raw_json",
}

type appSnapshotValues struct {
	identity    dto.AppIdentity
	capturedAt  string
	capturedDay string
	detail      dto.AppDetail
	args        []any
}

type cleanupHistoryQuery struct {
	Table       string
	TimeColumn  string
	Partitions  []string
	SelectExtra []string
	OuterWhere  string
	Cutoff      string
	MinKeep     int
	RankedAlias string
}

func NewSQLRepo(db *sql.DB) StoreIntelRepo {
	return &SQLRepo{db: db}
}

func (r *SQLRepo) ListSettings(ctx context.Context) (map[string]string, error) {
	if r == nil || r.db == nil {
		return nil, ErrNotFound
	}
	rows, err := r.db.QueryContext(ctx, "SELECT `key`, `value` FROM store_intel_settings ORDER BY `key`")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	values := map[string]string{}
	for rows.Next() {
		var key string
		var value sql.NullString
		if err := rows.Scan(&key, &value); err != nil {
			return nil, err
		}
		values[key] = value.String
	}
	return values, rows.Err()
}

func (r *SQLRepo) UpsertSettings(ctx context.Context, values map[string]string, updatedAt string) error {
	if r == nil || r.db == nil {
		return ErrNotFound
	}
	for key, value := range values {
		_, err := r.db.ExecContext(ctx,
			"INSERT INTO store_intel_settings (`key`, `value`, updated_at) VALUES (?, ?, ?) "+
				"ON DUPLICATE KEY UPDATE `value` = ?, updated_at = ?",
			key, value, updatedAt, value, updatedAt,
		)
		if err != nil {
			return err
		}
	}
	return nil
}

func acquireSettingUpdateSQL() string {
	return "UPDATE store_intel_settings SET `value` = ?, updated_at = ? WHERE `key` = ? AND (`value` IS NULL OR `value` <> ?)"
}

func acquireSettingInsertSQL() string {
	return "INSERT IGNORE INTO store_intel_settings (`key`, `value`, updated_at) VALUES (?, ?, ?)"
}

func (r *SQLRepo) AcquireSettingValue(ctx context.Context, key, value, updatedAt string) (bool, error) {
	if r == nil || r.db == nil {
		return false, ErrNotFound
	}
	key = strings.TrimSpace(key)
	if key == "" {
		return false, nil
	}
	result, err := r.db.ExecContext(ctx, acquireSettingUpdateSQL(), value, updatedAt, key, value)
	if err != nil {
		return false, err
	}
	affected, err := result.RowsAffected()
	if err != nil {
		return false, err
	}
	if affected > 0 {
		return true, nil
	}

	result, err = r.db.ExecContext(ctx, acquireSettingInsertSQL(), key, value, updatedAt)
	if err != nil {
		return false, err
	}
	affected, err = result.RowsAffected()
	if err != nil {
		return false, err
	}
	return affected > 0, nil
}

func (r *SQLRepo) CreateRefreshJob(ctx context.Context, input RefreshJobCreateInput) (dto.RefreshJobResponse, error) {
	if r == nil || r.db == nil {
		return dto.RefreshJobResponse{}, ErrNotFound
	}
	job := input.Job
	requestJSON, err := jsonColumn(input.Request)
	if err != nil {
		return dto.RefreshJobResponse{}, err
	}
	_, err = r.db.ExecContext(ctx, `
	INSERT INTO store_intel_refresh_jobs (
	  job_id, kind, status, worker_id, locked_until, message, request_json,
	  requested_at, started_at, finished_at, updated_at
	) VALUES (?, ?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?)`,
		job.JobID, job.Kind, job.Status, nullableString(job.Message), requestJSON,
		job.RequestedAt, nullableString(job.StartedAt), nullableString(job.FinishedAt),
		coalesce(job.UpdatedAt, job.RequestedAt),
	)
	if err != nil {
		return dto.RefreshJobResponse{}, err
	}
	return r.GetRefreshJob(ctx, job.JobID)
}

func (r *SQLRepo) UpdateRefreshJob(ctx context.Context, input RefreshJobUpdateInput) (dto.RefreshJobResponse, error) {
	if r == nil || r.db == nil {
		return dto.RefreshJobResponse{}, ErrNotFound
	}
	_, err := r.db.ExecContext(ctx, `
	UPDATE store_intel_refresh_jobs
	SET status = ?, message = ?, started_at = ?, finished_at = ?, updated_at = ?,
	    worker_id = CASE WHEN ? IN ('completed', 'failed') THEN NULL ELSE worker_id END,
	    locked_until = CASE WHEN ? IN ('completed', 'failed') THEN NULL ELSE locked_until END
	WHERE job_id = ?`,
		input.Status, nullableString(input.Message), nullableString(input.StartedAt),
		nullableString(input.FinishedAt), input.UpdatedAt, input.Status, input.Status,
		strings.TrimSpace(input.JobID),
	)
	if err != nil {
		return dto.RefreshJobResponse{}, err
	}
	return r.GetRefreshJob(ctx, input.JobID)
}

func (r *SQLRepo) GetRefreshJob(ctx context.Context, jobID string) (dto.RefreshJobResponse, error) {
	if r == nil || r.db == nil {
		return dto.RefreshJobResponse{}, ErrNotFound
	}
	row := r.db.QueryRowContext(ctx, `
	SELECT job_id, kind, status, COALESCE(message, ''), requested_at,
	       COALESCE(started_at, ''), COALESCE(finished_at, ''), updated_at
	FROM store_intel_refresh_jobs
	WHERE job_id = ?`,
		strings.TrimSpace(jobID),
	)
	return scanRefreshJob(row)
}

func (r *SQLRepo) ListRefreshJobs(ctx context.Context, filter RefreshJobListFilter) ([]dto.RefreshJobRecord, error) {
	if r == nil || r.db == nil {
		return nil, ErrNotFound
	}
	statuses := make([]string, 0, len(filter.Statuses))
	for _, status := range filter.Statuses {
		status = strings.TrimSpace(status)
		if status != "" {
			statuses = append(statuses, status)
		}
	}
	if len(statuses) == 0 {
		statuses = []string{"queued", "running"}
	}
	limit := filter.Limit
	if limit <= 0 {
		limit = 100
	}
	placeholders := make([]string, 0, len(statuses))
	args := make([]any, 0, len(statuses)+1)
	for _, status := range statuses {
		placeholders = append(placeholders, "?")
		args = append(args, status)
	}
	args = append(args, limit)
	rows, err := r.db.QueryContext(ctx, `
	SELECT job_id, kind, status, COALESCE(message, ''), requested_at,
	       COALESCE(started_at, ''), COALESCE(finished_at, ''), updated_at,
	       request_json
	FROM store_intel_refresh_jobs
	WHERE status IN (`+strings.Join(placeholders, ",")+`)
	ORDER BY updated_at ASC, id ASC
	LIMIT ?`, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	records := []dto.RefreshJobRecord{}
	for rows.Next() {
		record, err := scanRefreshJobRecord(rows)
		if err != nil {
			return nil, err
		}
		records = append(records, record)
	}
	return records, rows.Err()
}

func (r *SQLRepo) ClaimRefreshJob(ctx context.Context, input RefreshJobClaimInput) (dto.RefreshJobResponse, bool, error) {
	if r == nil || r.db == nil {
		return dto.RefreshJobResponse{}, false, ErrNotFound
	}
	result, err := r.db.ExecContext(ctx, `
	UPDATE store_intel_refresh_jobs
	SET status = 'running',
	    worker_id = ?,
	    locked_until = ?,
	    message = ?,
	    started_at = ?,
	    finished_at = NULL,
	    updated_at = ?
	WHERE job_id = ?
	  AND (
	    status = 'queued'
	    OR (status = 'running' AND (locked_until IS NULL OR locked_until < ?))
	  )`,
		input.WorkerID, input.LockedUntil, "服务器正在后台刷新。", input.StartedAt,
		input.UpdatedAt, strings.TrimSpace(input.JobID), input.UpdatedAt,
	)
	if err != nil {
		return dto.RefreshJobResponse{}, false, err
	}
	affected, err := result.RowsAffected()
	if err != nil {
		return dto.RefreshJobResponse{}, false, err
	}
	job, getErr := r.GetRefreshJob(ctx, input.JobID)
	if getErr != nil {
		return dto.RefreshJobResponse{}, false, getErr
	}
	return job, affected > 0, nil
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

func (r *SQLRepo) RemoveTrackedApp(ctx context.Context, identity dto.AppIdentity) (int, error) {
	if r == nil || r.db == nil {
		return 0, ErrNotFound
	}
	identity = normalizeIdentity(identity)
	result, err := r.db.ExecContext(ctx, `
DELETE FROM store_intel_tracked_apps
WHERE platform = ? AND app_id = ? AND country = ? AND lang = ?`,
		identity.Platform, identity.AppID, identity.Country, identity.Lang,
	)
	return rowsAffected(result, err)
}

func (r *SQLRepo) SetTrackedAppEnabled(ctx context.Context, identity dto.AppIdentity, enabled bool, updatedAt string) (bool, int, error) {
	if r == nil || r.db == nil {
		return enabled, 0, ErrNotFound
	}
	identity = normalizeIdentity(identity)
	result, err := r.db.ExecContext(ctx, `
UPDATE store_intel_tracked_apps
SET enabled = ?, updated_at = ?
WHERE platform = ? AND app_id = ? AND country = ? AND lang = ?`,
		boolInt(enabled), updatedAt, identity.Platform, identity.AppID, identity.Country, identity.Lang,
	)
	updated, err := rowsAffected(result, err)
	return enabled, updated, err
}

func (r *SQLRepo) SetTrackedAppFrequency(ctx context.Context, identity dto.AppIdentity, frequency, updatedAt string) (string, int, error) {
	if r == nil || r.db == nil {
		return frequency, 0, ErrNotFound
	}
	identity = normalizeIdentity(identity)
	result, err := r.db.ExecContext(ctx, `
UPDATE store_intel_tracked_apps
SET frequency = ?, updated_at = ?
WHERE platform = ? AND app_id = ? AND country = ? AND lang = ?`,
		frequency, updatedAt, identity.Platform, identity.AppID, identity.Country, identity.Lang,
	)
	updated, err := rowsAffected(result, err)
	return frequency, updated, err
}

func (r *SQLRepo) SetTrackedAppTag(ctx context.Context, identity dto.AppIdentity, tag, updatedAt string) (string, int, error) {
	if r == nil || r.db == nil {
		return "", 0, ErrNotFound
	}
	identity = normalizeIdentity(identity)
	tag = strings.TrimSpace(tag)
	result, err := r.db.ExecContext(ctx, `
UPDATE store_intel_tracked_apps
SET tag = ?, updated_at = ?
WHERE platform = ? AND app_id = ? AND country = ? AND lang = ?`,
		tag, updatedAt, identity.Platform, identity.AppID, identity.Country, identity.Lang,
	)
	updated, err := rowsAffected(result, err)
	return tag, updated, err
}

func (r *SQLRepo) UpdateTrackedAppSyncSuccess(ctx context.Context, identity dto.AppIdentity, syncedAt string) (int, error) {
	if r == nil || r.db == nil {
		return 0, ErrNotFound
	}
	identity = normalizeIdentity(identity)
	priorFailures, err := r.trackedAppFailureCount(ctx, identity)
	if err != nil {
		return 0, err
	}
	result, err := r.db.ExecContext(ctx, `
UPDATE store_intel_tracked_apps
SET last_synced_at = ?, consecutive_failures = 0, last_failed_at = '', updated_at = ?
WHERE platform = ? AND app_id = ? AND country = ? AND lang = ?`,
		syncedAt, syncedAt, identity.Platform, identity.AppID, identity.Country, identity.Lang,
	)
	if err := errOrNotFound(result, err); err != nil {
		return 0, err
	}
	return priorFailures, nil
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

func (r *SQLRepo) UpsertCachedApps(ctx context.Context, input CachedAppsUpsertInput) (int, error) {
	if r == nil || r.db == nil {
		return 0, ErrNotFound
	}
	platform := coalesce(input.Platform, dto.PlatformGooglePlay)
	country := strings.ToLower(coalesce(input.Country, "us"))
	lang := strings.ToLower(coalesce(input.Lang, "en"))
	saved := 0
	for _, item := range input.Items {
		item.AppID = strings.TrimSpace(item.AppID)
		if item.AppID == "" {
			continue
		}
		_, err := r.db.ExecContext(ctx, `
	INSERT INTO store_intel_apps (
	  platform, app_id, title, developer, developer_id, category, icon_url, store_url,
	  country, lang, created_at, updated_at
	) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	ON DUPLICATE KEY UPDATE
	  title = VALUES(title),
	  developer = VALUES(developer),
	  developer_id = VALUES(developer_id),
	  category = VALUES(category),
	  icon_url = VALUES(icon_url),
	  store_url = VALUES(store_url),
	  updated_at = VALUES(updated_at)`,
			coalesce(item.Platform, platform), item.AppID, nullableString(item.Title),
			nullableString(item.Developer), nullableString(item.DeveloperID),
			nullableString(item.Category), nullableString(item.IconURL),
			nullableString(item.StoreURL), country, lang, input.UpdatedAt, input.UpdatedAt,
		)
		if err != nil {
			return 0, err
		}
		saved++
	}
	return saved, nil
}

func (r *SQLRepo) SearchCachedApps(ctx context.Context, filter CachedAppSearchFilter) ([]dto.AppSummary, error) {
	if r == nil || r.db == nil {
		return nil, ErrNotFound
	}
	filter.Platform = coalesce(filter.Platform, dto.PlatformGooglePlay)
	filter.Query = strings.TrimSpace(filter.Query)
	filter.Country = strings.ToLower(coalesce(filter.Country, "us"))
	filter.Lang = strings.ToLower(coalesce(filter.Lang, "en"))
	limit := filter.Limit
	if limit <= 0 || limit > 100 {
		limit = 50
	}
	args := []any{filter.Platform, filter.Country, filter.Lang}
	where := "a.platform = ? AND a.country = ? AND a.lang = ?"
	if filter.Query != "" {
		like := "%" + filter.Query + "%"
		where += " AND (a.app_id LIKE ? OR a.title LIKE ? OR a.developer LIKE ? OR a.developer_id LIKE ? OR a.category LIKE ? OR s.title LIKE ? OR s.developer LIKE ? OR s.developer_id LIKE ? OR s.category LIKE ? OR s.summary LIKE ?)"
		args = append(args, like, like, like, like, like, like, like, like, like, like)
	}
	args = append(args, limit)
	rows, err := r.db.QueryContext(ctx, `
	SELECT
	  a.platform,
	  a.app_id,
	  COALESCE(NULLIF(s.title, ''), a.title, a.app_id) AS title,
	  COALESCE(NULLIF(s.developer, ''), a.developer) AS developer,
	  COALESCE(NULLIF(s.developer_id, ''), a.developer_id) AS developer_id,
	  COALESCE(NULLIF(s.category, ''), a.category) AS category,
	  s.summary,
	  s.rating,
	  s.ratings_count,
	  s.reviews_count,
	  s.installs,
	  s.min_installs,
	  s.price,
	  s.currency,
	  s.free,
	  s.has_iap,
	  COALESCE(NULLIF(s.icon_url, ''), a.icon_url) AS icon_url,
	  a.store_url,
	  a.country,
	  a.lang,
	  a.updated_at,
	  s.captured_at
	FROM store_intel_apps a
	LEFT JOIN store_intel_app_snapshots s
	  ON s.id = (
	    SELECT latest.id
	    FROM store_intel_app_snapshots latest
	    WHERE latest.platform = a.platform
	      AND latest.app_id = a.app_id
	      AND latest.country = a.country
	      AND latest.lang = a.lang
	    ORDER BY latest.captured_at DESC
	    LIMIT 1
	  )
	WHERE `+where+`
	ORDER BY a.updated_at DESC, title ASC
	LIMIT ?`, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []dto.AppSummary{}
	for rows.Next() {
		item, err := scanCachedApp(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (r *SQLRepo) UpsertTrackedKeyword(ctx context.Context, input TrackedKeywordInput) (dto.TrackedKeyword, error) {
	if r == nil || r.db == nil {
		return dto.TrackedKeyword{}, ErrNotFound
	}
	input = normalizeTrackedKeywordInput(input)
	_, err := r.db.ExecContext(ctx, `
INSERT INTO store_intel_tracked_keywords (
  platform, app_id, keyword, country, lang, frequency, enabled,
  last_synced_at, consecutive_failures, last_failed_at, created_at, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, '', 0, '', ?, ?)
ON DUPLICATE KEY UPDATE
  enabled = ?,
  frequency = CASE WHEN ? = '' THEN frequency ELSE ? END,
  updated_at = ?`,
		input.Platform, input.AppID, input.Keyword, input.Country, input.Lang,
		coalesce(input.Frequency, "daily"), boolInt(input.Enabled), input.NowISO, input.NowISO,
		boolInt(input.Enabled), input.Frequency, input.Frequency, input.NowISO,
	)
	if err != nil {
		return dto.TrackedKeyword{}, err
	}
	return r.getTrackedKeyword(ctx, input)
}

func (r *SQLRepo) ListTrackedKeywords(ctx context.Context, filter TrackedMonitorFilter) ([]dto.TrackedKeyword, error) {
	if r == nil || r.db == nil {
		return nil, ErrNotFound
	}
	query := `
SELECT id, platform, keyword, app_id, country, lang, frequency, enabled,
       last_synced_at, consecutive_failures, last_failed_at, created_at, updated_at
FROM store_intel_tracked_keywords`
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
	var items []dto.TrackedKeyword
	for rows.Next() {
		item, err := scanTrackedKeyword(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (r *SQLRepo) RemoveTrackedKeyword(ctx context.Context, input TrackedKeywordInput) (int, error) {
	if r == nil || r.db == nil {
		return 0, ErrNotFound
	}
	input = normalizeTrackedKeywordInput(input)
	result, err := r.db.ExecContext(ctx, `
DELETE FROM store_intel_tracked_keywords
WHERE platform = ? AND keyword = ? AND app_id = ? AND country = ? AND lang = ?`,
		input.Platform, input.Keyword, input.AppID, input.Country, input.Lang,
	)
	return rowsAffected(result, err)
}

func (r *SQLRepo) SetTrackedKeywordEnabled(ctx context.Context, input TrackedKeywordInput, enabled bool, updatedAt string) (bool, int, error) {
	if r == nil || r.db == nil {
		return enabled, 0, ErrNotFound
	}
	input = normalizeTrackedKeywordInput(input)
	result, err := r.db.ExecContext(ctx, `
UPDATE store_intel_tracked_keywords
SET enabled = ?, updated_at = ?
WHERE platform = ? AND keyword = ? AND app_id = ? AND country = ? AND lang = ?`,
		boolInt(enabled), updatedAt, input.Platform, input.Keyword, input.AppID, input.Country, input.Lang,
	)
	updated, err := rowsAffected(result, err)
	return enabled, updated, err
}

func (r *SQLRepo) SetTrackedKeywordFrequency(ctx context.Context, input TrackedKeywordInput, frequency, updatedAt string) (string, int, error) {
	if r == nil || r.db == nil {
		return frequency, 0, ErrNotFound
	}
	input = normalizeTrackedKeywordInput(input)
	result, err := r.db.ExecContext(ctx, `
UPDATE store_intel_tracked_keywords
SET frequency = ?, updated_at = ?
WHERE platform = ? AND keyword = ? AND app_id = ? AND country = ? AND lang = ?`,
		frequency, updatedAt, input.Platform, input.Keyword, input.AppID, input.Country, input.Lang,
	)
	updated, err := rowsAffected(result, err)
	return frequency, updated, err
}

func (r *SQLRepo) UpdateTrackedKeywordSyncSuccess(ctx context.Context, input TrackedKeywordInput, syncedAt string) (int, error) {
	if r == nil || r.db == nil {
		return 0, ErrNotFound
	}
	input = normalizeTrackedKeywordInput(input)
	priorFailures, err := r.trackedKeywordFailureCount(ctx, input)
	if err != nil {
		return 0, err
	}
	result, err := r.db.ExecContext(ctx, `
UPDATE store_intel_tracked_keywords
SET last_synced_at = ?, consecutive_failures = 0, last_failed_at = '', updated_at = ?
WHERE platform = ? AND keyword = ? AND app_id = ? AND country = ? AND lang = ?`,
		syncedAt, syncedAt, input.Platform, input.Keyword, input.AppID, input.Country, input.Lang,
	)
	if err := errOrNotFound(result, err); err != nil {
		return 0, err
	}
	return priorFailures, nil
}

func (r *SQLRepo) RecordTrackedKeywordFailure(ctx context.Context, input TrackedKeywordInput, failedAt, _ string) (int, error) {
	if r == nil || r.db == nil {
		return 0, ErrNotFound
	}
	input = normalizeTrackedKeywordInput(input)
	result, err := r.db.ExecContext(ctx, `
UPDATE store_intel_tracked_keywords
SET consecutive_failures = consecutive_failures + 1, last_failed_at = ?, updated_at = ?
WHERE platform = ? AND keyword = ? AND app_id = ? AND country = ? AND lang = ?`,
		failedAt, failedAt, input.Platform, input.Keyword, input.AppID, input.Country, input.Lang,
	)
	if err := errOrNotFound(result, err); err != nil {
		return 0, err
	}
	var count int
	err = r.db.QueryRowContext(ctx, `
SELECT consecutive_failures
FROM store_intel_tracked_keywords
WHERE platform = ? AND keyword = ? AND app_id = ? AND country = ? AND lang = ?`,
		input.Platform, input.Keyword, input.AppID, input.Country, input.Lang,
	).Scan(&count)
	if err != nil {
		return 0, normalizeSQLErr(err)
	}
	return count, nil
}

func (r *SQLRepo) UpsertTrackedChartApp(ctx context.Context, input TrackedChartAppInput) (dto.TrackedChartApp, error) {
	if r == nil || r.db == nil {
		return dto.TrackedChartApp{}, ErrNotFound
	}
	input = normalizeTrackedChartAppInput(input)
	_, err := r.db.ExecContext(ctx, `
INSERT INTO store_intel_tracked_chart_apps (
  platform, app_id, collection, category, country, lang, frequency, enabled,
  last_synced_at, consecutive_failures, last_failed_at, created_at, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', 0, '', ?, ?)
ON DUPLICATE KEY UPDATE
  enabled = ?,
  frequency = CASE WHEN ? = '' THEN frequency ELSE ? END,
  updated_at = ?`,
		input.Platform, input.AppID, input.Collection, input.Category, input.Country, input.Lang,
		coalesce(input.Frequency, "daily"), boolInt(input.Enabled), input.NowISO, input.NowISO,
		boolInt(input.Enabled), input.Frequency, input.Frequency, input.NowISO,
	)
	if err != nil {
		return dto.TrackedChartApp{}, err
	}
	return r.getTrackedChartApp(ctx, input)
}

func (r *SQLRepo) ListTrackedChartApps(ctx context.Context, filter TrackedMonitorFilter) ([]dto.TrackedChartApp, error) {
	if r == nil || r.db == nil {
		return nil, ErrNotFound
	}
	query := `
SELECT id, platform, app_id, collection, category, country, lang, frequency, enabled,
       last_synced_at, consecutive_failures, last_failed_at, created_at, updated_at
FROM store_intel_tracked_chart_apps`
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
	var items []dto.TrackedChartApp
	for rows.Next() {
		item, err := scanTrackedChartApp(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (r *SQLRepo) RemoveTrackedChartApp(ctx context.Context, input TrackedChartAppInput) (int, error) {
	if r == nil || r.db == nil {
		return 0, ErrNotFound
	}
	input = normalizeTrackedChartAppInput(input)
	result, err := r.db.ExecContext(ctx, `
DELETE FROM store_intel_tracked_chart_apps
WHERE platform = ? AND app_id = ? AND collection = ? AND category = ? AND country = ? AND lang = ?`,
		input.Platform, input.AppID, input.Collection, input.Category, input.Country, input.Lang,
	)
	return rowsAffected(result, err)
}

func (r *SQLRepo) SetTrackedChartAppEnabled(ctx context.Context, input TrackedChartAppInput, enabled bool, updatedAt string) (bool, int, error) {
	if r == nil || r.db == nil {
		return enabled, 0, ErrNotFound
	}
	input = normalizeTrackedChartAppInput(input)
	result, err := r.db.ExecContext(ctx, `
UPDATE store_intel_tracked_chart_apps
SET enabled = ?, updated_at = ?
WHERE platform = ? AND app_id = ? AND collection = ? AND category = ? AND country = ? AND lang = ?`,
		boolInt(enabled), updatedAt, input.Platform, input.AppID, input.Collection, input.Category,
		input.Country, input.Lang,
	)
	updated, err := rowsAffected(result, err)
	return enabled, updated, err
}

func (r *SQLRepo) UpdateTrackedChartAppSyncSuccess(ctx context.Context, input TrackedChartAppInput, syncedAt string) (int, error) {
	if r == nil || r.db == nil {
		return 0, ErrNotFound
	}
	input = normalizeTrackedChartAppInput(input)
	priorFailures, err := r.trackedChartAppFailureCount(ctx, input)
	if err != nil {
		return 0, err
	}
	result, err := r.db.ExecContext(ctx, `
UPDATE store_intel_tracked_chart_apps
SET last_synced_at = ?, consecutive_failures = 0, last_failed_at = '', updated_at = ?
WHERE platform = ? AND app_id = ? AND collection = ? AND category = ? AND country = ? AND lang = ?`,
		syncedAt, syncedAt, input.Platform, input.AppID, input.Collection, input.Category,
		input.Country, input.Lang,
	)
	if err := errOrNotFound(result, err); err != nil {
		return 0, err
	}
	return priorFailures, nil
}

func (r *SQLRepo) RecordTrackedChartAppFailure(ctx context.Context, input TrackedChartAppInput, failedAt, _ string) (int, error) {
	if r == nil || r.db == nil {
		return 0, ErrNotFound
	}
	input = normalizeTrackedChartAppInput(input)
	result, err := r.db.ExecContext(ctx, `
UPDATE store_intel_tracked_chart_apps
SET consecutive_failures = consecutive_failures + 1, last_failed_at = ?, updated_at = ?
WHERE platform = ? AND app_id = ? AND collection = ? AND category = ? AND country = ? AND lang = ?`,
		failedAt, failedAt, input.Platform, input.AppID, input.Collection, input.Category,
		input.Country, input.Lang,
	)
	if err := errOrNotFound(result, err); err != nil {
		return 0, err
	}
	var count int
	err = r.db.QueryRowContext(ctx, `
SELECT consecutive_failures
FROM store_intel_tracked_chart_apps
WHERE platform = ? AND app_id = ? AND collection = ? AND category = ? AND country = ? AND lang = ?`,
		input.Platform, input.AppID, input.Collection, input.Category, input.Country, input.Lang,
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
	day := dayKey(input.CapturedAt)
	values, err := buildAppSnapshotValues(input, identity, day)
	if err != nil {
		return SnapshotUpsertResult{}, err
	}
	current := values.record()
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
	if existingID > 0 {
		args := append(append([]any{}, values.args...), input.CapturedAt, existingID)
		_, err = r.db.ExecContext(ctx, buildUpdateSQL("store_intel_app_snapshots", appSnapshotColumns, "id = ?"), args...)
		if err != nil {
			return SnapshotUpsertResult{}, err
		}
		return SnapshotUpsertResult{Previous: previous, Current: current, FirstOfDay: false}, nil
	}
	insertColumns := append(append([]string{}, appSnapshotColumns...), "created_at", "updated_at")
	args := append(append([]any{}, values.args...), input.CapturedAt, input.CapturedAt)
	_, err = r.db.ExecContext(ctx, buildInsertSQL("store_intel_app_snapshots", insertColumns), args...)
	if err != nil {
		return SnapshotUpsertResult{}, err
	}
	return SnapshotUpsertResult{Previous: previous, Current: current, FirstOfDay: true}, nil
}

func (r *SQLRepo) LatestAppSnapshot(ctx context.Context, filter LatestAppSnapshotFilter) (SnapshotRecord, error) {
	if r == nil || r.db == nil {
		return SnapshotRecord{}, ErrNotFound
	}
	identity := normalizeIdentity(dto.AppIdentity{
		Platform: filter.Platform,
		AppID:    strings.TrimSpace(filter.AppID),
		Country:  filter.Country,
		Lang:     filter.Lang,
	})
	row := r.db.QueryRowContext(ctx, fmt.Sprintf(`
	SELECT %s
	FROM store_intel_app_snapshots
	WHERE platform = ? AND app_id = ? AND country = ? AND lang = ?
	ORDER BY captured_at DESC LIMIT 1`, columnList(appSnapshotSelectColumns)),
		identity.Platform, identity.AppID, identity.Country, identity.Lang,
	)
	return scanSnapshot(row)
}

func (r *SQLRepo) ListAppSnapshotHistory(ctx context.Context, filter AppSnapshotHistoryFilter) ([]dto.AppSnapshot, error) {
	if r == nil || r.db == nil {
		return nil, ErrNotFound
	}
	identity := normalizeIdentity(dto.AppIdentity{
		Platform: filter.Platform,
		AppID:    strings.TrimSpace(filter.AppID),
		Country:  filter.Country,
		Lang:     filter.Lang,
	})
	args := []any{identity.Platform, identity.AppID, identity.Country, identity.Lang}
	selectColumns := columnList(appSnapshotSelectColumns)
	query := fmt.Sprintf(`
	SELECT %s
	FROM store_intel_app_snapshots
	WHERE platform = ? AND app_id = ? AND country = ? AND lang = ?`, selectColumns)
	if filter.Limit > 0 {
		query = fmt.Sprintf(`
	SELECT %s
	FROM (
	  SELECT %s
	  FROM store_intel_app_snapshots
	  WHERE platform = ? AND app_id = ? AND country = ? AND lang = ?
	  ORDER BY captured_at DESC
	  LIMIT ?
	) AS recent_app_snapshots`, selectColumns, selectColumns)
		args = append(args, filter.Limit)
	}
	query += " ORDER BY captured_at ASC"
	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []dto.AppSnapshot{}
	for rows.Next() {
		record, err := scanSnapshot(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, record.DTO())
	}
	return items, rows.Err()
}

func (r *SQLRepo) ListRecentAppSnapshots(ctx context.Context, filter AppSnapshotRecentFilter) ([]dto.AppSnapshot, error) {
	if r == nil || r.db == nil {
		return nil, ErrNotFound
	}
	limit := filter.Limit
	if limit <= 0 {
		limit = 8
	}
	rows, err := r.db.QueryContext(ctx, fmt.Sprintf(`
	SELECT %s
	FROM store_intel_app_snapshots
	ORDER BY captured_at DESC
	LIMIT ?`, columnList(appSnapshotSelectColumns)), limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []dto.AppSnapshot{}
	for rows.Next() {
		record, err := scanSnapshot(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, record.DTO())
	}
	return items, rows.Err()
}

func (r *SQLRepo) CountAppSnapshots(ctx context.Context) (int, error) {
	if r == nil || r.db == nil {
		return 0, ErrNotFound
	}
	var total int
	err := r.db.QueryRowContext(ctx, "SELECT COUNT(*) FROM store_intel_app_snapshots").Scan(&total)
	if err != nil {
		return 0, err
	}
	return total, nil
}

func (r *SQLRepo) SaveChartSnapshot(ctx context.Context, input SaveChartSnapshotInput) (int, error) {
	if r == nil || r.db == nil {
		return 0, ErrNotFound
	}
	saved := 0
	for _, item := range input.Items {
		rawJSON, err := jsonColumn(item.Raw)
		if err != nil {
			return 0, err
		}
		result, err := r.db.ExecContext(ctx, `
	INSERT INTO store_intel_chart_snapshots (
	  platform, chart_type, category, country, lang, captured_at, rank, app_id,
	  title, developer, rating, installs, icon_url, raw_json
	) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
			coalesce(item.Platform, dto.PlatformGooglePlay),
			coalesce(input.ChartType, item.ChartType, "top_free"),
			nullableString(input.Category),
			strings.ToLower(coalesce(input.Country, item.Country, "us")),
			strings.ToLower(coalesce(input.Lang, item.Lang, "en")),
			input.CapturedAt,
			item.Rank,
			item.AppID,
			nullableString(item.Title),
			nullableString(item.Developer),
			nullableFloat(item.Rating),
			nullableString(item.Installs),
			nullableString(item.IconURL),
			rawJSON,
		)
		if err != nil {
			return 0, err
		}
		count, _ := result.RowsAffected()
		saved += int(count)
	}
	return saved, nil
}

func (r *SQLRepo) ListLatestChartSnapshot(ctx context.Context, filter LatestChartSnapshotFilter) ([]dto.ChartItem, string, error) {
	if r == nil || r.db == nil {
		return nil, "", ErrNotFound
	}
	filter.Platform = coalesce(filter.Platform, dto.PlatformGooglePlay)
	filter.ChartType = coalesce(filter.ChartType, "top_free")
	filter.Category = strings.TrimSpace(filter.Category)
	filter.Country = strings.ToLower(coalesce(filter.Country, "us"))
	filter.Lang = strings.ToLower(coalesce(filter.Lang, "en"))
	limit := filter.Limit
	if limit <= 0 || limit > 200 {
		limit = 100
	}
	var capturedAt string
	err := r.db.QueryRowContext(ctx, `
	SELECT captured_at
	FROM store_intel_chart_snapshots
	WHERE platform = ? AND chart_type = ? AND COALESCE(category, '') = ? AND country = ? AND lang = ?
	ORDER BY captured_at DESC
	LIMIT 1`,
		filter.Platform, filter.ChartType, filter.Category, filter.Country, filter.Lang,
	).Scan(&capturedAt)
	if err != nil {
		return nil, "", normalizeSQLErr(err)
	}
	rows, err := r.db.QueryContext(ctx, `
	SELECT platform, chart_type, COALESCE(category, ''), country, lang, rank, app_id,
	       title, developer, rating, installs, icon_url, raw_json
	FROM store_intel_chart_snapshots
	WHERE platform = ? AND chart_type = ? AND COALESCE(category, '') = ? AND country = ? AND lang = ? AND captured_at = ?
	ORDER BY rank ASC
	LIMIT ?`,
		filter.Platform, filter.ChartType, filter.Category, filter.Country, filter.Lang, capturedAt, limit,
	)
	if err != nil {
		return nil, "", err
	}
	defer rows.Close()
	items := []dto.ChartItem{}
	for rows.Next() {
		item, err := scanChartItem(rows)
		if err != nil {
			return nil, "", err
		}
		items = append(items, item)
	}
	return items, capturedAt, rows.Err()
}

func (r *SQLRepo) UpsertChartRank(ctx context.Context, input ChartRankUpsertInput) (dto.ChartRankResponse, bool, error) {
	if r == nil || r.db == nil {
		return dto.ChartRankResponse{}, false, ErrNotFound
	}
	current := chartRankSnapshot(input)
	var existingID uint64
	err := r.db.QueryRowContext(ctx, `
	SELECT id FROM store_intel_chart_rank_snapshots
	WHERE platform = ? AND app_id = ? AND collection = ? AND category = ?
	  AND country = ? AND lang = ? AND captured_day = ?
	ORDER BY captured_at DESC LIMIT 1`,
		current.Platform, current.AppID, current.Collection, current.Category,
		current.Country, current.Lang, input.CapturedDay,
	).Scan(&existingID)
	if err != nil && !errors.Is(err, sql.ErrNoRows) {
		return dto.ChartRankResponse{}, false, err
	}
	if existingID > 0 {
		_, err = r.db.ExecContext(ctx, `
	UPDATE store_intel_chart_rank_snapshots
	SET rank = ?, found = ?, checked_limit = ?, captured_at = ?
	WHERE id = ?`,
			nullableInt(current.Rank), boolInt(current.Found), current.CheckedLimit,
			current.CapturedAt, existingID,
		)
		if err != nil {
			return dto.ChartRankResponse{}, false, err
		}
		return current, false, nil
	}
	_, err = r.db.ExecContext(ctx, `
	INSERT INTO store_intel_chart_rank_snapshots (
	  platform, app_id, collection, category, country, lang, rank, found,
	  checked_limit, captured_at, captured_day, raw_json
	) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
		current.Platform, current.AppID, current.Collection, current.Category,
		current.Country, current.Lang, nullableInt(current.Rank), boolInt(current.Found),
		current.CheckedLimit, current.CapturedAt, input.CapturedDay, "{}",
	)
	if err != nil {
		return dto.ChartRankResponse{}, false, err
	}
	return current, true, nil
}

func (r *SQLRepo) ListChartRankHistory(ctx context.Context, filter ChartRankHistoryFilter) ([]dto.ChartRankResponse, error) {
	if r == nil || r.db == nil {
		return nil, ErrNotFound
	}
	filter.Platform = coalesce(filter.Platform, dto.PlatformGooglePlay)
	filter.Collection = coalesce(filter.Collection, "top_free")
	filter.Category = coalesce(filter.Category, "APPLICATION")
	filter.Country = strings.ToLower(coalesce(filter.Country, "us"))
	filter.Lang = strings.ToLower(coalesce(filter.Lang, "en"))
	args := []any{filter.Platform, strings.TrimSpace(filter.AppID), filter.Collection, filter.Category, filter.Country, filter.Lang}
	query := `
	SELECT platform, app_id, collection, category, country, lang, rank, found, checked_limit, captured_at
	FROM store_intel_chart_rank_snapshots
	WHERE platform = ? AND app_id = ? AND collection = ? AND category = ? AND country = ? AND lang = ?`
	if filter.Limit > 0 {
		query = `
	SELECT platform, app_id, collection, category, country, lang, rank, found, checked_limit, captured_at
	FROM (
	  SELECT platform, app_id, collection, category, country, lang, rank, found, checked_limit, captured_at
	  FROM store_intel_chart_rank_snapshots
	  WHERE platform = ? AND app_id = ? AND collection = ? AND category = ? AND country = ? AND lang = ?
	  ORDER BY captured_at DESC
	  LIMIT ?
	) AS recent_chart_ranks`
		args = append(args, filter.Limit)
	}
	query += " ORDER BY captured_at ASC"
	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var items []dto.ChartRankResponse
	for rows.Next() {
		item, err := scanChartRank(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (r *SQLRepo) UpsertKeywordRank(ctx context.Context, input KeywordRankUpsertInput) (KeywordRankUpsertResult, error) {
	if r == nil || r.db == nil {
		return KeywordRankUpsertResult{}, ErrNotFound
	}
	current := keywordRankSnapshot(input)
	rawJSON, err := json.Marshal(input.Result.Results)
	if err != nil {
		return KeywordRankUpsertResult{}, err
	}
	var existingID uint64
	err = r.db.QueryRowContext(ctx, `
	SELECT id FROM store_intel_keyword_ranks
	WHERE platform = ? AND keyword = ? AND app_id = ? AND country = ? AND lang = ? AND captured_day = ?
	ORDER BY captured_at DESC LIMIT 1`,
		current.Platform, current.Keyword, current.AppID, current.Country, current.Lang, input.CapturedDay,
	).Scan(&existingID)
	if err != nil && !errors.Is(err, sql.ErrNoRows) {
		return KeywordRankUpsertResult{}, err
	}
	_, err = r.db.ExecContext(ctx, `
	INSERT INTO store_intel_keyword_ranks (
	  platform, keyword, app_id, country, lang, rank, found, checked_limit,
	  captured_at, captured_day, raw_json
	) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	ON DUPLICATE KEY UPDATE
	  rank = VALUES(rank),
	  found = VALUES(found),
	  checked_limit = VALUES(checked_limit),
	  captured_at = VALUES(captured_at),
	  raw_json = VALUES(raw_json)`,
		current.Platform, current.Keyword, current.AppID, current.Country, current.Lang,
		nullableInt(current.Rank), boolInt(current.Found), current.CheckedLimit,
		current.CapturedAt, input.CapturedDay, string(rawJSON),
	)
	if err != nil {
		return KeywordRankUpsertResult{}, err
	}
	return KeywordRankUpsertResult{Current: current, FirstOfDay: existingID == 0}, nil
}

func (r *SQLRepo) ListKeywordRankHistory(ctx context.Context, filter KeywordRankHistoryFilter) ([]dto.KeywordRankSnapshot, error) {
	if r == nil || r.db == nil {
		return nil, ErrNotFound
	}
	filter.Platform = coalesce(filter.Platform, dto.PlatformGooglePlay)
	filter.Country = strings.ToLower(coalesce(filter.Country, "us"))
	filter.Lang = strings.ToLower(coalesce(filter.Lang, "en"))
	args := []any{filter.Platform, strings.TrimSpace(filter.Keyword), strings.TrimSpace(filter.AppID), filter.Country, filter.Lang}
	query := `
	SELECT platform, keyword, app_id, country, lang, rank, found, checked_limit, captured_at
	FROM store_intel_keyword_ranks
	WHERE platform = ? AND keyword = ? AND app_id = ? AND country = ? AND lang = ?`
	if filter.Limit > 0 {
		query = `
	SELECT platform, keyword, app_id, country, lang, rank, found, checked_limit, captured_at
	FROM (
	  SELECT platform, keyword, app_id, country, lang, rank, found, checked_limit, captured_at
	  FROM store_intel_keyword_ranks
	  WHERE platform = ? AND keyword = ? AND app_id = ? AND country = ? AND lang = ?
	  ORDER BY captured_at DESC
	  LIMIT ?
	) AS recent_keyword_ranks`
		args = append(args, filter.Limit)
	}
	query += " ORDER BY captured_at ASC"
	rows, err := r.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var items []dto.KeywordRankSnapshot
	for rows.Next() {
		item, err := scanKeywordRank(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (r *SQLRepo) ListRecentKeywordRanks(ctx context.Context, filter KeywordRankRecentFilter) ([]dto.KeywordRankSnapshot, error) {
	if r == nil || r.db == nil {
		return nil, ErrNotFound
	}
	filter.Platform = coalesce(filter.Platform, dto.PlatformGooglePlay)
	filter.AppID = strings.TrimSpace(filter.AppID)
	filter.Country = strings.ToLower(strings.TrimSpace(filter.Country))
	filter.Lang = strings.ToLower(strings.TrimSpace(filter.Lang))
	clauses := []string{"platform = ?"}
	args := []any{filter.Platform}
	if filter.AppID != "" {
		clauses = append(clauses, "app_id = ?")
		args = append(args, filter.AppID)
	}
	if filter.Country != "" {
		clauses = append(clauses, "country = ?")
		args = append(args, filter.Country)
	}
	if filter.Lang != "" {
		clauses = append(clauses, "lang = ?")
		args = append(args, filter.Lang)
	}
	limit := filter.Limit
	if limit <= 0 {
		limit = 8
	}
	args = append(args, limit)
	rows, err := r.db.QueryContext(ctx, `
	SELECT platform, keyword, app_id, country, lang, rank, found, checked_limit, captured_at
	FROM store_intel_keyword_ranks
	WHERE `+strings.Join(clauses, " AND ")+`
	ORDER BY captured_at DESC
	LIMIT ?`, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []dto.KeywordRankSnapshot{}
	for rows.Next() {
		item, err := scanKeywordRank(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (r *SQLRepo) RecordKeywordCorpus(ctx context.Context, input KeywordCorpusRecordInput) (int, error) {
	if r == nil || r.db == nil {
		return 0, ErrNotFound
	}
	input = normalizeKeywordCorpusRecordInput(input)
	if len(input.Items) == 0 {
		return 0, nil
	}
	tx, err := r.db.BeginTx(ctx, nil)
	if err != nil {
		return 0, err
	}
	defer tx.Rollback()

	keywords := make([]string, 0, len(input.Items))
	for _, item := range input.Items {
		keywords = append(keywords, item.Keyword)
	}
	existing, err := existingKeywordCorpus(ctx, tx, input.Platform, input.Country, input.Lang, keywords)
	if err != nil {
		return 0, err
	}
	added := 0
	for _, item := range input.Items {
		if !existing[item.Keyword] {
			added++
		}
		if _, err := tx.ExecContext(ctx, keywordCorpusUpsertSQL(),
			input.Platform, input.Country, input.Lang, item.Keyword, nullableString(item.Source),
			boolInt(item.Confirmed), item.HitCount, input.SeenAt, input.SeenAt,
		); err != nil {
			return 0, err
		}
	}
	if err := tx.Commit(); err != nil {
		return 0, err
	}
	return added, nil
}

func (r *SQLRepo) ListKeywordCorpus(ctx context.Context, filter KeywordCorpusFilter) ([]KeywordCorpusItem, error) {
	if r == nil || r.db == nil {
		return nil, ErrNotFound
	}
	filter = normalizeKeywordCorpusFilter(filter)
	rows, err := r.db.QueryContext(ctx, `
	SELECT platform, country, lang, keyword, source, confirmed, hit_count, first_seen_at, last_seen_at
	FROM store_intel_keyword_corpus
	WHERE platform = ? AND country = ? AND lang = ?
	ORDER BY confirmed DESC, hit_count DESC, last_seen_at DESC
	LIMIT ?`, filter.Platform, filter.Country, filter.Lang, filter.Limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	items := []KeywordCorpusItem{}
	for rows.Next() {
		item, err := scanKeywordCorpus(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (r *SQLRepo) UpsertKeywordCoverage(ctx context.Context, input KeywordCoverageUpsertInput) error {
	if r == nil || r.db == nil {
		return ErrNotFound
	}
	result := input.Result
	result.Platform = coalesce(result.Platform, dto.PlatformGooglePlay)
	result.AppID = strings.TrimSpace(result.AppID)
	result.Country = strings.ToLower(coalesce(result.Country, "us"))
	result.Lang = strings.ToLower(coalesce(result.Lang, "en"))
	result.CapturedAt = coalesce(input.CapturedAt, result.CapturedAt)
	if result.CandidateCount == 0 {
		result.CandidateCount = len(result.Candidates)
	}
	candidatesJSON, err := jsonColumn(result.Candidates)
	if err != nil {
		return err
	}
	coveredJSON, err := jsonColumn(result.Covered)
	if err != nil {
		return err
	}
	_, err = r.db.ExecContext(ctx, `
	INSERT INTO store_intel_keyword_coverage (
	  platform, app_id, canonical_app_id, country, lang, deep, candidates_json,
	  candidate_count, covered_json, checked_limit, captured_at
	) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	ON DUPLICATE KEY UPDATE
	  canonical_app_id = VALUES(canonical_app_id),
	  candidates_json = VALUES(candidates_json),
	  candidate_count = VALUES(candidate_count),
	  covered_json = VALUES(covered_json),
	  checked_limit = VALUES(checked_limit),
	  captured_at = VALUES(captured_at)`,
		result.Platform, result.AppID, nullableString(result.CanonicalAppID), result.Country,
		result.Lang, boolInt(result.Deep), candidatesJSON, result.CandidateCount, coveredJSON,
		result.CheckedLimit, result.CapturedAt,
	)
	return err
}

func (r *SQLRepo) LatestKeywordCoverage(ctx context.Context, filter KeywordCoverageLatestFilter) (dto.KeywordCoverageResponse, error) {
	if r == nil || r.db == nil {
		return dto.KeywordCoverageResponse{}, ErrNotFound
	}
	filter.Platform = coalesce(filter.Platform, dto.PlatformGooglePlay)
	filter.AppID = strings.TrimSpace(filter.AppID)
	filter.Country = strings.ToLower(coalesce(filter.Country, "us"))
	filter.Lang = strings.ToLower(coalesce(filter.Lang, "en"))
	row := r.db.QueryRowContext(ctx, `
	SELECT platform, app_id, COALESCE(canonical_app_id, ''), country, lang, deep,
	       candidates_json, candidate_count, covered_json, checked_limit, captured_at
	FROM store_intel_keyword_coverage
	WHERE platform = ? AND app_id = ? AND country = ? AND lang = ? AND deep = ?
	ORDER BY captured_at DESC
	LIMIT 1`,
		filter.Platform, filter.AppID, filter.Country, filter.Lang, boolInt(filter.Deep),
	)
	return scanKeywordCoverage(row)
}

func (r *SQLRepo) ExistingReviewIDs(ctx context.Context, filter ExistingReviewsFilter) (map[string]bool, error) {
	if r == nil || r.db == nil {
		return nil, ErrNotFound
	}
	identity := normalizeIdentity(filter.Identity)
	ids := make([]string, 0, len(filter.ReviewIDs))
	seen := map[string]bool{}
	for _, reviewID := range filter.ReviewIDs {
		reviewID = strings.TrimSpace(reviewID)
		if reviewID == "" || seen[reviewID] {
			continue
		}
		seen[reviewID] = true
		ids = append(ids, reviewID)
	}
	existing := map[string]bool{}
	if len(ids) == 0 {
		return existing, nil
	}
	placeholders := make([]string, 0, len(ids))
	args := []any{identity.Platform, identity.AppID}
	for _, reviewID := range ids {
		placeholders = append(placeholders, "?")
		args = append(args, reviewID)
	}
	rows, err := r.db.QueryContext(ctx, `
	SELECT review_id
	FROM store_intel_reviews
	WHERE platform = ? AND app_id = ? AND review_id IN (`+strings.Join(placeholders, ",")+`)`,
		args...,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var reviewID string
		if err := rows.Scan(&reviewID); err != nil {
			return nil, err
		}
		existing[reviewID] = true
	}
	return existing, rows.Err()
}

func (r *SQLRepo) SaveReviews(ctx context.Context, input SaveReviewsInput) (int, error) {
	if r == nil || r.db == nil {
		return 0, ErrNotFound
	}
	identity := normalizeIdentity(input.Identity)
	saved := 0
	for _, item := range input.Items {
		platform := coalesce(item.Platform, identity.Platform)
		rawJSON, err := jsonColumn(item.Raw)
		if err != nil {
			return 0, err
		}
		result, err := r.db.ExecContext(ctx, `
	INSERT IGNORE INTO store_intel_reviews (
	  platform, app_id, country, lang, review_id, user_name, rating, content,
	  app_version, helpful_count, review_created_at, captured_at, raw_json
	) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
			platform, identity.AppID, identity.Country, identity.Lang,
			nullableString(item.ReviewID), nullableString(item.UserName), nullableInt(item.Rating),
			nullableString(item.Content), nullableString(item.AppVersion), nullableInt64(item.HelpfulCount),
			nullableString(item.ReviewCreatedAt), input.CapturedAt, rawJSON,
		)
		if err != nil {
			return 0, err
		}
		count, _ := result.RowsAffected()
		saved += int(count)
	}
	return saved, nil
}

func (r *SQLRepo) ListReviews(ctx context.Context, filter ListReviewsFilter) ([]dto.ReviewItem, error) {
	if r == nil || r.db == nil {
		return nil, ErrNotFound
	}
	limit := filter.Limit
	if limit <= 0 || limit > 1000 {
		limit = 100
	}
	rows, err := r.db.QueryContext(ctx, `
	SELECT platform, app_id, country, lang, review_id, user_name, rating, content,
	       app_version, helpful_count, review_created_at, captured_at, raw_json
	FROM store_intel_reviews
	WHERE app_id = ?
	ORDER BY review_created_at DESC, captured_at DESC, id DESC
	LIMIT ?`,
		strings.TrimSpace(filter.AppID), limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var items []dto.ReviewItem
	for rows.Next() {
		item, err := scanReview(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
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

func (r *SQLRepo) CleanupHistory(ctx context.Context, input HistoryRetentionCleanupInput) (dto.HistoryRetentionCleanupResponse, error) {
	if r == nil || r.db == nil {
		return dto.HistoryRetentionCleanupResponse{}, ErrNotFound
	}
	var result dto.HistoryRetentionCleanupResponse
	var err error
	result.Snapshots, err = r.cleanupPartitionedHistory(ctx, cleanupHistoryQuery{
		Table:       "store_intel_app_snapshots",
		TimeColumn:  "captured_at",
		Partitions:  []string{"platform", "app_id", "country", "lang"},
		Cutoff:      input.SnapshotCutoff,
		MinKeep:     input.MinKeep,
		RankedAlias: "ranked_snapshots",
	})
	if err != nil {
		return dto.HistoryRetentionCleanupResponse{}, err
	}
	result.Keywords, err = r.cleanupPartitionedHistory(ctx, cleanupHistoryQuery{
		Table:       "store_intel_keyword_ranks",
		TimeColumn:  "captured_at",
		Partitions:  []string{"platform", "keyword", "app_id", "country", "lang"},
		Cutoff:      input.KeywordCutoff,
		MinKeep:     input.MinKeep,
		RankedAlias: "ranked_keywords",
	})
	if err != nil {
		return dto.HistoryRetentionCleanupResponse{}, err
	}
	result.Charts, err = r.cleanupPartitionedHistory(ctx, cleanupHistoryQuery{
		Table:       "store_intel_chart_rank_snapshots",
		TimeColumn:  "captured_at",
		Partitions:  []string{"platform", "app_id", "collection", "category", "country", "lang"},
		Cutoff:      input.ChartCutoff,
		MinKeep:     input.MinKeep,
		RankedAlias: "ranked_charts",
	})
	if err != nil {
		return dto.HistoryRetentionCleanupResponse{}, err
	}
	result.Alerts, err = r.cleanupPartitionedHistory(ctx, cleanupHistoryQuery{
		Table:       "store_intel_alerts",
		TimeColumn:  "created_at",
		Partitions:  []string{"app_id"},
		SelectExtra: []string{"is_read"},
		OuterWhere:  " AND is_read = 1",
		Cutoff:      input.AlertCutoff,
		MinKeep:     input.MinKeep,
		RankedAlias: "ranked_alerts",
	})
	if err != nil {
		return dto.HistoryRetentionCleanupResponse{}, err
	}
	result.Reviews, err = r.cleanupPartitionedHistory(ctx, cleanupHistoryQuery{
		Table:       "store_intel_reviews",
		TimeColumn:  "captured_at",
		Partitions:  []string{"platform", "app_id"},
		Cutoff:      input.ReviewCutoff,
		MinKeep:     input.MinKeep,
		RankedAlias: "ranked_reviews",
	})
	if err != nil {
		return dto.HistoryRetentionCleanupResponse{}, err
	}
	return result, nil
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

func (r *SQLRepo) getTrackedKeyword(ctx context.Context, input TrackedKeywordInput) (dto.TrackedKeyword, error) {
	input = normalizeTrackedKeywordInput(input)
	row := r.db.QueryRowContext(ctx, `
SELECT id, platform, keyword, app_id, country, lang, frequency, enabled,
       last_synced_at, consecutive_failures, last_failed_at, created_at, updated_at
FROM store_intel_tracked_keywords
WHERE platform = ? AND keyword = ? AND app_id = ? AND country = ? AND lang = ?`,
		input.Platform, input.Keyword, input.AppID, input.Country, input.Lang,
	)
	return scanTrackedKeyword(row)
}

func (r *SQLRepo) getTrackedChartApp(ctx context.Context, input TrackedChartAppInput) (dto.TrackedChartApp, error) {
	input = normalizeTrackedChartAppInput(input)
	row := r.db.QueryRowContext(ctx, `
SELECT id, platform, app_id, collection, category, country, lang, frequency, enabled,
       last_synced_at, consecutive_failures, last_failed_at, created_at, updated_at
FROM store_intel_tracked_chart_apps
WHERE platform = ? AND app_id = ? AND collection = ? AND category = ? AND country = ? AND lang = ?`,
		input.Platform, input.AppID, input.Collection, input.Category, input.Country, input.Lang,
	)
	return scanTrackedChartApp(row)
}

func (r *SQLRepo) trackedAppFailureCount(ctx context.Context, identity dto.AppIdentity) (int, error) {
	identity = normalizeIdentity(identity)
	var count int
	err := r.db.QueryRowContext(ctx, `
SELECT COALESCE(consecutive_failures, 0)
FROM store_intel_tracked_apps
WHERE platform = ? AND app_id = ? AND country = ? AND lang = ?`,
		identity.Platform, identity.AppID, identity.Country, identity.Lang,
	).Scan(&count)
	if err != nil {
		return 0, normalizeSQLErr(err)
	}
	return count, nil
}

func (r *SQLRepo) trackedKeywordFailureCount(ctx context.Context, input TrackedKeywordInput) (int, error) {
	input = normalizeTrackedKeywordInput(input)
	var count int
	err := r.db.QueryRowContext(ctx, `
SELECT COALESCE(consecutive_failures, 0)
FROM store_intel_tracked_keywords
WHERE platform = ? AND keyword = ? AND app_id = ? AND country = ? AND lang = ?`,
		input.Platform, input.Keyword, input.AppID, input.Country, input.Lang,
	).Scan(&count)
	if err != nil {
		return 0, normalizeSQLErr(err)
	}
	return count, nil
}

func (r *SQLRepo) trackedChartAppFailureCount(ctx context.Context, input TrackedChartAppInput) (int, error) {
	input = normalizeTrackedChartAppInput(input)
	var count int
	err := r.db.QueryRowContext(ctx, `
SELECT COALESCE(consecutive_failures, 0)
FROM store_intel_tracked_chart_apps
WHERE platform = ? AND app_id = ? AND collection = ? AND category = ? AND country = ? AND lang = ?`,
		input.Platform, input.AppID, input.Collection, input.Category, input.Country, input.Lang,
	).Scan(&count)
	if err != nil {
		return 0, normalizeSQLErr(err)
	}
	return count, nil
}

func (r *SQLRepo) previousSnapshot(ctx context.Context, identity dto.AppIdentity, day string) (*SnapshotRecord, error) {
	row := r.db.QueryRowContext(ctx, fmt.Sprintf(`
SELECT %s
FROM store_intel_app_snapshots
WHERE platform = ? AND app_id = ? AND country = ? AND lang = ? AND captured_day <> ?
ORDER BY captured_at DESC LIMIT 1`, columnList(appSnapshotSelectColumns)),
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

func scanRefreshJob(row rowScanner) (dto.RefreshJobResponse, error) {
	var job dto.RefreshJobResponse
	err := row.Scan(
		&job.JobID, &job.Kind, &job.Status, &job.Message, &job.RequestedAt,
		&job.StartedAt, &job.FinishedAt, &job.UpdatedAt,
	)
	if err != nil {
		return dto.RefreshJobResponse{}, normalizeSQLErr(err)
	}
	return job, nil
}

func scanRefreshJobRecord(row rowScanner) (dto.RefreshJobRecord, error) {
	var record dto.RefreshJobRecord
	var requestJSON string
	err := row.Scan(
		&record.Job.JobID, &record.Job.Kind, &record.Job.Status, &record.Job.Message,
		&record.Job.RequestedAt, &record.Job.StartedAt, &record.Job.FinishedAt,
		&record.Job.UpdatedAt, &requestJSON,
	)
	if err != nil {
		return dto.RefreshJobRecord{}, normalizeSQLErr(err)
	}
	if strings.TrimSpace(requestJSON) != "" {
		if err := json.Unmarshal([]byte(requestJSON), &record.Request); err != nil {
			return dto.RefreshJobRecord{}, err
		}
	}
	return record, nil
}

func scanTrackedKeyword(row rowScanner) (dto.TrackedKeyword, error) {
	var item dto.TrackedKeyword
	var enabled int
	var lastSyncedAt, lastFailedAt sql.NullString
	err := row.Scan(
		&item.ID, &item.Platform, &item.Keyword, &item.AppID, &item.Country, &item.Lang,
		&item.Frequency, &enabled, &lastSyncedAt, &item.ConsecutiveFailures,
		&lastFailedAt, &item.CreatedAt, &item.UpdatedAt,
	)
	if err != nil {
		return dto.TrackedKeyword{}, normalizeSQLErr(err)
	}
	item.Enabled = enabled != 0
	item.LastSyncedAt = lastSyncedAt.String
	item.LastFailedAt = lastFailedAt.String
	return item, nil
}

func scanTrackedChartApp(row rowScanner) (dto.TrackedChartApp, error) {
	var item dto.TrackedChartApp
	var enabled int
	var category, lastSyncedAt, lastFailedAt sql.NullString
	err := row.Scan(
		&item.ID, &item.Platform, &item.AppID, &item.Collection, &category, &item.Country,
		&item.Lang, &item.Frequency, &enabled, &lastSyncedAt, &item.ConsecutiveFailures,
		&lastFailedAt, &item.CreatedAt, &item.UpdatedAt,
	)
	if err != nil {
		return dto.TrackedChartApp{}, normalizeSQLErr(err)
	}
	item.Category = category.String
	item.Enabled = enabled != 0
	item.LastSyncedAt = lastSyncedAt.String
	item.LastFailedAt = lastFailedAt.String
	return item, nil
}

func scanSnapshot(row rowScanner) (SnapshotRecord, error) {
	var record SnapshotRecord
	var (
		rawJSON, title, developer, category, installs, price, version, updated, released sql.NullString
		androidVersion, contentRating, description, summary, changelog, iconURL          sql.NullString
		screenshotsJSON, genreID, developerID, currency                                  sql.NullString
		developerEmail, developerWebsite, developerAddress, developerPhone               sql.NullString
		publisherCountry, privacyPolicy, headerImage, video                              sql.NullString
		contentRatingDescription, appBundle                                              sql.NullString
		histogramJSON, categoriesJSON, permissionsJSON, dataSafetyJSON                   sql.NullString
		rating, originalPrice                                                            sql.NullFloat64
		ratingsCount, reviewsCount, minInstalls, realInstalls                            sql.NullInt64
		dailyInstalls, minDailyInstalls, realDailyInstalls                               sql.NullInt64
		monthlyInstalls, minMonthlyInstalls, realMonthlyInstalls                         sql.NullInt64
		appAgeDays, maxAndroidAPI, minAndroidAPI                                         sql.NullInt64
		free, hasIAP, containsAds, adSupported, sale, available                          sql.NullInt64
	)
	err := row.Scan(
		&record.Identity.Platform, &record.Identity.AppID, &record.Identity.Country,
		&record.Identity.Lang, &record.CapturedAt, &title, &developer, &category,
		&rating, &ratingsCount, &reviewsCount, &installs, &minInstalls, &realInstalls,
		&price, &free, &hasIAP, &version, &updated, &released, &androidVersion,
		&contentRating, &description, &summary, &changelog, &iconURL, &screenshotsJSON,
		&containsAds, &adSupported, &dailyInstalls, &minDailyInstalls, &realDailyInstalls,
		&monthlyInstalls, &minMonthlyInstalls, &realMonthlyInstalls, &appAgeDays,
		&genreID, &developerID, &currency, &sale, &originalPrice, &developerEmail,
		&developerWebsite, &developerAddress, &developerPhone, &publisherCountry,
		&privacyPolicy, &headerImage, &video, &contentRatingDescription, &available,
		&maxAndroidAPI, &minAndroidAPI, &appBundle, &histogramJSON, &categoriesJSON,
		&permissionsJSON, &dataSafetyJSON, &rawJSON,
	)
	if err != nil {
		return SnapshotRecord{}, normalizeSQLErr(err)
	}
	record.Title = title.String
	if rating.Valid {
		record.Rating = &rating.Float64
	}
	if ratingsCount.Valid {
		record.RatingsCount = &ratingsCount.Int64
	}
	if reviewsCount.Valid {
		record.ReviewsCount = &reviewsCount.Int64
	}
	record.Installs = installs.String
	if minInstalls.Valid {
		record.MinInstalls = &minInstalls.Int64
	}
	if realInstalls.Valid {
		record.RealInstalls = &realInstalls.Int64
	}
	record.Version = version.String
	record.Raw = dto.AppDetail{
		AppSummary: dto.AppSummary{
			Platform:     record.Identity.Platform,
			AppID:        record.Identity.AppID,
			Title:        record.Title,
			Developer:    developer.String,
			DeveloperID:  developerID.String,
			Category:     category.String,
			Summary:      summary.String,
			Rating:       record.Rating,
			RatingsCount: record.RatingsCount,
			ReviewsCount: record.ReviewsCount,
			Installs:     record.Installs,
			MinInstalls:  record.MinInstalls,
			Price:        price.String,
			Currency:     currency.String,
			Free:         nullableIntBool(free),
			HasIAP:       nullableIntBool(hasIAP),
			IconURL:      iconURL.String,
		},
		Version:                  record.Version,
		Updated:                  updated.String,
		Released:                 released.String,
		AndroidVersion:           androidVersion.String,
		ContentRating:            contentRating.String,
		Description:              description.String,
		Changelog:                changelog.String,
		Screenshots:              parseStringSliceColumn(screenshotsJSON.String),
		RealInstalls:             record.RealInstalls,
		Histogram:                parseInt64SliceColumn(histogramJSON.String),
		ContainsAds:              nullableIntBool(containsAds),
		AdSupported:              nullableIntBool(adSupported),
		DailyInstalls:            nullableInt64FromSQL(dailyInstalls),
		MinDailyInstalls:         nullableInt64FromSQL(minDailyInstalls),
		RealDailyInstalls:        nullableInt64FromSQL(realDailyInstalls),
		MonthlyInstalls:          nullableInt64FromSQL(monthlyInstalls),
		MinMonthlyInstalls:       nullableInt64FromSQL(minMonthlyInstalls),
		RealMonthlyInstalls:      nullableInt64FromSQL(realMonthlyInstalls),
		AppAgeDays:               nullableInt64FromSQL(appAgeDays),
		GenreID:                  genreID.String,
		Categories:               parseStringSliceColumn(categoriesJSON.String),
		Sale:                     nullableIntBool(sale),
		OriginalPrice:            nullableFloat64FromSQL(originalPrice),
		DeveloperEmail:           developerEmail.String,
		DeveloperWebsite:         developerWebsite.String,
		DeveloperAddress:         developerAddress.String,
		DeveloperPhone:           developerPhone.String,
		PublisherCountry:         publisherCountry.String,
		PrivacyPolicy:            privacyPolicy.String,
		HeaderImage:              headerImage.String,
		Video:                    video.String,
		ContentRatingDescription: contentRatingDescription.String,
		Available:                nullableIntBool(available),
		MaxAndroidAPI:            nullableInt64FromSQL(maxAndroidAPI),
		MinAndroidAPI:            nullableInt64FromSQL(minAndroidAPI),
		AppBundle:                appBundle.String,
		Permissions:              parseMapColumn(permissionsJSON.String),
		DataSafety:               parseAnySliceColumn(dataSafetyJSON.String),
	}
	if rawJSON.String != "" {
		var raw map[string]any
		if err := json.Unmarshal([]byte(rawJSON.String), &raw); err == nil {
			record.Raw.Raw = raw
		}
	}
	return record, nil
}

func nullableInt64FromSQL(value sql.NullInt64) *int64 {
	if !value.Valid {
		return nil
	}
	return &value.Int64
}

func nullableFloat64FromSQL(value sql.NullFloat64) *float64 {
	if !value.Valid {
		return nil
	}
	return &value.Float64
}

func nullableIntBool(value sql.NullInt64) *bool {
	if !value.Valid {
		return nil
	}
	parsed := value.Int64 != 0
	return &parsed
}

func parseStringSliceColumn(raw string) []string {
	if strings.TrimSpace(raw) == "" || strings.TrimSpace(raw) == "{}" {
		return nil
	}
	var values []string
	if err := json.Unmarshal([]byte(raw), &values); err == nil {
		return values
	}
	var anyValues []any
	if err := json.Unmarshal([]byte(raw), &anyValues); err != nil {
		return nil
	}
	result := make([]string, 0, len(anyValues))
	for _, item := range anyValues {
		if text, ok := item.(string); ok && strings.TrimSpace(text) != "" {
			result = append(result, text)
		}
	}
	return result
}

func parseInt64SliceColumn(raw string) []int64 {
	if strings.TrimSpace(raw) == "" || strings.TrimSpace(raw) == "{}" {
		return nil
	}
	var values []int64
	if err := json.Unmarshal([]byte(raw), &values); err == nil {
		return values
	}
	var anyValues []any
	if err := json.Unmarshal([]byte(raw), &anyValues); err != nil {
		return nil
	}
	result := make([]int64, 0, len(anyValues))
	for _, item := range anyValues {
		switch value := item.(type) {
		case float64:
			result = append(result, int64(value))
		case int64:
			result = append(result, value)
		}
	}
	return result
}

func parseMapColumn(raw string) map[string]any {
	if strings.TrimSpace(raw) == "" || strings.TrimSpace(raw) == "{}" {
		return nil
	}
	var values map[string]any
	if err := json.Unmarshal([]byte(raw), &values); err != nil {
		return nil
	}
	return values
}

func parseAnySliceColumn(raw string) []any {
	if strings.TrimSpace(raw) == "" || strings.TrimSpace(raw) == "{}" {
		return nil
	}
	var values []any
	if err := json.Unmarshal([]byte(raw), &values); err != nil {
		return nil
	}
	return values
}

func scanCachedApp(row rowScanner) (dto.AppSummary, error) {
	var item dto.AppSummary
	var title, developer, developerID, category, summary, installs, price, currency sql.NullString
	var iconURL, storeURL, country, lang, updatedAt, capturedAt sql.NullString
	var rating sql.NullFloat64
	var ratingsCount, reviewsCount, minInstalls, free, hasIAP sql.NullInt64
	err := row.Scan(
		&item.Platform, &item.AppID, &title, &developer, &developerID, &category,
		&summary, &rating, &ratingsCount, &reviewsCount, &installs, &minInstalls,
		&price, &currency, &free, &hasIAP, &iconURL, &storeURL, &country, &lang,
		&updatedAt, &capturedAt,
	)
	if err != nil {
		return dto.AppSummary{}, normalizeSQLErr(err)
	}
	item.Title = title.String
	item.Developer = developer.String
	item.DeveloperID = developerID.String
	item.Category = category.String
	item.Summary = summary.String
	item.Rating = nullableFloat64FromSQL(rating)
	item.RatingsCount = nullableInt64FromSQL(ratingsCount)
	item.ReviewsCount = nullableInt64FromSQL(reviewsCount)
	item.Installs = installs.String
	item.MinInstalls = nullableInt64FromSQL(minInstalls)
	item.Price = price.String
	item.Currency = currency.String
	item.Free = nullableIntBool(free)
	item.HasIAP = nullableIntBool(hasIAP)
	item.IconURL = iconURL.String
	item.StoreURL = storeURL.String
	item.Raw = map[string]any{
		"country":    country.String,
		"lang":       lang.String,
		"updated_at": updatedAt.String,
	}
	if capturedAt.Valid && capturedAt.String != "" {
		item.Raw["captured_at"] = capturedAt.String
	}
	return item, nil
}

func scanChartItem(row rowScanner) (dto.ChartItem, error) {
	var item dto.ChartItem
	var category, title, developer, installs, iconURL, rawJSON sql.NullString
	var rating sql.NullFloat64
	err := row.Scan(
		&item.Platform, &item.ChartType, &category, &item.Country, &item.Lang, &item.Rank,
		&item.AppID, &title, &developer, &rating, &installs, &iconURL, &rawJSON,
	)
	if err != nil {
		return dto.ChartItem{}, normalizeSQLErr(err)
	}
	item.Category = category.String
	item.Title = title.String
	item.Developer = developer.String
	if rating.Valid {
		item.Rating = &rating.Float64
	}
	item.Installs = installs.String
	item.IconURL = iconURL.String
	if rawJSON.String != "" {
		_ = json.Unmarshal([]byte(rawJSON.String), &item.Raw)
	}
	return item, nil
}

func scanKeywordCoverage(row rowScanner) (dto.KeywordCoverageResponse, error) {
	var result dto.KeywordCoverageResponse
	var canonical, candidatesJSON, coveredJSON sql.NullString
	var deep int
	err := row.Scan(
		&result.Platform, &result.AppID, &canonical, &result.Country, &result.Lang, &deep,
		&candidatesJSON, &result.CandidateCount, &coveredJSON, &result.CheckedLimit,
		&result.CapturedAt,
	)
	if err != nil {
		return dto.KeywordCoverageResponse{}, normalizeSQLErr(err)
	}
	result.CanonicalAppID = canonical.String
	result.Deep = deep != 0
	if candidatesJSON.String != "" {
		_ = json.Unmarshal([]byte(candidatesJSON.String), &result.Candidates)
	}
	if coveredJSON.String != "" {
		_ = json.Unmarshal([]byte(coveredJSON.String), &result.Covered)
	}
	return result, nil
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

func existingKeywordCorpus(ctx context.Context, tx *sql.Tx, platform, country, lang string, keywords []string) (map[string]bool, error) {
	existing := map[string]bool{}
	if len(keywords) == 0 {
		return existing, nil
	}
	args := []any{platform, country, lang}
	for _, keyword := range keywords {
		args = append(args, keyword)
	}
	rows, err := tx.QueryContext(ctx, keywordCorpusSelectExistingSQL(len(keywords)), args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var keyword string
		if err := rows.Scan(&keyword); err != nil {
			return nil, err
		}
		existing[keyword] = true
	}
	return existing, rows.Err()
}

func keywordCorpusSelectExistingSQL(keywordCount int) string {
	return `
	SELECT keyword
	FROM store_intel_keyword_corpus
	WHERE platform = ? AND country = ? AND lang = ? AND keyword IN (` + placeholders(keywordCount) + `)`
}

func keywordCorpusUpsertSQL() string {
	return `
	INSERT INTO store_intel_keyword_corpus (
	  platform, country, lang, keyword, source, confirmed, hit_count, first_seen_at, last_seen_at
	) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
	ON DUPLICATE KEY UPDATE
	  hit_count = hit_count + 1,
	  last_seen_at = VALUES(last_seen_at),
	  confirmed = GREATEST(confirmed, VALUES(confirmed))`
}

func scanKeywordCorpus(row rowScanner) (KeywordCorpusItem, error) {
	var item KeywordCorpusItem
	var source sql.NullString
	var confirmed int
	err := row.Scan(
		&item.Platform, &item.Country, &item.Lang, &item.Keyword, &source,
		&confirmed, &item.HitCount, &item.FirstSeenAt, &item.LastSeenAt,
	)
	if err != nil {
		return KeywordCorpusItem{}, normalizeSQLErr(err)
	}
	item.Source = source.String
	item.Confirmed = confirmed != 0
	return item, nil
}

func scanChartRank(row rowScanner) (dto.ChartRankResponse, error) {
	var item dto.ChartRankResponse
	var rank sql.NullInt64
	var found int
	var checkedLimit sql.NullInt64
	var category sql.NullString
	err := row.Scan(
		&item.Platform, &item.AppID, &item.Collection, &category, &item.Country, &item.Lang,
		&rank, &found, &checkedLimit, &item.CapturedAt,
	)
	if err != nil {
		return dto.ChartRankResponse{}, normalizeSQLErr(err)
	}
	item.Category = category.String
	if rank.Valid {
		value := int(rank.Int64)
		item.Rank = &value
	}
	item.Found = found != 0
	if checkedLimit.Valid {
		item.CheckedLimit = int(checkedLimit.Int64)
	}
	return item, nil
}

func scanKeywordRank(row rowScanner) (dto.KeywordRankSnapshot, error) {
	var item dto.KeywordRankSnapshot
	var rank sql.NullInt64
	var found int
	var checkedLimit sql.NullInt64
	err := row.Scan(
		&item.Platform, &item.Keyword, &item.AppID, &item.Country, &item.Lang,
		&rank, &found, &checkedLimit, &item.CapturedAt,
	)
	if err != nil {
		return dto.KeywordRankSnapshot{}, normalizeSQLErr(err)
	}
	if rank.Valid {
		value := int(rank.Int64)
		item.Rank = &value
	}
	item.Found = found != 0
	if checkedLimit.Valid {
		item.CheckedLimit = int(checkedLimit.Int64)
	}
	return item, nil
}

func scanReview(row rowScanner) (dto.ReviewItem, error) {
	var item dto.ReviewItem
	var reviewID, userName, content, appVersion, reviewCreatedAt, rawJSON sql.NullString
	var rating sql.NullInt64
	var helpfulCount sql.NullInt64
	err := row.Scan(
		&item.Platform, &item.AppID, &item.Country, &item.Lang, &reviewID, &userName,
		&rating, &content, &appVersion, &helpfulCount, &reviewCreatedAt, &item.CapturedAt,
		&rawJSON,
	)
	if err != nil {
		return dto.ReviewItem{}, normalizeSQLErr(err)
	}
	item.ReviewID = reviewID.String
	item.UserName = userName.String
	if rating.Valid {
		value := int(rating.Int64)
		item.Rating = &value
	}
	item.Content = content.String
	item.AppVersion = appVersion.String
	if helpfulCount.Valid {
		item.HelpfulCount = &helpfulCount.Int64
	}
	item.ReviewCreatedAt = reviewCreatedAt.String
	if rawJSON.String != "" {
		_ = json.Unmarshal([]byte(rawJSON.String), &item.Raw)
	}
	return item, nil
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

func rowsAffected(result sql.Result, err error) (int, error) {
	if err != nil {
		return 0, err
	}
	if result == nil {
		return 0, nil
	}
	count, err := result.RowsAffected()
	if err != nil {
		return 0, nil
	}
	return int(count), nil
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

func buildAppSnapshotValues(input SnapshotUpsertInput, identity dto.AppIdentity, day string) (appSnapshotValues, error) {
	detail := input.Detail
	rawJSON, err := jsonColumn(detail.Raw)
	if err != nil {
		return appSnapshotValues{}, err
	}
	screenshotsJSON, err := jsonColumn(detail.Screenshots)
	if err != nil {
		return appSnapshotValues{}, err
	}
	histogramJSON, err := jsonColumn(detail.Histogram)
	if err != nil {
		return appSnapshotValues{}, err
	}
	categoriesJSON, err := jsonColumn(detail.Categories)
	if err != nil {
		return appSnapshotValues{}, err
	}
	permissionsJSON, err := jsonColumn(detail.Permissions)
	if err != nil {
		return appSnapshotValues{}, err
	}
	dataSafetyJSON, err := jsonColumn(detail.DataSafety)
	if err != nil {
		return appSnapshotValues{}, err
	}

	args := []any{
		identity.Platform,
		identity.AppID,
		identity.Country,
		identity.Lang,
		input.CapturedAt,
		day,
		detail.Title,
		detail.Developer,
		detail.Category,
		nullableFloat(detail.Rating),
		nullableInt64(detail.RatingsCount),
		nullableInt64(detail.ReviewsCount),
		detail.Installs,
		nullableInt64(detail.MinInstalls),
		nil,
		nullableInt64(detail.RealInstalls),
		detail.Price,
		nullableBool(detail.Free),
		nullableBool(detail.HasIAP),
		detail.Version,
		detail.Updated,
		detail.Released,
		detail.AndroidVersion,
		detail.ContentRating,
		detail.Description,
		detail.Summary,
		detail.Changelog,
		detail.IconURL,
		screenshotsJSON,
		nullableBool(detail.ContainsAds),
		nullableBool(detail.AdSupported),
		nullableInt64(detail.DailyInstalls),
		nullableInt64(detail.MinDailyInstalls),
		nullableInt64(detail.RealDailyInstalls),
		nullableInt64(detail.MonthlyInstalls),
		nullableInt64(detail.MinMonthlyInstalls),
		nullableInt64(detail.RealMonthlyInstalls),
		nullableInt64(detail.AppAgeDays),
		detail.GenreID,
		detail.DeveloperID,
		detail.Currency,
		nullableBool(detail.Sale),
		nullableFloat(detail.OriginalPrice),
		detail.DeveloperEmail,
		detail.DeveloperWebsite,
		detail.DeveloperAddress,
		detail.DeveloperPhone,
		detail.PublisherCountry,
		detail.PrivacyPolicy,
		detail.HeaderImage,
		detail.Video,
		detail.ContentRatingDescription,
		nullableBool(detail.Available),
		nullableInt64(detail.MaxAndroidAPI),
		nullableInt64(detail.MinAndroidAPI),
		detail.AppBundle,
		histogramJSON,
		categoriesJSON,
		permissionsJSON,
		dataSafetyJSON,
		rawJSON,
	}
	return appSnapshotValues{
		identity:    identity,
		capturedAt:  input.CapturedAt,
		capturedDay: day,
		detail:      detail,
		args:        args,
	}, nil
}

func (v appSnapshotValues) record() SnapshotRecord {
	return SnapshotRecord{
		Identity:     v.identity,
		CapturedAt:   v.capturedAt,
		Title:        v.detail.Title,
		Rating:       v.detail.Rating,
		RatingsCount: v.detail.RatingsCount,
		ReviewsCount: v.detail.ReviewsCount,
		Installs:     v.detail.Installs,
		MinInstalls:  v.detail.MinInstalls,
		RealInstalls: v.detail.RealInstalls,
		Version:      v.detail.Version,
		Raw:          v.detail,
	}
}

func buildInsertSQL(table string, columns []string) string {
	return fmt.Sprintf(
		"INSERT INTO %s (%s) VALUES (%s)",
		table,
		columnList(columns),
		placeholders(len(columns)),
	)
}

func buildUpdateSQL(table string, columns []string, where string) string {
	return fmt.Sprintf("UPDATE %s SET %s WHERE %s", table, assignments(columns), where)
}

func (r *SQLRepo) cleanupPartitionedHistory(ctx context.Context, spec cleanupHistoryQuery) (int, error) {
	result, err := r.db.ExecContext(ctx, buildCleanupHistorySQL(spec), spec.MinKeep, spec.Cutoff)
	if err != nil {
		return 0, err
	}
	count, _ := result.RowsAffected()
	return int(count), nil
}

func buildCleanupHistorySQL(spec cleanupHistoryQuery) string {
	selectColumns := append([]string{"id", spec.TimeColumn}, spec.SelectExtra...)
	rankedAlias := spec.RankedAlias
	if rankedAlias == "" {
		rankedAlias = "ranked_history"
	}
	return fmt.Sprintf(`
DELETE FROM %s WHERE id IN (
  SELECT id FROM (
    SELECT %s,
      ROW_NUMBER() OVER (
        PARTITION BY %s ORDER BY %s DESC
      ) AS rn
    FROM %s
  ) AS %s
  WHERE rn > ? AND %s < ?%s
)`,
		quoteIdent(spec.Table),
		columnList(selectColumns),
		columnList(spec.Partitions),
		quoteIdent(spec.TimeColumn),
		quoteIdent(spec.Table),
		rankedAlias,
		quoteIdent(spec.TimeColumn),
		spec.OuterWhere,
	)
}

func quoteIdent(value string) string {
	return "`" + value + "`"
}

func columnList(columns []string) string {
	quoted := make([]string, 0, len(columns))
	for _, column := range columns {
		quoted = append(quoted, quoteIdent(column))
	}
	return strings.Join(quoted, ", ")
}

func assignments(columns []string) string {
	parts := make([]string, 0, len(columns)+1)
	for _, column := range columns {
		parts = append(parts, "`"+column+"` = ?")
	}
	parts = append(parts, "`updated_at` = ?")
	return strings.Join(parts, ", ")
}

func placeholders(count int) string {
	items := make([]string, 0, count)
	for range count {
		items = append(items, "?")
	}
	return strings.Join(items, ", ")
}

func jsonColumn(value any) (string, error) {
	if isEmptyJSONValue(value) {
		return "{}", nil
	}
	data, err := json.Marshal(value)
	if err != nil {
		return "", err
	}
	return string(data), nil
}

func isEmptyJSONValue(value any) bool {
	if value == nil {
		return true
	}
	rv := reflect.ValueOf(value)
	switch rv.Kind() {
	case reflect.Map, reflect.Slice, reflect.Array:
		return rv.Len() == 0
	default:
		return false
	}
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

func nullableInt(value *int) any {
	if value == nil {
		return nil
	}
	return *value
}

func nullableString(value string) any {
	if strings.TrimSpace(value) == "" {
		return nil
	}
	return value
}

func nullableBool(value *bool) any {
	if value == nil {
		return nil
	}
	return boolInt(*value)
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
