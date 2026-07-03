from __future__ import annotations

from typing import Any


class ApiLogController:
    """Owns the request/response log feed shown in the desktop's API log panel.

    A plain (non-QObject) class: QmlBridge exposes the actual apiLogs
    @Property and clearApiLogs/_append_api_log_entry @Slots QML binds to, and
    is responsible for emitting apiLogsChanged — Signals must live on the
    QObject, so this class only owns the entries list and the normalization
    logic, not signal emission.
    """

    def __init__(self, limit: int = 200) -> None:
        self.entries: list[dict[str, Any]] = []
        self.limit = limit

    def append(self, entry: Any) -> bool:
        """Normalize and append a raw log entry. Returns True if it was a
        valid entry (the caller should then emit apiLogsChanged)."""
        if not isinstance(entry, dict):
            return False
        row = {
            "time": str(entry.get("time") or ""),
            "method": str(entry.get("method") or ""),
            "path": str(entry.get("path") or ""),
            "query": str(entry.get("query") or ""),
            "queryFull": str(entry.get("query_full") or entry.get("query") or ""),
            "body": str(entry.get("body") or ""),
            "bodyFull": str(entry.get("body_full") or entry.get("body") or ""),
            "response": str(entry.get("response") or ""),
            "responseFull": str(entry.get("response_full") or entry.get("response") or ""),
            "status": str(entry.get("status") or "-"),
            "code": str(entry.get("code") or "-"),
            "duration": f"{int(entry.get('duration_ms') or 0)}ms",
            "ok": bool(entry.get("ok")),
            "error": str(entry.get("error") or ""),
            "stream": bool(entry.get("stream")),
        }
        self.entries = (self.entries + [row])[-self.limit :]
        return True

    def clear(self) -> None:
        self.entries = []
