package schema_test

import (
	"os"
	"strings"
	"testing"
)

func TestMySQLSchemaCoversDesktopModels(t *testing.T) {
	data, err := os.ReadFile("mysql.sql")
	if err != nil {
		t.Fatalf("read mysql.sql: %v", err)
	}

	schema := string(data)
	requiredTokens := []string{
		"CREATE TABLE IF NOT EXISTS `store_intel_apps`",
		"UNIQUE KEY `store_intel_apps_identity`",
		"CREATE TABLE IF NOT EXISTS `store_intel_app_snapshots`",
		"`ratings_count` BIGINT NULL",
		"`screenshots_json` JSON NULL",
		"`permissions_json` JSON NULL",
		"UNIQUE KEY `store_intel_app_snapshots_identity_day`",
		"CREATE TABLE IF NOT EXISTS `store_intel_reviews`",
		"UNIQUE KEY `store_intel_reviews_identity`",
		"CREATE TABLE IF NOT EXISTS `store_intel_chart_snapshots`",
		"CREATE TABLE IF NOT EXISTS `store_intel_keyword_ranks`",
		"UNIQUE KEY `store_intel_keyword_ranks_identity_day`",
		"CREATE TABLE IF NOT EXISTS `store_intel_keyword_corpus`",
		"UNIQUE KEY `store_intel_keyword_corpus_identity`",
		"CREATE TABLE IF NOT EXISTS `store_intel_keyword_coverage`",
		"UNIQUE KEY `store_intel_keyword_coverage_identity`",
		"CREATE TABLE IF NOT EXISTS `store_intel_chart_rank_snapshots`",
		"UNIQUE KEY `store_intel_chart_rank_identity_day`",
		"CREATE TABLE IF NOT EXISTS `store_intel_tracked_apps`",
		"CREATE TABLE IF NOT EXISTS `store_intel_tracked_keywords`",
		"CREATE TABLE IF NOT EXISTS `store_intel_tracked_chart_apps`",
		"CREATE TABLE IF NOT EXISTS `store_intel_alerts`",
		"CREATE TABLE IF NOT EXISTS `store_intel_refresh_jobs`",
		"UNIQUE KEY `store_intel_refresh_jobs_job_id`",
		"KEY `store_intel_refresh_jobs_lock`",
		"CREATE TABLE IF NOT EXISTS `store_intel_settings`",
	}

	for _, token := range requiredTokens {
		if !strings.Contains(schema, token) {
			t.Errorf("mysql.sql missing %q", token)
		}
	}

	if got, want := strings.Count(schema, "CREATE TABLE IF NOT EXISTS"), 14; got != want {
		t.Fatalf("mysql.sql table count = %d, want %d", got, want)
	}
}
