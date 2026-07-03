from __future__ import annotations

import re
from typing import Any


def split_monitor_chart_key(key: str) -> tuple[str, str]:
    parts = (key or "").split("|", 1)
    collection = parts[0].strip() or "top_free"
    category = parts[1].strip() if len(parts) > 1 else "APPLICATION"
    return collection, category or "APPLICATION"


def is_valid_app_id(app_id: str, platform: str = "google_play") -> bool:
    if not app_id or " " in app_id:
        return False
    if platform == "app_store":
        return app_id.isdigit()
    return bool(re.fullmatch(r"[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+", app_id))


def bulk_app_ids(raw_text: str) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in (raw_text or "").splitlines():
        app_id = raw.strip()
        if not app_id or app_id in seen:
            continue
        seen.add(app_id)
        cleaned.append(app_id)
    return cleaned


class TrackingController:
    """Domain logic for tracked-app/keyword/chart-app monitor CRUD (add,
    toggle, remove, sync-one, set-frequency, set-tag, bulk-import), shared
    between API mode and legacy/offline mode. Needs a reference to the
    bridge for the shared _store_intel_api helper and services. QmlBridge
    owns the Slot surface, async dispatch (_run), input validation/error
    messaging (_monitor_target stays on the bridge since it emits
    errorMessage), tracking/dashboard state, and signal emission.
    """

    def __init__(self, bridge) -> None:
        self.bridge = bridge

    # --- monitor row lookup (needed because the QML list round-trips
    # kind/app_id/country/lang/key, not platform — mutations must resolve
    # the owning platform, not silently default to Google Play) -----------

    def find_item(self, api, kind: str, app_id: str, country: str, lang: str, key: str):
        if kind == "app":
            return next(
                (
                    item
                    for item in api.list_tracked_apps()
                    if getattr(item, "app_id", "") == app_id
                    and getattr(item, "country", "us") == country
                    and getattr(item, "lang", "en") == lang
                ),
                None,
            )
        if kind == "keyword":
            return next(
                (
                    item
                    for item in api.list_tracked_keywords()
                    if getattr(item, "keyword", "") == key
                    and getattr(item, "app_id", "") == app_id
                    and getattr(item, "country", "us") == country
                    and getattr(item, "lang", "en") == lang
                ),
                None,
            )
        collection, category = split_monitor_chart_key(key)
        return next(
            (
                item
                for item in api.list_tracked_chart_apps()
                if getattr(item, "app_id", "") == app_id
                and getattr(item, "collection", "") == collection
                and (getattr(item, "category", "") or "APPLICATION") == category
                and getattr(item, "country", "us") == country
                and getattr(item, "lang", "en") == lang
            ),
            None,
        )

    def platform_of(self, api, kind: str, app_id: str, country: str, lang: str, key: str) -> str:
        current = self.find_item(api, kind, app_id, country, lang, key)
        return getattr(current, "platform", "google_play") if current else "google_play"

    def toggle_via_api(self, api, kind: str, app_id: str, country: str, lang: str, key: str) -> bool:
        current = self.find_item(api, kind, app_id, country, lang, key)
        enabled = not bool(getattr(current, "enabled", False)) if current else True
        platform = getattr(current, "platform", "google_play") if current else "google_play"
        if kind == "app":
            result = api.set_tracked_app_enabled(app_id, enabled, country, lang, platform)
            return bool(getattr(result, "enabled", enabled))
        if kind == "keyword":
            result = api.set_tracked_keyword_enabled(key, app_id, enabled, country, lang, platform)
            return bool(getattr(result, "enabled", enabled))
        collection, category = split_monitor_chart_key(key)
        result = api.set_tracked_chart_app_enabled(app_id, collection, enabled, category, country, lang, platform)
        return bool(getattr(result, "enabled", enabled))

    # --- add ------------------------------------------------------------

    def add_app(self, api, app_id: str, country: str, lang: str, frequency: str, platform: str) -> Any:
        if api is not None:
            return api.add_tracked_app(app_id, country, lang, frequency, platform=platform)
        return self.bridge.services["tracking_service"].add_app(app_id, country, lang, frequency)

    def add_chart_app(
        self, api, app_id: str, collection: str, category: str, country: str, lang: str, platform: str
    ) -> Any:
        if api is not None:
            return api.add_tracked_chart_app(
                app_id, collection or "top_free", category or None, country, lang, platform=platform
            )
        return self.bridge.services["tracking_service"].add_chart_app(
            app_id, collection or "top_free", category or "APPLICATION", country, lang
        )

    def bulk_import(
        self, api, app_ids: list[str], country: str, lang: str, frequency: str, platform: str
    ) -> dict[str, Any]:
        if api is None:
            return self.bridge.services["tracking_service"].add_apps_bulk(app_ids, country, lang, frequency)
        existing_keys = {
            (getattr(item, "app_id", ""), getattr(item, "country", "us"), getattr(item, "lang", "en"))
            for item in api.list_tracked_apps(platform=platform)
        }
        added = 0
        existing = 0
        failed: list[dict[str, str]] = []
        for app_id in app_ids:
            if not is_valid_app_id(app_id, platform):
                failed.append({"app_id": app_id, "reason": "包名格式不合法"})
                continue
            try:
                already = (app_id, country, lang) in existing_keys
                api.add_tracked_app(app_id, country, lang, frequency, platform=platform)
                if already:
                    existing += 1
                else:
                    added += 1
                    existing_keys.add((app_id, country, lang))
            except Exception as exc:  # noqa: BLE001 - keep bulk import best-effort.
                failed.append({"app_id": app_id, "reason": str(exc)})
        return {"added": added, "existing": existing, "failed": failed, "total": len(app_ids)}

    # --- sync / toggle / frequency / tag / remove, given a validated
    # (kind, app_id, country, lang, key) target -------------------------

    def sync_one(self, api, target: tuple[str, str, str, str, str]) -> str:
        kind, app_id, country, lang, key = target
        if api is not None:
            platform = self.platform_of(api, kind, app_id, country, lang, key)
            if kind == "app":
                job = api.request_refresh("app", app_id=app_id, country=country, lang=lang, platform=platform)
                return f"已提交应用后台刷新（任务 {getattr(job, 'job_id', '-')}）。"
            if kind == "keyword":
                job = api.request_refresh(
                    "keyword", keyword=key, app_id=app_id, country=country, lang=lang, platform=platform
                )
                return f"已提交关键词后台刷新（任务 {getattr(job, 'job_id', '-')}）。"
            collection, category = split_monitor_chart_key(key)
            job = api.request_refresh(
                "chart", app_id=app_id, collection=collection, category=category, country=country, lang=lang, platform=platform
            )
            return f"已提交榜单后台刷新（任务 {getattr(job, 'job_id', '-')}）。"
        tracking_service = self.bridge.services["tracking_service"]
        if kind == "app":
            tracking_service.sync_app_now(app_id, country, lang)
            return "应用同步完成。"
        if kind == "keyword":
            result = tracking_service.sync_keyword_now(key, app_id, country, lang)
            rank = result.rank if getattr(result, "rank", None) is not None else "未命中"
            return f"关键词同步完成，当前排名 {rank}。"
        collection, category = split_monitor_chart_key(key)
        result = tracking_service.sync_chart_now(app_id, collection, category, country, lang)
        rank = result.rank if getattr(result, "rank", None) is not None else "未命中"
        return f"榜单同步完成，当前排名 {rank}。"

    def toggle_one(self, api, target: tuple[str, str, str, str, str]) -> tuple[str, bool]:
        kind, app_id, country, lang, key = target
        if api is not None:
            return kind, self.toggle_via_api(api, kind, app_id, country, lang, key)
        tracking_service = self.bridge.services["tracking_service"]
        if kind == "app":
            return kind, tracking_service.toggle_app(app_id, country, lang)
        if kind == "keyword":
            return kind, tracking_service.toggle_keyword(key, app_id, country, lang)
        collection, category = split_monitor_chart_key(key)
        return kind, tracking_service.toggle_chart_app(app_id, collection, category, country, lang)

    def set_frequency(self, api, target: tuple[str, str, str, str, str], frequency: str) -> str:
        kind, app_id, country, lang, key = target
        if api is not None:
            platform = self.platform_of(api, kind, app_id, country, lang, key)
            if kind == "app":
                result = api.set_tracked_app_frequency(app_id, frequency, country, lang, platform)
            else:
                result = api.set_tracked_keyword_frequency(key, app_id, frequency, country, lang, platform)
            return getattr(result, "frequency", frequency)
        tracking_service = self.bridge.services["tracking_service"]
        if kind == "app":
            return tracking_service.set_app_frequency(app_id, country, lang, frequency)
        return tracking_service.set_keyword_frequency(key, app_id, country, lang, frequency)

    def set_tag(self, api, target: tuple[str, str, str, str, str], tag: str) -> str:
        kind, app_id, country, lang, key = target
        if api is not None:
            platform = self.platform_of(api, kind, app_id, country, lang, key)
            result = api.set_tracked_app_tag(app_id, tag, country, lang, platform)
            return getattr(result, "tag", tag)
        result = self.bridge.services["tracking_service"].set_app_tag(app_id, country, lang, tag)
        return result or ""

    def remove_one(self, api, target: tuple[str, str, str, str, str]) -> str:
        kind, app_id, country, lang, key = target
        if api is not None:
            # Resolve platform before removing — the row won't exist to look up afterward.
            platform = self.platform_of(api, kind, app_id, country, lang, key)
            if kind == "app":
                api.remove_tracked_app(app_id, country, lang, platform)
                return "已删除应用监控。"
            if kind == "keyword":
                api.remove_tracked_keyword(key, app_id, country, lang, platform)
                return "已删除关键词监控。"
            collection, category = split_monitor_chart_key(key)
            api.remove_tracked_chart_app(app_id, collection, category, country, lang, platform)
            return "已删除榜单监控。"
        tracking_service = self.bridge.services["tracking_service"]
        if kind == "app":
            tracking_service.remove_app(app_id, country, lang)
            return "已删除应用监控。"
        if kind == "keyword":
            tracking_service.remove_keyword(key, app_id, country, lang)
            return "已删除关键词监控。"
        collection, category = split_monitor_chart_key(key)
        tracking_service.remove_chart_app(app_id, collection, category, country, lang)
        return "已删除榜单监控。"
