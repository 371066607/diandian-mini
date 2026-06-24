-- MySQL schema for the Go StoreIntel backend.
--
-- Table names use the store_intel_ prefix, while columns mirror the current
-- SQLite models in app/db/models.py. The captured_day columns are derived from
-- captured_at and make the existing "one row per object per calendar day"
-- upsert behavior enforceable in MySQL.

CREATE TABLE IF NOT EXISTS `store_intel_apps` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `platform` VARCHAR(32) NOT NULL DEFAULT 'google_play',
  `app_id` VARCHAR(255) NOT NULL,
  `title` VARCHAR(512) NULL,
  `developer` VARCHAR(512) NULL,
  `developer_id` VARCHAR(255) NULL,
  `category` VARCHAR(255) NULL,
  `genre` VARCHAR(255) NULL,
  `icon_url` TEXT NULL,
  `store_url` TEXT NULL,
  `country` VARCHAR(16) NOT NULL DEFAULT 'us',
  `lang` VARCHAR(16) NOT NULL DEFAULT 'en',
  `created_at` VARCHAR(64) NOT NULL,
  `updated_at` VARCHAR(64) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `store_intel_apps_identity` (`platform`, `app_id`, `country`, `lang`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `store_intel_app_snapshots` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `platform` VARCHAR(32) NOT NULL DEFAULT 'google_play',
  `app_id` VARCHAR(255) NOT NULL,
  `country` VARCHAR(16) NOT NULL DEFAULT 'us',
  `lang` VARCHAR(16) NOT NULL DEFAULT 'en',
  `captured_at` VARCHAR(64) NOT NULL,
  `captured_day` VARCHAR(10) NOT NULL,
  `title` VARCHAR(512) NULL,
  `developer` VARCHAR(512) NULL,
  `category` VARCHAR(255) NULL,
  `rating` DOUBLE NULL,
  `ratings_count` BIGINT NULL,
  `reviews_count` BIGINT NULL,
  `installs` VARCHAR(128) NULL,
  `min_installs` BIGINT NULL,
  `max_installs` BIGINT NULL,
  `real_installs` BIGINT NULL,
  `price` VARCHAR(128) NULL,
  `free` TINYINT(1) NULL,
  `has_iap` TINYINT(1) NULL,
  `version` VARCHAR(255) NULL,
  `updated` VARCHAR(255) NULL,
  `released` VARCHAR(255) NULL,
  `android_version` VARCHAR(255) NULL,
  `content_rating` VARCHAR(255) NULL,
  `description` LONGTEXT NULL,
  `summary` TEXT NULL,
  `changelog` TEXT NULL,
  `icon_url` TEXT NULL,
  `screenshots_json` JSON NULL,
  `contains_ads` TINYINT(1) NULL,
  `ad_supported` TINYINT(1) NULL,
  `daily_installs` BIGINT NULL,
  `min_daily_installs` BIGINT NULL,
  `real_daily_installs` BIGINT NULL,
  `monthly_installs` BIGINT NULL,
  `min_monthly_installs` BIGINT NULL,
  `real_monthly_installs` BIGINT NULL,
  `app_age_days` INT NULL,
  `genre_id` VARCHAR(255) NULL,
  `developer_id` VARCHAR(255) NULL,
  `currency` VARCHAR(32) NULL,
  `sale` TINYINT(1) NULL,
  `original_price` DOUBLE NULL,
  `developer_email` VARCHAR(512) NULL,
  `developer_website` TEXT NULL,
  `developer_address` TEXT NULL,
  `developer_phone` VARCHAR(128) NULL,
  `publisher_country` VARCHAR(128) NULL,
  `privacy_policy` TEXT NULL,
  `header_image` TEXT NULL,
  `video` TEXT NULL,
  `content_rating_description` TEXT NULL,
  `available` TINYINT(1) NULL,
  `max_android_api` INT NULL,
  `min_android_api` INT NULL,
  `app_bundle` VARCHAR(255) NULL,
  `histogram_json` JSON NULL,
  `categories_json` JSON NULL,
  `permissions_json` JSON NULL,
  `data_safety_json` JSON NULL,
  `raw_json` JSON NULL,
  `created_at` VARCHAR(64) NOT NULL,
  `updated_at` VARCHAR(64) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `store_intel_app_snapshots_identity_day` (`platform`, `app_id`, `country`, `lang`, `captured_day`),
  KEY `store_intel_app_snapshots_lookup` (`platform`, `app_id`, `country`, `lang`, `captured_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `store_intel_reviews` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `platform` VARCHAR(32) NOT NULL DEFAULT 'google_play',
  `app_id` VARCHAR(255) NOT NULL,
  `country` VARCHAR(16) NOT NULL DEFAULT 'us',
  `lang` VARCHAR(16) NOT NULL DEFAULT 'en',
  `review_id` VARCHAR(255) NULL,
  `user_name` VARCHAR(512) NULL,
  `rating` INT NULL,
  `content` TEXT NULL,
  `app_version` VARCHAR(255) NULL,
  `helpful_count` BIGINT NULL,
  `review_created_at` VARCHAR(64) NULL,
  `captured_at` VARCHAR(64) NOT NULL,
  `raw_json` JSON NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `store_intel_reviews_identity` (`platform`, `app_id`, `review_id`),
  KEY `store_intel_reviews_app_created` (`platform`, `app_id`, `review_created_at`),
  KEY `store_intel_reviews_app_captured` (`platform`, `app_id`, `captured_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `store_intel_chart_snapshots` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `platform` VARCHAR(32) NOT NULL DEFAULT 'google_play',
  `chart_type` VARCHAR(64) NOT NULL,
  `category` VARCHAR(128) NULL,
  `country` VARCHAR(16) NOT NULL DEFAULT 'us',
  `lang` VARCHAR(16) NOT NULL DEFAULT 'en',
  `captured_at` VARCHAR(64) NOT NULL,
  `rank` INT NOT NULL,
  `app_id` VARCHAR(255) NOT NULL,
  `title` VARCHAR(512) NULL,
  `developer` VARCHAR(512) NULL,
  `rating` DOUBLE NULL,
  `installs` VARCHAR(128) NULL,
  `icon_url` TEXT NULL,
  `raw_json` JSON NULL,
  PRIMARY KEY (`id`),
  KEY `store_intel_chart_snapshots_lookup` (`platform`, `chart_type`, `category`, `country`, `lang`, `captured_at`),
  KEY `store_intel_chart_snapshots_app` (`platform`, `app_id`, `captured_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `store_intel_keyword_ranks` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `platform` VARCHAR(32) NOT NULL DEFAULT 'google_play',
  `keyword` VARCHAR(255) NOT NULL,
  `app_id` VARCHAR(255) NOT NULL,
  `country` VARCHAR(16) NOT NULL DEFAULT 'us',
  `lang` VARCHAR(16) NOT NULL DEFAULT 'en',
  `rank` INT NULL,
  `found` TINYINT(1) NOT NULL DEFAULT 0,
  `checked_limit` INT NULL,
  `captured_at` VARCHAR(64) NOT NULL,
  `captured_day` VARCHAR(10) NOT NULL,
  `raw_json` JSON NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `store_intel_keyword_ranks_identity_day` (`platform`, `keyword`, `app_id`, `country`, `lang`, `captured_day`),
  KEY `store_intel_keyword_ranks_lookup` (`platform`, `keyword`, `app_id`, `country`, `lang`, `captured_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `store_intel_keyword_corpus` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `platform` VARCHAR(32) NOT NULL DEFAULT 'google_play',
  `country` VARCHAR(16) NOT NULL DEFAULT 'us',
  `lang` VARCHAR(16) NOT NULL DEFAULT 'en',
  `keyword` VARCHAR(255) NOT NULL,
  `source` VARCHAR(64) NULL,
  `confirmed` TINYINT(1) NOT NULL DEFAULT 0,
  `hit_count` INT NOT NULL DEFAULT 1,
  `first_seen_at` VARCHAR(64) NOT NULL,
  `last_seen_at` VARCHAR(64) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `store_intel_keyword_corpus_identity` (`platform`, `country`, `lang`, `keyword`),
  KEY `store_intel_keyword_corpus_fetch` (`platform`, `country`, `lang`, `confirmed`, `hit_count`, `last_seen_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `store_intel_keyword_coverage` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `platform` VARCHAR(32) NOT NULL DEFAULT 'google_play',
  `app_id` VARCHAR(255) NOT NULL,
  `canonical_app_id` VARCHAR(255) NULL,
  `country` VARCHAR(16) NOT NULL DEFAULT 'us',
  `lang` VARCHAR(16) NOT NULL DEFAULT 'en',
  `deep` TINYINT(1) NOT NULL DEFAULT 0,
  `candidates_json` JSON NULL,
  `candidate_count` INT NOT NULL DEFAULT 0,
  `covered_json` JSON NULL,
  `checked_limit` INT NOT NULL DEFAULT 0,
  `captured_at` VARCHAR(64) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `store_intel_keyword_coverage_identity` (`platform`, `app_id`, `country`, `lang`, `deep`),
  KEY `store_intel_keyword_coverage_lookup` (`platform`, `app_id`, `country`, `lang`, `captured_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `store_intel_chart_rank_snapshots` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `platform` VARCHAR(32) NOT NULL DEFAULT 'google_play',
  `app_id` VARCHAR(255) NOT NULL,
  `collection` VARCHAR(64) NOT NULL,
  `category` VARCHAR(128) NULL,
  `country` VARCHAR(16) NOT NULL DEFAULT 'us',
  `lang` VARCHAR(16) NOT NULL DEFAULT 'en',
  `rank` INT NULL,
  `found` TINYINT(1) NOT NULL DEFAULT 0,
  `checked_limit` INT NULL,
  `captured_at` VARCHAR(64) NOT NULL,
  `captured_day` VARCHAR(10) NOT NULL,
  `raw_json` JSON NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `store_intel_chart_rank_identity_day` (`platform`, `app_id`, `collection`, `category`, `country`, `lang`, `captured_day`),
  KEY `store_intel_chart_ranks_lookup` (`platform`, `app_id`, `collection`, `category`, `country`, `lang`, `captured_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `store_intel_tracked_apps` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `platform` VARCHAR(32) NOT NULL DEFAULT 'google_play',
  `app_id` VARCHAR(255) NOT NULL,
  `country` VARCHAR(16) NOT NULL DEFAULT 'us',
  `lang` VARCHAR(16) NOT NULL DEFAULT 'en',
  `title` VARCHAR(512) NOT NULL DEFAULT '',
  `frequency` VARCHAR(32) NOT NULL DEFAULT 'daily',
  `tag` VARCHAR(255) NOT NULL DEFAULT '',
  `enabled` TINYINT(1) NOT NULL DEFAULT 1,
  `last_synced_at` VARCHAR(64) NOT NULL DEFAULT '',
  `consecutive_failures` INT NOT NULL DEFAULT 0,
  `last_failed_at` VARCHAR(64) NOT NULL DEFAULT '',
  `created_at` VARCHAR(64) NOT NULL,
  `updated_at` VARCHAR(64) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `store_intel_tracked_apps_identity` (`platform`, `app_id`, `country`, `lang`),
  KEY `store_intel_tracked_apps_enabled` (`enabled`),
  KEY `store_intel_tracked_apps_synced` (`last_synced_at`),
  KEY `store_intel_tracked_apps_enabled_updated` (`enabled`, `updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `store_intel_tracked_keywords` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `platform` VARCHAR(32) NOT NULL DEFAULT 'google_play',
  `app_id` VARCHAR(255) NOT NULL,
  `keyword` VARCHAR(255) NOT NULL,
  `country` VARCHAR(16) NOT NULL DEFAULT 'us',
  `lang` VARCHAR(16) NOT NULL DEFAULT 'en',
  `frequency` VARCHAR(32) NOT NULL DEFAULT 'daily',
  `enabled` TINYINT(1) NOT NULL DEFAULT 1,
  `last_synced_at` VARCHAR(64) NOT NULL DEFAULT '',
  `consecutive_failures` INT NOT NULL DEFAULT 0,
  `last_failed_at` VARCHAR(64) NOT NULL DEFAULT '',
  `created_at` VARCHAR(64) NOT NULL,
  `updated_at` VARCHAR(64) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `store_intel_tracked_keywords_identity` (`platform`, `app_id`, `keyword`, `country`, `lang`),
  KEY `store_intel_tracked_keywords_enabled` (`enabled`),
  KEY `store_intel_tracked_keywords_synced` (`last_synced_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `store_intel_tracked_chart_apps` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `platform` VARCHAR(32) NOT NULL DEFAULT 'google_play',
  `app_id` VARCHAR(255) NOT NULL,
  `collection` VARCHAR(64) NOT NULL,
  `category` VARCHAR(128) NULL,
  `country` VARCHAR(16) NOT NULL DEFAULT 'us',
  `lang` VARCHAR(16) NOT NULL DEFAULT 'en',
  `frequency` VARCHAR(32) NOT NULL DEFAULT 'daily',
  `enabled` TINYINT(1) NOT NULL DEFAULT 1,
  `last_synced_at` VARCHAR(64) NOT NULL DEFAULT '',
  `consecutive_failures` INT NOT NULL DEFAULT 0,
  `last_failed_at` VARCHAR(64) NOT NULL DEFAULT '',
  `created_at` VARCHAR(64) NOT NULL,
  `updated_at` VARCHAR(64) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `store_intel_tracked_chart_apps_identity` (`platform`, `app_id`, `collection`, `category`, `country`, `lang`),
  KEY `store_intel_tracked_chart_apps_enabled` (`enabled`),
  KEY `store_intel_tracked_chart_apps_synced` (`last_synced_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `store_intel_alerts` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `type` VARCHAR(64) NOT NULL,
  `severity` VARCHAR(32) NOT NULL,
  `app_id` VARCHAR(255) NOT NULL DEFAULT '',
  `title` VARCHAR(512) NOT NULL DEFAULT '',
  `message` TEXT NOT NULL,
  `payload_json` JSON NULL,
  `is_read` TINYINT(1) NOT NULL DEFAULT 0,
  `created_at` VARCHAR(64) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `store_intel_alerts_app_created` (`app_id`, `created_at`),
  KEY `store_intel_alerts_read_created` (`is_read`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `store_intel_refresh_jobs` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `job_id` VARCHAR(128) NOT NULL,
  `kind` VARCHAR(64) NOT NULL,
  `status` VARCHAR(32) NOT NULL,
  `worker_id` VARCHAR(128) NULL,
  `locked_until` VARCHAR(64) NULL,
  `message` TEXT NULL,
  `request_json` JSON NOT NULL,
  `requested_at` VARCHAR(64) NOT NULL,
  `started_at` VARCHAR(64) NULL,
  `finished_at` VARCHAR(64) NULL,
  `updated_at` VARCHAR(64) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `store_intel_refresh_jobs_job_id` (`job_id`),
  KEY `store_intel_refresh_jobs_lock` (`status`, `locked_until`),
  KEY `store_intel_refresh_jobs_status_updated` (`status`, `updated_at`),
  KEY `store_intel_refresh_jobs_kind_requested` (`kind`, `requested_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `store_intel_settings` (
  `key` VARCHAR(255) NOT NULL,
  `value` TEXT NULL,
  `updated_at` VARCHAR(64) NOT NULL,
  PRIMARY KEY (`key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
