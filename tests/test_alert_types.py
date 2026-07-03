# All tests formerly in this module exercised AlertService.create_snapshot_alerts
# (the per-field diff engine that turned two snapshots into installs_milestone /
# ads_changed / price_changed / developer_contact_changed / negative_review_surge /
# positive_ratio_drop alerts) together with SnapshotRepository.save_detail, used
# only to seed the "previous" snapshot for that diff.
#
# Both were deleted in the legacy-scraper retirement: create_snapshot_alerts (plus
# its NewAlert dataclass, _parse_histogram, _format_percent, _ads_flag, and
# INSTALL_MILESTONES) no longer exists on AlertService, and save_detail no longer
# exists on SnapshotRepository. Every test here depended on both, with no
# remaining coverage of a still-functional read path independent of them, so the
# module has no tests left to keep, repurpose, or fix — it is intentionally empty.
