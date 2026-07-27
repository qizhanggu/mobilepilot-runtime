"""逐事件落盘、默认脱敏的 JSONL Trace。"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import uuid


_SENSITIVE_KEYS = {
    "api_key", "apikey", "authorization", "password", "secret",
    "access_token", "refresh_token", "token",
}


class JsonlTraceWriter:
    def __init__(self, path: str | Path, *, run_id: str | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id or uuid.uuid4().hex

    def write(self, event: str, **payload: Any) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "event": event,
            **_sanitize(payload),
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _sanitize(value: Any, key: str = "") -> Any:
    lowered = key.lower()
    # Keep accounting fields (for example ``prompt_tokens``) auditable while
    # still removing actual credential fields.
    if lowered in _SENSITIVE_KEYS or lowered.endswith("_api_key"):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(child_key): _sanitize(child_value, str(child_key)) for child_key, child_value in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
