"""Redact source payloads before they are persisted or exported."""

from __future__ import annotations

import re
import json
from typing import Any

REDACTED = "[REDACTED]"
_SENSITIVE_KEY = re.compile(
    r"(?:authorization|cookie|credential|password|secret|token|authcode|code[_-]?verifier|private[_-]?key)",
    re.IGNORECASE,
)
_CONTENT_KEYS = {"body", "message"}


def redact_payload(value: Any, *, omit_content: bool = True) -> Any:
    """Return a recursive copy safe for database retention and JSONL export."""
    if isinstance(value, dict):
        return {
            str(key): _redact_item(str(key), item, omit_content=omit_content)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_payload(item, omit_content=omit_content) for item in value]
    if isinstance(value, tuple):
        return [redact_payload(item, omit_content=omit_content) for item in value]
    return value


def _redact_item(key: str, value: Any, *, omit_content: bool) -> Any:
    if _SENSITIVE_KEY.search(key):
        return REDACTED
    if omit_content and key.lower() in _CONTENT_KEYS:
        return "[OMITTED]"
    if key == "CloudTrailEvent" and isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return value
        if isinstance(parsed, dict):
            return redact_payload(parsed, omit_content=omit_content)
    return redact_payload(value, omit_content=omit_content)
