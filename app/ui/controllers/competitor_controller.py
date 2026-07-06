"""Domain logic for competitor keyword reverse-lookup / gap analysis.

API-only feature (no legacy/offline fallback) -- data lives in the server's
accumulated SERP observations. Synchronous endpoints, no progress polling,
simpler than CoverageController. Sorting is done here because the backend
returns items in scan order, not ranked order.
"""

from __future__ import annotations

from typing import Any

from app.ui.formatting import fmt_dt

_RANK_SENTINEL = 10**9  # missing rank sorts last


def _rank_or_none(item: dict, key: str) -> int | None:
    value = item.get(key)
    return int(value) if isinstance(value, int) else None


class CompetitorController:
    def __init__(self, bridge) -> None:
        self.bridge = bridge

    def analyze(
        self,
        api,
        app_id: str,
        competitor_app_id: str,
        country: str,
        lang: str,
        platform: str,
    ) -> dict[str, Any]:
        app_id = (app_id or "").strip()
        competitor_app_id = (competitor_app_id or "").strip()
        if not app_id:
            raise RuntimeError("请输入目标 App ID。")
        if competitor_app_id and competitor_app_id.lower() == app_id.lower():
            raise RuntimeError("竞品 App 不能与目标 App 相同，请换一个竞品或留空只反查目标 App。")
        if api is None:
            raise RuntimeError("竞品关键词反查需要连接 StoreIntel API，请在「设置」页配置服务器地址。")
        if not competitor_app_id:
            try:
                resp = api.list_app_keyword_serp(
                    app_id, country=country, lang=lang, limit=200, platform=platform
                )
            except Exception as exc:
                raise RuntimeError(f"反查关键词覆盖失败：{exc}") from exc
            return self._single_payload(app_id, competitor_app_id, country, lang, resp)
        try:
            resp = api.analyze_keyword_gap(
                app_id,
                competitor_app_id,
                country=country,
                lang=lang,
                limit=200,
                platform=platform,
            )
        except Exception as exc:
            raise RuntimeError(f"对比竞品关键词失败：{exc}") from exc
        return self._gap_payload(app_id, competitor_app_id, country, lang, resp)

    def _single_payload(self, app_id, competitor_app_id, country, lang, resp) -> dict[str, Any]:
        items = [i for i in (getattr(resp, "items", None) or [])]
        rows = sorted(
            (
                {
                    "rank": item.get("rank"),
                    "keyword": item.get("keyword", ""),
                    "lastSeen": fmt_dt(item.get("last_seen_at")),
                    "_lastSeenRaw": item.get("last_seen_at") or "",
                }
                for item in items
            ),
            key=lambda r: (
                r["rank"] if isinstance(r["rank"], int) else _RANK_SENTINEL,
                r["_lastSeenRaw"],
            ),
        )
        for r in rows:
            r.pop("_lastSeenRaw", None)
            if r["rank"] is None:
                r["rank"] = "-"
        return {
            "mode": "single",
            "queried": True,
            "appId": app_id,
            "competitorAppId": "",
            "country": country,
            "lang": lang,
            "summary": f"共 {len(rows)} 个关键词",
            "rows": rows,
            "gapRows": [],
            "overlapRows": [],
            "exclusiveRows": [],
            "gapTotal": 0,
            "overlapTotal": 0,
            "exclusiveTotal": 0,
        }

    def _gap_payload(self, app_id, competitor_app_id, country, lang, resp) -> dict[str, Any]:
        gap_items = getattr(resp, "gap", None) or []
        overlap_items = getattr(resp, "overlap", None) or []
        exclusive_items = getattr(resp, "exclusive", None) or []

        def _gap_row(i: dict) -> dict:
            rank = _rank_or_none(i, "competitor_rank")
            return {
                "keyword": i.get("keyword", ""),
                "competitorRank": rank,
                "hot": (rank or _RANK_SENTINEL) <= 10,
            }

        gap_rows = sorted(
            (_gap_row(i) for i in gap_items),
            key=lambda r: (
                r["competitorRank"] if r["competitorRank"] is not None else _RANK_SENTINEL
            ),
        )
        for r in gap_rows:
            if r["competitorRank"] is None:
                r["competitorRank"] = "-"

        def _overlap_row(i: dict) -> dict:
            target_rank = _rank_or_none(i, "target_rank")
            competitor_rank = _rank_or_none(i, "competitor_rank")
            if target_rank is None or competitor_rank is None:
                delta_text, behind, sort_key = "-", False, -_RANK_SENTINEL
            else:
                diff = target_rank - competitor_rank
                sort_key = diff
                if diff > 0:
                    delta_text, behind = f"落后 {diff}", True
                elif diff < 0:
                    delta_text, behind = f"领先 {-diff}", False
                else:
                    delta_text, behind = "持平", False
            return {
                "keyword": i.get("keyword", ""),
                "targetRank": target_rank if target_rank is not None else "-",
                "competitorRank": competitor_rank if competitor_rank is not None else "-",
                "delta": delta_text,
                "behind": behind,
                "_sort": sort_key,
            }

        overlap_rows = sorted((_overlap_row(i) for i in overlap_items), key=lambda r: -r["_sort"])
        for r in overlap_rows:
            r.pop("_sort", None)

        exclusive_rows = sorted(
            (
                {"keyword": i.get("keyword", ""), "targetRank": _rank_or_none(i, "target_rank")}
                for i in exclusive_items
            ),
            key=lambda r: r["targetRank"] if r["targetRank"] is not None else _RANK_SENTINEL,
        )
        for r in exclusive_rows:
            if r["targetRank"] is None:
                r["targetRank"] = "-"

        gap_total = getattr(resp, "gap_total", None) or len(gap_rows)
        overlap_total = getattr(resp, "overlap_total", None) or len(overlap_rows)
        exclusive_total = getattr(resp, "exclusive_total", None) or len(exclusive_rows)

        return {
            "mode": "gap",
            "queried": True,
            "appId": app_id,
            "competitorAppId": competitor_app_id,
            "country": country,
            "lang": lang,
            "summary": f"机会 {gap_total} · 重合 {overlap_total} · 独有 {exclusive_total}",
            "rows": [],
            "gapRows": gap_rows,
            "overlapRows": overlap_rows,
            "exclusiveRows": exclusive_rows,
            "gapTotal": gap_total,
            "overlapTotal": overlap_total,
            "exclusiveTotal": exclusive_total,
        }
