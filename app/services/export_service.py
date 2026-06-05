from __future__ import annotations

import csv

from app.db.repositories import AlertRepository, SnapshotRepository
from app.ui.alert_labels import alert_severity_label, alert_type_label

# Snapshot export columns: (model attribute -> Chinese header). Order is fixed so the
# CSV is stable for the user. Large text columns (raw_json/description/summary/changelog/
# screenshots_json/categories_json/permissions_json/data_safety_json) are deliberately
# excluded — they bloat the file and aren't useful in a spreadsheet.
_SNAPSHOT_COLUMNS: list[tuple[str, str]] = [
    ("captured_at", "采集时间"),
    ("title", "应用"),
    ("rating", "评分"),
    ("ratings_count", "评分数"),
    ("reviews_count", "评论数"),
    ("installs", "安装量"),
    ("real_installs", "真实安装"),
    ("version", "版本"),
    ("price", "价格"),
    ("currency", "货币"),
    ("contains_ads", "含广告"),
    ("content_rating", "内容分级"),
    ("updated", "更新时间"),
    ("released", "发布时间"),
]

# Alert export columns: (logical key -> Chinese header). type/severity are mapped to
# Chinese labels; the rest are read straight off the model.
_ALERT_COLUMNS: list[tuple[str, str]] = [
    ("created_at", "时间"),
    ("type", "类型"),
    ("severity", "级别"),
    ("message", "内容"),
]


def _cell(value) -> str:
    """Stringify a column value for CSV. None -> empty string; everything else
    (int/float/bool — bool prints as 1/0) becomes its plain string form."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


class ExportService:
    """Exports a tracked app's snapshot time-series and alerts to CSV.

    Files are written with a UTF-8 BOM (``utf-8-sig``) so Excel renders Chinese
    correctly, and ``newline=""`` per the csv module's contract. IO errors are not
    swallowed — they propagate so the UI's run_task error branch surfaces them.
    """

    def __init__(self, database):
        self.database = database
        self.snapshots = SnapshotRepository()
        self.alerts = AlertRepository()

    def export_app_snapshots(
        self,
        app_id: str,
        country: str,
        lang: str,
        dest_path: str,
        start: str | None = None,
        end: str | None = None,
    ) -> int:
        """Export a tracked app's snapshot time-series to CSV.

        ``start`` / ``end`` (ISO ``captured_at`` strings, either optional) slice the
        history to ``start <= captured_at <= end``. With both omitted (the default)
        the behaviour is identical to before — the full history is written.
        """
        with self.database.session() as session:
            rows = self.snapshots.get_history(session, app_id, country=country, lang=lang)
            if start is not None or end is not None:
                rows = [
                    snap
                    for snap in rows
                    if (start is None or (snap.captured_at or "") >= start)
                    and (end is None or (snap.captured_at or "") <= end)
                ]
            with open(dest_path, "w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow([header for _, header in _SNAPSHOT_COLUMNS])
                for snapshot in rows:
                    writer.writerow(
                        [_cell(getattr(snapshot, attr, None)) for attr, _ in _SNAPSHOT_COLUMNS]
                    )
            return len(rows)

    def export_app_alerts(self, app_id: str, dest_path: str) -> int:
        with self.database.session() as session:
            rows = self.alerts.list_filtered(session, app_id=app_id, limit=10000)
            with open(dest_path, "w", encoding="utf-8-sig", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow([header for _, header in _ALERT_COLUMNS])
                for alert in rows:
                    writer.writerow(
                        [
                            _cell(alert.created_at),
                            alert_type_label(alert.type),
                            alert_severity_label(alert.severity),
                            _cell(alert.message),
                        ]
                    )
            return len(rows)
