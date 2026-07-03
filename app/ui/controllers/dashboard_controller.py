from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.ui.formatting import (
    alert_row,
    fail_label,
    fmt_dt,
    frequency_label,
    latest_sync_time,
    next_sync_label,
    rank_text,
    short_time,
)


class DashboardController:
    """Read/aggregation logic for the dashboard, monitor tree/series charts,
    tracking list, and history views — shared between API mode and
    legacy/offline mode. Needs a reference to the bridge for the shared
    _store_intel_api helper, services, database/repositories, and the
    _history_selection state (mutated here, read by QML via bridge.history).
    QmlBridge owns the Slot surface, async dispatch (_run), state storage,
    and signal emission.
    """

    def __init__(self, bridge) -> None:
        self.bridge = bridge

    # --- monitor tree (app-centric tree of tracked apps + nested
    # keywords/charts) -----------------------------------------------------

    def monitor_tree(self) -> dict[str, Any]:
        api = self.bridge._store_intel_api()
        if api is not None:
            return self._monitor_tree_api(api)
        ts = self.bridge.services["tracking_service"]
        apps = ts.list_apps()
        keywords = ts.list_keywords()
        chart_apps = ts.list_chart_apps()
        tree = []
        for a in apps:
            tree.append(
                {
                    "title": a.title or a.app_id,
                    "appId": a.app_id,
                    "country": a.country,
                    "lang": a.lang,
                    "lastSynced": fmt_dt(a.last_synced_at),
                    "keywords": [
                        {
                            "keyword": k.keyword,
                            "country": k.country,
                            "lang": k.lang,
                            "rank": self.keyword_rank_label(k),
                        }
                        for k in keywords
                        if k.app_id == a.app_id
                    ],
                    "charts": [
                        {
                            "collection": c.collection,
                            "category": c.category or "",
                            "country": c.country,
                            "lang": c.lang,
                            "rank": self.chart_rank_label(c),
                        }
                        for c in chart_apps
                        if c.app_id == a.app_id
                    ],
                }
            )
        return {"apps": tree}

    def _monitor_tree_api(self, api) -> dict[str, Any]:
        try:
            apps = api.list_tracked_apps()
            keywords = api.list_tracked_keywords()
            chart_apps = api.list_tracked_chart_apps()
            tree = []
            for app in apps:
                app_id = getattr(app, "app_id", "")
                tree.append(
                    {
                        "title": getattr(app, "title", "") or app_id,
                        "appId": app_id,
                        "country": getattr(app, "country", "us"),
                        "lang": getattr(app, "lang", "en"),
                        "lastSynced": fmt_dt(getattr(app, "last_synced_at", "")),
                        "keywords": [
                            {
                                "keyword": getattr(keyword, "keyword", ""),
                                "country": getattr(keyword, "country", "us"),
                                "lang": getattr(keyword, "lang", "en"),
                                "rank": api.latest_keyword_rank_label(
                                    getattr(keyword, "keyword", ""),
                                    getattr(keyword, "app_id", ""),
                                    getattr(keyword, "country", "us"),
                                    getattr(keyword, "lang", "en"),
                                    getattr(keyword, "platform", "google_play") or "google_play",
                                ),
                            }
                            for keyword in keywords
                            if getattr(keyword, "app_id", "") == app_id
                        ],
                        "charts": [
                            {
                                "collection": getattr(chart, "collection", ""),
                                "category": getattr(chart, "category", "") or "",
                                "country": getattr(chart, "country", "us"),
                                "lang": getattr(chart, "lang", "en"),
                                "rank": api.latest_chart_rank_label(
                                    getattr(chart, "app_id", ""),
                                    getattr(chart, "collection", ""),
                                    getattr(chart, "category", "") or None,
                                    getattr(chart, "country", "us"),
                                    getattr(chart, "lang", "en"),
                                    getattr(chart, "platform", "google_play") or "google_play",
                                ),
                            }
                            for chart in chart_apps
                            if getattr(chart, "app_id", "") == app_id
                        ],
                    }
                )
            return {"apps": tree}
        except Exception:  # noqa: BLE001
            return {"apps": []}

    # --- monitor series (time-series for a selected monitored object) -----

    def monitor_series(
        self, kind: str, app_id: str, country: str, lang: str, key: str, days: int = 30
    ) -> dict[str, Any]:
        country = country or "us"
        lang = lang or "en"
        api = self.bridge._store_intel_api()
        if api is not None:
            return self._monitor_series_api(api, kind, app_id, country, lang, key, days)
        cutoff = (
            ""
            if days <= 0
            else (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        )

        def win(items):
            return [r for r in items if not cutoff or (r.captured_at or "") >= cutoff]

        try:
            with self.bridge.database.session() as session:
                if kind == "keyword":
                    rows = win(
                        self.bridge.keyword_rank_repository.history(
                            session, key, app_id, country, lang
                        )
                    )
                    labels = [r.captured_at[5:10] for r in rows]
                    values = [r.rank if r.rank else 0 for r in rows]
                    cur = rank_text(rows[-1].rank if rows else None)
                    return {
                        "title": key,
                        "subtitle": f"{app_id} · {country}/{lang}",
                        "charts": [
                            {
                                "name": "排名",
                                "labels": labels,
                                "values": values,
                                "current": cur,
                                "invert": True,
                            }
                        ],
                    }
                if kind == "chart":
                    coll, _, cat = key.partition("|")
                    rows = self.bridge.chart_rank_repository.history(
                        session, app_id, coll, cat or None, country, lang
                    )
                    labels = [r.captured_at[5:10] for r in rows]
                    values = [r.rank if r.rank else 0 for r in rows]
                    cur = rank_text(rows[-1].rank if rows else None)
                    return {
                        "title": coll + (f" · {cat}" if cat else ""),
                        "subtitle": app_id,
                        "charts": [
                            {
                                "name": "榜单名次",
                                "labels": labels,
                                "values": values,
                                "current": cur,
                                "invert": True,
                            }
                        ],
                    }
                rows = self.bridge.snapshot_repository.get_history(session, app_id, country, lang)
                labels = [r.captured_at[5:10] for r in rows]
                last = rows[-1] if rows else None
                return {
                    "title": (last.title if last and last.title else app_id),
                    "subtitle": f"{app_id} · {country}/{lang}",
                    "charts": [
                        {
                            "name": "评分",
                            "labels": labels,
                            "values": [
                                round(getattr(r, "rating", None), 2)
                                if getattr(r, "rating", None)
                                else 0
                                for r in rows
                            ],
                            "current": (
                                f"{getattr(last, 'rating'):.2f}"
                                if last and getattr(last, "rating", None)
                                else "-"
                            ),
                            "invert": False,
                        },
                        {
                            "name": "安装量",
                            "labels": labels,
                            "values": [
                                getattr(r, "real_installs", None)
                                or getattr(r, "min_installs", None)
                                or 0
                                for r in rows
                            ],
                            "current": (
                                str(
                                    getattr(last, "real_installs", None)
                                    or getattr(last, "min_installs", None)
                                    or 0
                                )
                                if last
                                else "-"
                            ),
                            "invert": False,
                        },
                        {
                            "name": "评论数",
                            "labels": labels,
                            "values": [getattr(r, "reviews_count", None) or 0 for r in rows],
                            "current": (
                                str(getattr(last, "reviews_count", None) or 0) if last else "-"
                            ),
                            "invert": False,
                        },
                    ],
                }
        except Exception:  # noqa: BLE001
            return {"title": "", "subtitle": "", "charts": []}

    def _monitor_series_api(
        self,
        api,
        kind: str,
        app_id: str,
        country: str,
        lang: str,
        key: str,
        days: int = 30,
    ) -> dict[str, Any]:
        platform = self.bridge._tracking_controller.platform_of(
            api, kind, app_id, country, lang, key
        )
        cutoff = (
            ""
            if days <= 0
            else (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        )

        def win(items):
            return [
                item
                for item in items
                if not cutoff or (getattr(item, "captured_at", "") or "") >= cutoff
            ]

        try:
            if kind == "keyword":
                rows = win(
                    api.list_keyword_rank_history(key, app_id, country, lang, platform=platform)
                )
                labels = [short_time(getattr(row, "captured_at", "")) for row in rows]
                values = [
                    getattr(row, "rank", None) or getattr(row, "checked_limit", None) or 0
                    for row in rows
                ]
                current_rank = getattr(rows[-1], "rank", None) if rows else None
                return {
                    "title": key,
                    "subtitle": f"{app_id} · {country}/{lang}",
                    "charts": [
                        {
                            "name": "排名",
                            "labels": labels,
                            "values": values,
                            "current": rank_text(current_rank),
                            "invert": True,
                        }
                    ],
                }
            if kind == "chart":
                collection, _, category = key.partition("|")
                rows = win(
                    api.list_chart_rank_history(
                        app_id,
                        collection,
                        category or None,
                        country,
                        lang,
                        platform=platform,
                    )
                )
                labels = [short_time(getattr(row, "captured_at", "")) for row in rows]
                values = [
                    getattr(row, "rank", None) or getattr(row, "checked_limit", None) or 0
                    for row in rows
                ]
                current_rank = getattr(rows[-1], "rank", None) if rows else None
                return {
                    "title": collection + (f" · {category}" if category else ""),
                    "subtitle": app_id,
                    "charts": [
                        {
                            "name": "榜单名次",
                            "labels": labels,
                            "values": values,
                            "current": rank_text(current_rank),
                            "invert": True,
                        }
                    ],
                }
            rows = win(api.list_app_snapshots(app_id, country, lang, limit=0, platform=platform))
            labels = [short_time(getattr(row, "captured_at", "")) for row in rows]
            last = rows[-1] if rows else None
            return {
                "title": (getattr(last, "title", "") if last else "") or app_id,
                "subtitle": f"{app_id} · {country}/{lang}",
                "charts": [
                    {
                        "name": "评分",
                        "labels": labels,
                        "values": [
                            round(getattr(row, "rating", None), 2)
                            if getattr(row, "rating", None)
                            else 0
                            for row in rows
                        ],
                        "current": (
                            f"{getattr(last, 'rating'):.2f}"
                            if last is not None and getattr(last, "rating", None)
                            else "-"
                        ),
                        "invert": False,
                    },
                    {
                        "name": "安装量",
                        "labels": labels,
                        "values": [
                            getattr(row, "real_installs", None)
                            or getattr(row, "min_installs", None)
                            or 0
                            for row in rows
                        ],
                        "current": (
                            str(
                                getattr(last, "real_installs", None)
                                or getattr(last, "min_installs", None)
                                or 0
                            )
                            if last is not None
                            else "-"
                        ),
                        "invert": False,
                    },
                    {
                        "name": "评论数",
                        "labels": labels,
                        "values": [getattr(row, "reviews_count", None) or 0 for row in rows],
                        "current": (
                            str(getattr(last, "reviews_count", None) or 0)
                            if last is not None
                            else "-"
                        ),
                        "invert": False,
                    },
                ],
            }
        except Exception:  # noqa: BLE001
            return {"title": "", "subtitle": "", "charts": []}

    # --- dashboard summary --------------------------------------------------

    def collect_dashboard(self) -> dict[str, Any]:
        api = self.bridge._store_intel_api()
        if api is not None:
            return self._collect_dashboard_api(api)
        tracking_service = self.bridge.services["tracking_service"]
        alert_service = self.bridge.services["alert_service"]
        tracked_apps = tracking_service.list_apps()
        tracked_keywords = tracking_service.list_keywords()
        chart_apps = tracking_service.list_chart_apps()
        with self.bridge.database.session() as session:
            snapshots_count = self.bridge.snapshot_repository.count(session)
            recent_snapshots = list(
                reversed(self.bridge.snapshot_repository.list_recent(session, limit=8))
            )
            latest_kw = self.bridge.keyword_rank_repository.list_recent(session, limit=1)
            keyword_history = []
            keyword_name = ""
            if latest_kw:
                top = latest_kw[0]
                keyword_name = top.keyword
                keyword_history = self.bridge.keyword_rank_repository.history(
                    session, top.keyword, top.app_id, top.country, top.lang
                )
        unread = alert_service.unread_count()
        alerts = alert_service.recent_alerts(limit=6)
        latest_sync = latest_sync_time(tracked_apps, tracked_keywords, chart_apps)
        health = tracking_service.monitor_overview()
        return {
            "stats": [
                {
                    "label": "监控 App",
                    "value": len(tracked_apps),
                    "meta": f"启用 {sum(1 for x in tracked_apps if x.enabled)}",
                },
                {"label": "关键词监控", "value": len(tracked_keywords), "meta": "本地排名历史"},
                {"label": "榜单监控", "value": len(chart_apps), "meta": "Google Play 榜单"},
                {"label": "历史快照", "value": snapshots_count, "meta": "SQLite 本地数据"},
                {"label": "未读提醒", "value": unread, "meta": "评分 / 版本 / 排名变化"},
            ],
            "latestSync": short_time(latest_sync) if latest_sync else "-",
            "alerts": [alert_row(alert) for alert in alerts],
            "health": [self.health_row(item) for item in health],
            "ratingLabels": [short_time(item.captured_at) for item in recent_snapshots],
            "ratingValues": [
                getattr(item, "rating", None) or getattr(item, "latest_rating", None) or 0
                for item in recent_snapshots
            ],
            "keywordName": keyword_name,
            "keywordLabels": [short_time(item.captured_at) for item in keyword_history],
            "keywordValues": [
                getattr(item, "rank", None) or getattr(item, "checked_limit", None) or 0
                for item in keyword_history
            ],
        }

    def _collect_dashboard_api(self, api) -> dict[str, Any]:
        tracked_apps = api.list_tracked_apps()
        tracked_keywords = api.list_tracked_keywords()
        chart_apps = api.list_tracked_chart_apps()
        alerts = api.list_alerts(limit=6)
        unread = api.unread_count()
        snapshots_count = api.count_app_snapshots()
        recent_snapshots = list(reversed(api.list_recent_app_snapshots(limit=8)))
        try:
            latest_kw = api.list_recent_keyword_ranks(limit=1)
        except Exception:
            latest_kw = []
        keyword_history = []
        keyword_name = ""
        if latest_kw:
            top = latest_kw[0]
            keyword_name = top.keyword
            try:
                keyword_history = api.list_keyword_rank_history(
                    top.keyword,
                    top.app_id,
                    top.country,
                    top.lang,
                    platform=getattr(top, "platform", "google_play") or "google_play",
                )
            except Exception:
                keyword_history = []
        latest_sync = latest_sync_time(tracked_apps, tracked_keywords, chart_apps)
        return {
            "stats": [
                {
                    "label": "监控 App",
                    "value": len(tracked_apps),
                    "meta": f"启用 {sum(1 for x in tracked_apps if x.enabled)}",
                },
                {"label": "关键词监控", "value": len(tracked_keywords), "meta": "后端排名历史"},
                {"label": "榜单监控", "value": len(chart_apps), "meta": "Go 后端榜单"},
                {"label": "历史快照", "value": snapshots_count, "meta": "Go 后端数据"},
                {"label": "未读提醒", "value": unread, "meta": "评分 / 版本 / 排名变化"},
            ],
            "latestSync": short_time(latest_sync) if latest_sync else "-",
            "alerts": [alert_row(alert) for alert in alerts],
            "health": [self.health_row_from_tracked(item) for item in tracked_apps if item.enabled],
            "ratingLabels": [short_time(item.captured_at) for item in recent_snapshots],
            "ratingValues": [
                getattr(item, "rating", None) or getattr(item, "latest_rating", None) or 0
                for item in recent_snapshots
            ],
            "keywordName": keyword_name,
            "keywordLabels": [short_time(item.captured_at) for item in keyword_history],
            "keywordValues": [
                getattr(item, "rank", None) or getattr(item, "checked_limit", None) or 0
                for item in keyword_history
            ],
        }

    # --- tracking list --------------------------------------------------

    def collect_tracking(self) -> dict[str, Any]:
        api = self.bridge._store_intel_api()
        if api is not None:
            return self._collect_tracking_api(api)
        tracking_service = self.bridge.services["tracking_service"]
        settings = self.bridge.services["settings_service"].get_all()
        apps = tracking_service.list_apps()
        keywords = tracking_service.list_keywords()
        chart_apps = tracking_service.list_chart_apps()
        return {
            "defaults": {
                "country": settings["default_country"],
                "lang": settings["default_lang"],
                "limit": settings["default_limit"],
            },
            "apps": [
                {
                    "title": item.title or item.app_id,
                    "appId": item.app_id,
                    "country": item.country,
                    "lang": item.lang,
                    "frequency": frequency_label(item.frequency),
                    "lastSynced": fmt_dt(item.last_synced_at),
                    "nextSync": next_sync_label(item.last_synced_at, item.frequency),
                    "failures": fail_label(item),
                    "tag": item.tag or "-",
                    "enabled": "启用" if item.enabled else "禁用",
                }
                for item in apps
            ],
            "keywords": [
                {
                    "keyword": item.keyword,
                    "appId": item.app_id,
                    "rank": self.keyword_rank_label(item),
                    "country": item.country,
                    "frequency": frequency_label(item.frequency),
                    "lastSynced": fmt_dt(item.last_synced_at),
                    "nextSync": next_sync_label(item.last_synced_at, item.frequency),
                    "failures": fail_label(item),
                    "enabled": "启用" if item.enabled else "禁用",
                }
                for item in keywords
            ],
            "charts": [
                {
                    "appId": item.app_id,
                    "collection": item.collection,
                    "category": item.category or "-",
                    "country": item.country,
                    "rank": self.chart_rank_label(item),
                    "lastSynced": fmt_dt(item.last_synced_at),
                    "failures": fail_label(item),
                    "enabled": "启用" if item.enabled else "禁用",
                }
                for item in chart_apps
            ],
        }

    def _collect_tracking_api(self, api) -> dict[str, Any]:
        settings = api.get_settings()
        apps = api.list_tracked_apps()
        keywords = api.list_tracked_keywords()
        chart_apps = api.list_tracked_chart_apps()
        return {
            "defaults": {
                "country": settings["default_country"],
                "lang": settings["default_lang"],
                "limit": settings["default_limit"],
            },
            "apps": [
                {
                    "title": getattr(item, "title", "") or getattr(item, "app_id", ""),
                    "appId": getattr(item, "app_id", ""),
                    "country": getattr(item, "country", "us"),
                    "lang": getattr(item, "lang", "en"),
                    "frequency": frequency_label(getattr(item, "frequency", "daily")),
                    "lastSynced": fmt_dt(getattr(item, "last_synced_at", "")),
                    "nextSync": next_sync_label(
                        getattr(item, "last_synced_at", ""),
                        getattr(item, "frequency", "daily"),
                    ),
                    "failures": fail_label(item),
                    "tag": getattr(item, "tag", "") or "-",
                    "enabled": "启用" if getattr(item, "enabled", True) else "禁用",
                }
                for item in apps
            ],
            "keywords": [
                {
                    "keyword": getattr(item, "keyword", ""),
                    "appId": getattr(item, "app_id", ""),
                    "rank": api.latest_keyword_rank_label(
                        getattr(item, "keyword", ""),
                        getattr(item, "app_id", ""),
                        getattr(item, "country", "us"),
                        getattr(item, "lang", "en"),
                    ),
                    "country": getattr(item, "country", "us"),
                    "frequency": frequency_label(getattr(item, "frequency", "daily")),
                    "lastSynced": fmt_dt(getattr(item, "last_synced_at", "")),
                    "nextSync": next_sync_label(
                        getattr(item, "last_synced_at", ""),
                        getattr(item, "frequency", "daily"),
                    ),
                    "failures": fail_label(item),
                    "enabled": "启用" if getattr(item, "enabled", True) else "禁用",
                }
                for item in keywords
            ],
            "charts": [
                {
                    "appId": getattr(item, "app_id", ""),
                    "collection": getattr(item, "collection", ""),
                    "category": getattr(item, "category", "") or "-",
                    "country": getattr(item, "country", "us"),
                    "rank": api.latest_chart_rank_label(
                        getattr(item, "app_id", ""),
                        getattr(item, "collection", ""),
                        getattr(item, "category", None),
                        getattr(item, "country", "us"),
                        getattr(item, "lang", "en"),
                    ),
                    "lastSynced": fmt_dt(getattr(item, "last_synced_at", "")),
                    "failures": fail_label(item),
                    "enabled": "启用" if getattr(item, "enabled", True) else "禁用",
                }
                for item in chart_apps
            ],
        }

    # --- history ----------------------------------------------------------

    def collect_history(self) -> dict[str, Any]:
        api = self.bridge._store_intel_api()
        if api is not None:
            return self._collect_history_api(api)
        tracking_service = self.bridge.services["tracking_service"]
        apps = tracking_service.list_apps()
        selected = apps[0] if apps else None
        if self.bridge._history_selection is not None:
            selected = next(
                (
                    item
                    for item in apps
                    if (
                        item.app_id,
                        item.country,
                        item.lang,
                    )
                    == self.bridge._history_selection
                ),
                selected,
            )
        snapshots = []
        keyword_rows = []
        if selected is not None:
            self.bridge._history_selection = (selected.app_id, selected.country, selected.lang)
            with self.bridge.database.session() as session:
                snapshots = self.bridge.snapshot_repository.get_history(
                    session, selected.app_id, selected.country, selected.lang
                )[-80:]
                recent_kw = self.bridge.keyword_rank_repository.list_recent(session, limit=80)
                keyword_rows = [
                    row
                    for row in recent_kw
                    if row.app_id == selected.app_id
                    and row.country == selected.country
                    and row.lang == selected.lang
                ]
        return {
            "apps": [
                {
                    "label": f"{item.title or item.app_id} · {item.country}/{item.lang}",
                    "appId": item.app_id,
                    "country": item.country,
                    "lang": item.lang,
                }
                for item in apps
            ],
            "selected": selected.app_id if selected is not None else "",
            "snapshots": [
                {
                    "time": short_time(item.captured_at),
                    "title": item.title or item.app_id,
                    "rating": getattr(item, "rating", None) or "-",
                    "ratings": getattr(item, "ratings_count", None) or "-",
                    "reviews": getattr(item, "reviews_count", None) or "-",
                    "installs": getattr(item, "installs", "") or "-",
                    "version": getattr(item, "version", "") or "-",
                }
                for item in snapshots
            ],
            "keywords": [
                {
                    "time": short_time(getattr(item, "captured_at", "")),
                    "keyword": getattr(item, "keyword", ""),
                    "rank": getattr(item, "rank", None)
                    if getattr(item, "rank", None) is not None
                    else "未命中",
                    "limit": getattr(item, "checked_limit", 0),
                }
                for item in keyword_rows
            ],
        }

    def _collect_history_api(self, api) -> dict[str, Any]:
        apps = api.list_tracked_apps()
        selected = apps[0] if apps else None
        if self.bridge._history_selection is not None:
            selected = next(
                (
                    item
                    for item in apps
                    if (item.app_id, item.country, item.lang) == self.bridge._history_selection
                ),
                selected,
            )
        if selected is not None:
            self.bridge._history_selection = (selected.app_id, selected.country, selected.lang)
        selected_platform = (
            getattr(selected, "platform", "google_play") or "google_play"
            if selected is not None
            else "google_play"
        )
        snapshots = (
            api.list_app_snapshots(
                selected.app_id,
                selected.country,
                selected.lang,
                limit=80,
                platform=selected_platform,
            )
            if selected is not None
            else []
        )
        keyword_rows = []
        if selected is not None:
            try:
                keyword_rows = api.list_recent_keyword_ranks(
                    app_id=selected.app_id,
                    country=selected.country,
                    lang=selected.lang,
                    limit=80,
                    platform=selected_platform,
                )
            except Exception:
                keyword_rows = []
        return {
            "apps": [
                {
                    "label": (
                        f"{getattr(item, 'title', '') or getattr(item, 'app_id', '')}"
                        f" · {getattr(item, 'country', 'us')}/{getattr(item, 'lang', 'en')}"
                    ),
                    "appId": getattr(item, "app_id", ""),
                    "country": getattr(item, "country", "us"),
                    "lang": getattr(item, "lang", "en"),
                }
                for item in apps
            ],
            "selected": selected.app_id if selected is not None else "",
            "snapshots": [
                {
                    "time": short_time(getattr(item, "captured_at", "")),
                    "title": getattr(item, "title", "") or getattr(item, "app_id", ""),
                    "rating": getattr(item, "rating", None) or "-",
                    "ratings": getattr(item, "ratings_count", None) or "-",
                    "reviews": getattr(item, "reviews_count", None) or "-",
                    "installs": getattr(item, "installs", "") or "-",
                    "version": getattr(item, "version", "") or "-",
                }
                for item in snapshots
            ],
            "keywords": [
                {
                    "time": short_time(getattr(item, "captured_at", "")),
                    "keyword": getattr(item, "keyword", ""),
                    "rank": getattr(item, "rank", None)
                    if getattr(item, "rank", None) is not None
                    else "未命中",
                    "limit": getattr(item, "checked_limit", 0),
                }
                for item in keyword_rows
            ],
        }

    # --- rank labels / health rows ----------------------------------------

    def keyword_rank_label(self, item) -> str:
        # Rank snapshots are platform-scoped — read via the service matching the ROW's
        # platform (the tracked list mixes both stores), not the UI's current toggle.
        key = "keyword_service_app_store" if item.platform == "app_store" else "keyword_service"
        keyword_service = self.bridge.services.get(key)
        if keyword_service is None:
            return "未同步"
        snapshot = keyword_service.latest_rank(item.keyword, item.app_id, item.country, item.lang)
        if snapshot is None:
            return "未同步"
        return f"#{snapshot.rank}" if snapshot.found and snapshot.rank is not None else "未命中"

    def chart_rank_label(self, item) -> str:
        chart_rank_service = self.bridge.services.get("chart_rank_service")
        if chart_rank_service is None:
            return "未同步"
        snapshot = chart_rank_service.latest_rank(
            item.app_id, item.collection, item.category, item.country, item.lang
        )
        if snapshot is None:
            return "未同步"
        return f"#{snapshot.rank}" if snapshot.found and snapshot.rank is not None else "未命中"

    @staticmethod
    def health_row(item) -> dict[str, Any]:
        color = {"normal": "#16A34A", "failing": "#D97706", "escalated": "#DC2626"}.get(
            item.fail_status, "#16A34A"
        )
        return {
            "title": item.title or item.app_id,
            "appId": item.app_id,
            "rating": f"{item.latest_rating:.2f}" if item.latest_rating is not None else "-",
            "installs": item.latest_installs or "-",
            "unread": item.unread_count,
            "failures": item.consecutive_failures,
            "statusColor": color,
            "lastSynced": fmt_dt(item.last_synced_at),
        }

    @staticmethod
    def health_row_from_tracked(item) -> dict[str, Any]:
        failures = getattr(item, "consecutive_failures", 0) or 0
        color = "#16A34A" if failures == 0 else "#D97706"
        app_id = getattr(item, "app_id", "")
        return {
            "title": getattr(item, "title", "") or app_id,
            "appId": app_id,
            "rating": "-",
            "installs": "-",
            "unread": 0,
            "failures": failures,
            "statusColor": color,
            "lastSynced": fmt_dt(getattr(item, "last_synced_at", "")),
        }
