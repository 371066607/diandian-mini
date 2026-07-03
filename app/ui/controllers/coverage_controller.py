from __future__ import annotations

import time
from typing import Any

from app.utils.normalize import safe_int


def has_coverage_cache_data(result) -> bool:
    if result is None:
        return False
    return bool(
        getattr(result, "captured_at", "")
        or getattr(result, "candidate_count", 0)
        or getattr(result, "candidates", [])
        or getattr(result, "covered", [])
    )


class CoverageController:
    """Domain logic for a keyword-coverage scan, shared between API mode
    (cache-or-refresh-job, with a polling loop while the backend analyzes)
    and legacy/offline mode (a local, optionally proxy-pooled scan via
    keyword_coverage_service). Needs a reference to the bridge for the
    shared _store_intel_api helper and the coverageProgress signal (the
    only domain with inline scan-progress reporting, not just a busy
    spinner). QmlBridge owns the Slot surface, async dispatch (_run),
    coverage state (_coverage/_coverage_pools), and signal emission for
    the final result.
    """

    def __init__(self, bridge) -> None:
        self.bridge = bridge

    def concurrency(self) -> int:
        """Max parallel workers for a proxy-backed coverage scan (clamped 1..16)."""
        raw = self.bridge.services["settings_service"].get("coverage_concurrency", "6")
        return max(1, min(16, safe_int(raw, 6)))

    def analyze(
        self,
        api,
        app_id: str,
        country: str,
        lang: str,
        deep: bool,
        platform: str,
        cached_pool: tuple[Any, Any] | None,
        proxy_pool=None,
        max_workers: int = 1,
    ) -> dict[str, Any]:
        candidates, canonical = cached_pool or (None, None)
        if api is not None:
            try:
                result = api.cached_coverage(app_id, country=country, lang=lang, deep=deep, platform=platform)
            except Exception:
                result = None
            if not has_coverage_cache_data(result):
                result = self.refresh_api_cache(
                    api, app_id=app_id, country=country, lang=lang, deep=deep, platform=platform
                )
            if not has_coverage_cache_data(result):
                raise RuntimeError("服务器没有返回可用的覆盖词数据。")
            return result
        return self.bridge.services["keyword_coverage_service"].analyze_coverage(
            platform,
            app_id,
            country=country,
            lang=lang,
            limit=50,
            deep=deep,
            candidates=candidates,
            canonical_app_id=canonical,
            proxy_pool=proxy_pool,
            max_workers=max_workers,
            progress=lambda msg, frac: self.bridge.coverageProgress.emit(msg, float(frac)),
        )

    def refresh_api_cache(
        self, api, *, app_id: str, country: str, lang: str, deep: bool, platform: str = "google_play"
    ):
        self.bridge.coverageProgress.emit("暂无缓存，已开始后台分析...", 0.05)
        job = api.request_refresh(
            "coverage", app_id=app_id, country=country, lang=lang, limit=50, deep=deep, platform=platform
        )
        job_id = getattr(job, "job_id", "") or getattr(job, "id", "")
        if job_id:
            self.bridge.coverageProgress.emit("后台分析中，请稍候...", 0.25)
            job = api.wait_refresh_job(job_id, timeout=300.0 if deep else 180.0, interval=2.0)
        if str(getattr(job, "status", "")).lower() == "failed":
            message = getattr(job, "error", "") or getattr(job, "message", "")
            raise RuntimeError(message or "服务器覆盖词分析任务失败。")

        self.bridge.coverageProgress.emit("后台分析完成，正在读取缓存...", 0.9)
        deadline = time.monotonic() + 30.0
        result = None
        while time.monotonic() <= deadline:
            try:
                result = api.cached_coverage(app_id, country=country, lang=lang, deep=deep, platform=platform)
            except Exception:
                result = None
            if has_coverage_cache_data(result):
                return result
            time.sleep(1.0)
        return result
