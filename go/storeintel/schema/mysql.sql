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
  KEY `store_intel_tracked_apps_enabled_updated` (`enabled`, `updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `store_intel_app_snapshots` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `platform` VARCHAR(32) NOT NULL DEFAULT 'google_play',
  `app_id` VARCHAR(255) NOT NULL,
  `country` VARCHAR(16) NOT NULL DEFAULT 'us',
  `lang` VARCHAR(16) NOT NULL DEFAULT 'en',
  `captured_at` VARCHAR(64) NOT NULL,
  `captured_day` VARCHAR(10) NOT NULL,
  `title` VARCHAR(512) NOT NULL DEFAULT '',
  `rating` DOUBLE NULL,
  `reviews_count` BIGINT NULL,
  `installs` VARCHAR(128) NOT NULL DEFAULT '',
  `min_installs` BIGINT NULL,
  `raw_json` JSON NOT NULL,
  `created_at` VARCHAR(64) NOT NULL,
  `updated_at` VARCHAR(64) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `store_intel_app_snapshots_identity_day` (`platform`, `app_id`, `country`, `lang`, `captured_day`),
  KEY `store_intel_app_snapshots_lookup` (`platform`, `app_id`, `country`, `lang`, `captured_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `store_intel_alerts` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `type` VARCHAR(64) NOT NULL,
  `severity` VARCHAR(32) NOT NULL,
  `app_id` VARCHAR(255) NOT NULL DEFAULT '',
  `title` VARCHAR(512) NOT NULL DEFAULT '',
  `message` TEXT NOT NULL,
  `payload_json` JSON NOT NULL,
  `is_read` TINYINT(1) NOT NULL DEFAULT 0,
  `created_at` VARCHAR(64) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `store_intel_alerts_app_created` (`app_id`, `created_at`),
  KEY `store_intel_alerts_read_created` (`is_read`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
