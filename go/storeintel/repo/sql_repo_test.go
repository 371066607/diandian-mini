package repo

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"
	"testing"

	"github.com/catch-radar/storeintel/dto"
)

func TestBuildAppSnapshotValuesMirrorsDetailFields(t *testing.T) {
	rating := 4.7
	ratingsCount := int64(1200)
	reviewsCount := int64(340)
	minInstalls := int64(100000)
	realInstalls := int64(128900)
	free := true
	hasIAP := false
	containsAds := true
	available := false
	originalPrice := 1.99

	identity := normalizeIdentity(dto.AppIdentity{
		AppID:   "com.demo",
		Country: "US",
		Lang:    "EN",
	})
	values, err := buildAppSnapshotValues(SnapshotUpsertInput{
		Detail: dto.AppDetail{
			AppSummary: dto.AppSummary{
				AppID:        "com.demo",
				Title:        "Demo",
				Developer:    "Acme",
				DeveloperID:  "dev-acme",
				Category:     "TOOLS",
				Summary:      "Short summary",
				Rating:       &rating,
				RatingsCount: &ratingsCount,
				ReviewsCount: &reviewsCount,
				Installs:     "100K+",
				MinInstalls:  &minInstalls,
				Price:        "$1.99",
				Currency:     "USD",
				Free:         &free,
				HasIAP:       &hasIAP,
				IconURL:      "https://example.test/icon.png",
				Raw:          map[string]any{"source": "fixture"},
			},
			Version:        "1.2.3",
			Description:    "Long description",
			Screenshots:    []string{"one.png", "two.png"},
			RealInstalls:   &realInstalls,
			Histogram:      []int64{1, 2, 3, 4, 5},
			ContainsAds:    &containsAds,
			DeveloperEmail: "dev@example.test",
			Categories:     []string{"Tools", "Productivity"},
			Available:      &available,
			Permissions:    map[string]any{"Camera": []string{"take pictures"}},
			DataSafety:     []any{map[string]any{"type": "location"}},
			OriginalPrice:  &originalPrice,
		},
		Country:    "us",
		Lang:       "en",
		CapturedAt: "2026-06-18T01:02:03Z",
	}, identity, "2026-06-18")
	if err != nil {
		t.Fatalf("buildAppSnapshotValues returned error: %v", err)
	}
	if len(values.args) != len(appSnapshotColumns) {
		t.Fatalf("args length = %d, want %d", len(values.args), len(appSnapshotColumns))
	}

	assertArg(t, values, "platform", dto.PlatformGooglePlay)
	assertArg(t, values, "country", "us")
	assertArg(t, values, "lang", "en")
	assertArg(t, values, "developer", "Acme")
	assertArg(t, values, "ratings_count", ratingsCount)
	assertArg(t, values, "free", 1)
	assertArg(t, values, "has_iap", 0)
	assertArg(t, values, "contains_ads", 1)
	assertArg(t, values, "available", 0)
	assertArg(t, values, "original_price", originalPrice)
	assertArg(t, values, "max_installs", nil)

	assertJSONArg(t, values, "screenshots_json", []any{"one.png", "two.png"})
	assertJSONArg(t, values, "histogram_json", []any{float64(1), float64(2), float64(3), float64(4), float64(5)})
	assertJSONArg(t, values, "categories_json", []any{"Tools", "Productivity"})
	assertJSONArg(t, values, "permissions_json", map[string]any{"Camera": []any{"take pictures"}})
	assertJSONArg(t, values, "data_safety_json", []any{map[string]any{"type": "location"}})
	assertJSONArg(t, values, "raw_json", map[string]any{"source": "fixture"})
}

func TestSnapshotSQLBuildersUseSharedColumnContract(t *testing.T) {
	insertSQL := buildInsertSQL("store_intel_app_snapshots", append(append([]string{}, appSnapshotColumns...), "created_at", "updated_at"))
	if !strings.Contains(insertSQL, "`developer`") || !strings.Contains(insertSQL, "`permissions_json`") {
		t.Fatalf("insert SQL missing extended snapshot columns: %s", insertSQL)
	}
	if got, want := strings.Count(insertSQL, "?"), len(appSnapshotColumns)+2; got != want {
		t.Fatalf("insert placeholders = %d, want %d", got, want)
	}

	updateSQL := buildUpdateSQL("store_intel_app_snapshots", appSnapshotColumns, "id = ?")
	if !strings.Contains(updateSQL, "`developer` = ?") || !strings.Contains(updateSQL, "`permissions_json` = ?") {
		t.Fatalf("update SQL missing extended snapshot columns: %s", updateSQL)
	}
	if got, want := strings.Count(updateSQL, "?"), len(appSnapshotColumns)+2; got != want {
		t.Fatalf("update placeholders = %d, want %d", got, want)
	}
}

func TestScanSnapshotRestoresCachedDetailFields(t *testing.T) {
	rating := 4.7
	ratingsCount := int64(1200)
	reviewsCount := int64(340)
	minInstalls := int64(100000)
	realInstalls := int64(128900)
	free := true
	hasIAP := false
	containsAds := true
	adSupported := false
	available := true
	originalPrice := 1.99

	values, err := buildAppSnapshotValues(SnapshotUpsertInput{
		Detail: dto.AppDetail{
			AppSummary: dto.AppSummary{
				Platform:     dto.PlatformGooglePlay,
				AppID:        "com.demo",
				Title:        "Demo",
				Developer:    "Acme",
				DeveloperID:  "dev-acme",
				Category:     "TOOLS",
				Summary:      "Short summary",
				Rating:       &rating,
				RatingsCount: &ratingsCount,
				ReviewsCount: &reviewsCount,
				Installs:     "100K+",
				MinInstalls:  &minInstalls,
				Price:        "$1.99",
				Currency:     "USD",
				Free:         &free,
				HasIAP:       &hasIAP,
				IconURL:      "https://example.test/icon.png",
				Raw:          map[string]any{"source": "fixture"},
			},
			Version:           "1.2.3",
			Updated:           "Jun 18, 2026",
			Released:          "Jan 1, 2026",
			AndroidVersion:    "Android",
			ContentRating:     "Everyone",
			Description:       "Long description",
			Changelog:         "Bug fixes",
			Screenshots:       []string{"one.png", "two.png"},
			RealInstalls:      &realInstalls,
			Histogram:         []int64{1, 2, 3, 4, 5},
			ContainsAds:       &containsAds,
			AdSupported:       &adSupported,
			DeveloperEmail:    "dev@example.test",
			DeveloperWebsite:  "https://example.test",
			PrivacyPolicy:     "https://example.test/privacy",
			Categories:        []string{"Tools", "Productivity"},
			Available:         &available,
			Permissions:       map[string]any{"Camera": []string{"take pictures"}},
			DataSafety:        []any{map[string]any{"type": "location"}},
			OriginalPrice:     &originalPrice,
			PublisherCountry:  "US",
			DeveloperPhone:    "+1 555 0100",
			DeveloperAddress:  "1 Main St",
			HeaderImage:       "https://example.test/header.png",
			Video:             "https://example.test/video.mp4",
			AppBundle:         "aab",
			GenreID:           "tools",
			MaxAndroidAPI:     &reviewsCount,
			MinAndroidAPI:     &minInstalls,
			AppAgeDays:        &realInstalls,
			DailyInstalls:     &reviewsCount,
			MinDailyInstalls:  &reviewsCount,
			RealDailyInstalls: &reviewsCount,
		},
		Country:    "us",
		Lang:       "en",
		CapturedAt: "2026-06-18T01:02:03Z",
	}, normalizeIdentity(dto.AppIdentity{AppID: "com.demo", Country: "us", Lang: "en"}), "2026-06-18")
	if err != nil {
		t.Fatalf("buildAppSnapshotValues returned error: %v", err)
	}

	rowValues := make([]any, 0, len(appSnapshotSelectColumns))
	for _, column := range appSnapshotSelectColumns {
		rowValues = append(rowValues, argForColumn(t, values, column))
	}
	record, err := scanSnapshot(fakeRow{values: rowValues})
	if err != nil {
		t.Fatalf("scanSnapshot returned error: %v", err)
	}
	detail := record.Raw
	if detail.Title != "Demo" || detail.Developer != "Acme" || detail.Category != "TOOLS" {
		t.Fatalf("summary fields not restored: %+v", detail.AppSummary)
	}
	if detail.Description != "Long description" || detail.Summary != "Short summary" || detail.IconURL == "" {
		t.Fatalf("detail text/media fields not restored: %+v", detail)
	}
	if detail.Free == nil || !*detail.Free || detail.HasIAP == nil || *detail.HasIAP {
		t.Fatalf("monetization flags not restored: free=%v has_iap=%v", detail.Free, detail.HasIAP)
	}
	if len(detail.Screenshots) != 2 || len(detail.Categories) != 2 || len(detail.Histogram) != 5 {
		t.Fatalf("JSON arrays not restored: screenshots=%v categories=%v histogram=%v", detail.Screenshots, detail.Categories, detail.Histogram)
	}
	if detail.Permissions["Camera"] == nil || len(detail.DataSafety) != 1 {
		t.Fatalf("JSON object/slice fields not restored: permissions=%v data_safety=%v", detail.Permissions, detail.DataSafety)
	}
	if detail.Raw["source"] != "fixture" {
		t.Fatalf("raw JSON not restored: %+v", detail.Raw)
	}
}

func TestScanCachedAppRestoresSnapshotDisplayFields(t *testing.T) {
	row, err := scanCachedApp(fakeRow{values: []any{
		dto.PlatformGooglePlay,
		"com.hotshotai",
		"Hotshot AI: Photo Generator",
		"Hotshot Studio",
		"dev-hotshot",
		"PHOTOGRAPHY",
		"Create AI meme photos.",
		4.7,
		int64(1200),
		int64(340),
		"100K+",
		int64(100000),
		"0",
		"USD",
		int64(1),
		int64(0),
		"https://example.test/icon.png",
		"https://play.google.com/store/apps/details?id=com.hotshotai",
		"us",
		"en",
		"2026-06-18T01:00:00Z",
		"2026-06-18T01:02:03Z",
	}})
	if err != nil {
		t.Fatalf("scanCachedApp returned error: %v", err)
	}
	if row.Title != "Hotshot AI: Photo Generator" || row.Developer != "Hotshot Studio" ||
		row.DeveloperID != "dev-hotshot" || row.Category != "PHOTOGRAPHY" ||
		row.Summary != "Create AI meme photos." {
		t.Fatalf("display fields not restored: %+v", row)
	}
	if row.Rating == nil || *row.Rating != 4.7 || row.RatingsCount == nil ||
		*row.RatingsCount != 1200 || row.ReviewsCount == nil || *row.ReviewsCount != 340 ||
		row.Installs != "100K+" || row.MinInstalls == nil || *row.MinInstalls != 100000 {
		t.Fatalf("metric fields not restored: %+v", row)
	}
	if row.Price != "0" || row.Currency != "USD" || row.Free == nil || !*row.Free ||
		row.HasIAP == nil || *row.HasIAP || row.IconURL == "" || row.StoreURL == "" {
		t.Fatalf("commercial/media fields not restored: %+v", row)
	}
	if row.Raw["captured_at"] != "2026-06-18T01:02:03Z" {
		t.Fatalf("raw captured_at not preserved: %+v", row.Raw)
	}
}

func TestCleanupHistorySQLUsesWindowedRetentionContract(t *testing.T) {
	query := buildCleanupHistorySQL(cleanupHistoryQuery{
		Table:       "store_intel_keyword_ranks",
		TimeColumn:  "captured_at",
		Partitions:  []string{"platform", "keyword", "app_id", "country", "lang"},
		Cutoff:      "2026-01-01T00:00:00Z",
		MinKeep:     30,
		RankedAlias: "ranked_keywords",
	})
	for _, want := range []string{
		"DELETE FROM `store_intel_keyword_ranks`",
		"ROW_NUMBER() OVER",
		"PARTITION BY `platform`, `keyword`, `app_id`, `country`, `lang` ORDER BY `captured_at` DESC",
		"WHERE rn > ? AND `captured_at` < ?",
	} {
		if !strings.Contains(query, want) {
			t.Fatalf("cleanup query missing %q:\n%s", want, query)
		}
	}

	alertQuery := buildCleanupHistorySQL(cleanupHistoryQuery{
		Table:       "store_intel_alerts",
		TimeColumn:  "created_at",
		Partitions:  []string{"app_id"},
		SelectExtra: []string{"is_read"},
		OuterWhere:  " AND is_read = 1",
		RankedAlias: "ranked_alerts",
	})
	if !strings.Contains(alertQuery, "`is_read`") || !strings.Contains(alertQuery, "AND is_read = 1") {
		t.Fatalf("alert cleanup query should preserve unread alerts:\n%s", alertQuery)
	}
}

func TestAcquireSettingSQLUsesAtomicKVContract(t *testing.T) {
	updateSQL := acquireSettingUpdateSQL()
	for _, want := range []string{
		"UPDATE store_intel_settings",
		"SET `value` = ?",
		"WHERE `key` = ?",
		"`value` IS NULL OR `value` <> ?",
	} {
		if !strings.Contains(updateSQL, want) {
			t.Fatalf("acquire update SQL missing %q:\n%s", want, updateSQL)
		}
	}

	insertSQL := acquireSettingInsertSQL()
	for _, want := range []string{
		"INSERT IGNORE INTO store_intel_settings",
		"`key`, `value`, updated_at",
	} {
		if !strings.Contains(insertSQL, want) {
			t.Fatalf("acquire insert SQL missing %q:\n%s", want, insertSQL)
		}
	}
}

func TestKeywordCorpusSQLUsesPythonCompatibleUpsertContract(t *testing.T) {
	upsertSQL := keywordCorpusUpsertSQL()
	for _, want := range []string{
		"INSERT INTO store_intel_keyword_corpus",
		"platform, country, lang, keyword, source, confirmed, hit_count, first_seen_at, last_seen_at",
		"ON DUPLICATE KEY UPDATE",
		"hit_count = hit_count + 1",
		"last_seen_at = VALUES(last_seen_at)",
		"confirmed = GREATEST(confirmed, VALUES(confirmed))",
	} {
		if !strings.Contains(upsertSQL, want) {
			t.Fatalf("keyword corpus upsert SQL missing %q:\n%s", want, upsertSQL)
		}
	}

	selectSQL := keywordCorpusSelectExistingSQL(3)
	for _, want := range []string{
		"SELECT keyword",
		"FROM store_intel_keyword_corpus",
		"platform = ? AND country = ? AND lang = ?",
		"keyword IN (?, ?, ?)",
	} {
		if !strings.Contains(selectSQL, want) {
			t.Fatalf("keyword corpus existing SQL missing %q:\n%s", want, selectSQL)
		}
	}
}

func assertArg(t *testing.T, values appSnapshotValues, column string, want any) {
	t.Helper()
	got := argForColumn(t, values, column)
	if got != want {
		t.Fatalf("%s = %#v, want %#v", column, got, want)
	}
}

func assertJSONArg(t *testing.T, values appSnapshotValues, column string, want any) {
	t.Helper()
	raw, ok := argForColumn(t, values, column).(string)
	if !ok {
		t.Fatalf("%s is not a JSON string", column)
	}
	var got any
	if err := json.Unmarshal([]byte(raw), &got); err != nil {
		t.Fatalf("%s contains invalid JSON %q: %v", column, raw, err)
	}
	if jsonString(t, got) != jsonString(t, want) {
		t.Fatalf("%s = %s, want %s", column, jsonString(t, got), jsonString(t, want))
	}
}

func argForColumn(t *testing.T, values appSnapshotValues, column string) any {
	t.Helper()
	for index, candidate := range appSnapshotColumns {
		if candidate == column {
			return values.args[index]
		}
	}
	t.Fatalf("unknown app snapshot column %q", column)
	return nil
}

func jsonString(t *testing.T, value any) string {
	t.Helper()
	data, err := json.Marshal(value)
	if err != nil {
		t.Fatalf("marshal JSON fixture: %v", err)
	}
	return string(data)
}

type fakeRow struct {
	values []any
}

func (r fakeRow) Scan(dest ...any) error {
	if len(dest) != len(r.values) {
		return fmt.Errorf("scan dest count = %d, want %d", len(dest), len(r.values))
	}
	for index, target := range dest {
		assignScanValue(target, r.values[index])
	}
	return nil
}

func assignScanValue(target any, value any) {
	switch dest := target.(type) {
	case *string:
		if value == nil {
			*dest = ""
			return
		}
		*dest = fmt.Sprint(value)
	case *sql.NullString:
		if value == nil {
			*dest = sql.NullString{}
			return
		}
		*dest = sql.NullString{String: fmt.Sprint(value), Valid: true}
	case *sql.NullFloat64:
		switch typed := value.(type) {
		case nil:
			*dest = sql.NullFloat64{}
		case float64:
			*dest = sql.NullFloat64{Float64: typed, Valid: true}
		case float32:
			*dest = sql.NullFloat64{Float64: float64(typed), Valid: true}
		case int:
			*dest = sql.NullFloat64{Float64: float64(typed), Valid: true}
		case int64:
			*dest = sql.NullFloat64{Float64: float64(typed), Valid: true}
		}
	case *sql.NullInt64:
		switch typed := value.(type) {
		case nil:
			*dest = sql.NullInt64{}
		case int:
			*dest = sql.NullInt64{Int64: int64(typed), Valid: true}
		case int64:
			*dest = sql.NullInt64{Int64: typed, Valid: true}
		}
	}
}
