"""Trace ids, secret redaction and structured JSON logging (P1-20).

Framework-free on purpose: the HTTP layer in ``apps/api`` plugs into it. Nothing that may hold
a credential (headers, passwords, tokens, cookies, URLs with embedded passwords) is ever written
to a log in clear text; redaction is applied to field values, messages and tracebacks.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

REDACTED = "[REDACTED]"

trace_id_var: ContextVar[str | None] = ContextVar("gei_trace_id", default=None)

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def new_trace_id() -> str:
    return str(uuid.uuid4())


def valid_trace_id(value: str) -> bool:
    """Only well-formed UUIDs are accepted from callers, which also blocks log injection."""
    return _UUID_RE.fullmatch(value) is not None


# --- redaction -----------------------------------------------------------------------------

_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "cookie",
    "api_key",
    "apikey",
    "credential",
    "private_key",
)


def _is_sensitive_key(key: object) -> bool:
    normalised = str(key).lower().replace("-", "_")
    return any(part in normalised for part in _SENSITIVE_KEY_PARTS)


def redact(value: Any) -> Any:
    """Return a copy of ``value`` with sensitive keys masked and strings scrubbed."""
    if isinstance(value, dict):
        return {k: REDACTED if _is_sensitive_key(k) else redact(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


_KEYS = "password|passwd|pwd|token|secret|api[_-]?key|access[_-]?key|session[_-]?id"
_HEADER_RE = re.compile(
    r"(?i)\b(proxy-authorization|authorization|set-cookie|cookie)\b(\s*[:=]\s*)[^\r\n]+"
)
_SCHEME_RE = re.compile(r"(?i)\b(bearer|basic)(\s+)[A-Za-z0-9._~+/=\-]+")
_KEYED_VALUE_RE = re.compile(
    rf"""(?ix)\b({_KEYS})(["']?\s*[=:]\s*)("[^"]*"|'[^']*'|[^\s,;&}}\]]+)"""
)
_URL_PASSWORD_RE = re.compile(r"(\b[a-zA-Z][a-zA-Z0-9+.\-]*://[^\s:/@]+:)([^\s@/]+)(@)")


def redact_text(text: str) -> str:
    """Mask credentials embedded in free text (headers, key=value pairs, URL passwords)."""
    text = _HEADER_RE.sub(rf"\1\2{REDACTED}", text)
    text = _SCHEME_RE.sub(rf"\1\2{REDACTED}", text)
    text = _KEYED_VALUE_RE.sub(rf"\1\2{REDACTED}", text)
    return _URL_PASSWORD_RE.sub(rf"\1{REDACTED}\3", text)


# --- logging -------------------------------------------------------------------------------

_RESERVED = frozenset({"ts", "level", "logger", "message", "trace_id", "exc"})


class JsonFormatter(logging.Formatter):
    """One JSON object per line. Structured data goes in ``extra={"fields": {...}}``."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {}
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            entry.update({k: v for k, v in redact(fields).items() if k not in _RESERVED})
        entry.update(
            {
                "ts": datetime.fromtimestamp(record.created, UTC)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"),
                "level": record.levelname,
                "logger": record.name,
                "message": redact_text(record.getMessage()),
                "trace_id": trace_id_var.get(),
            }
        )
        if record.exc_info:
            entry["exc"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(entry, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Route the ``gei`` logger tree to stderr as redacted JSON; safe to call repeatedly."""
    logger = logging.getLogger("gei")
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False
