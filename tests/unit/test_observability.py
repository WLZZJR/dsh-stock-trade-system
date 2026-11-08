"""P1-20: redaction and structured JSON logging (no framework needed)."""

from __future__ import annotations

import io
import json
import logging

import pytest

from application.observability import (
    REDACTED,
    JsonFormatter,
    new_trace_id,
    redact,
    redact_text,
    trace_id_var,
    valid_trace_id,
)


def test_redact_masks_sensitive_keys_at_any_depth_case_insensitively() -> None:
    data = {
        "Authorization": "Bearer abc",
        "nested": {"Password": "p", "keep": "visible", "items": [{"api-key": "k"}]},
        "Set-Cookie": "sid=1",
        "x_token": "t",
        "client_secret": "s",
    }
    out = redact(data)
    assert out["Authorization"] == REDACTED
    assert out["nested"]["Password"] == REDACTED
    assert out["nested"]["keep"] == "visible"
    assert out["nested"]["items"][0]["api-key"] == REDACTED
    assert out["Set-Cookie"] == REDACTED
    assert out["x_token"] == REDACTED
    assert out["client_secret"] == REDACTED


def test_redact_does_not_mutate_input() -> None:
    data = {"password": "p", "nested": {"token": "t"}}
    redact(data)
    assert data == {"password": "p", "nested": {"token": "t"}}


@pytest.mark.parametrize(
    ("text", "secret"),
    [
        ("Authorization: Bearer abc.def-123", "abc.def-123"),
        ("got header authorization=Basic dXNlcjpwYXNz", "dXNlcjpwYXNz"),
        ("login failed password=hunter2 for owner", "hunter2"),
        ('payload {"password": "hunter2"}', "hunter2"),
        ("retry token: s3cr3t-token, again", "s3cr3t-token"),
        ("api_key=AKIA123456 used", "AKIA123456"),
        ("Cookie: session=abc123; theme=dark", "abc123"),
        ("connect postgresql://gei:pa55w0rd@db:5432/gei failed", "pa55w0rd"),
    ],
)
def test_redact_text_removes_secret_values(text: str, secret: str) -> None:
    cleaned = redact_text(text)
    assert secret not in cleaned
    assert REDACTED in cleaned


def test_redact_text_keeps_innocent_text() -> None:
    text = "request finished status=200 path=/instruments/resolve"
    assert redact_text(text) == text


def test_redact_text_keeps_url_host_and_user() -> None:
    cleaned = redact_text("postgresql://gei:pa55w0rd@db:5432/gei")
    assert cleaned == f"postgresql://gei:{REDACTED}@db:5432/gei"


def test_trace_id_validation() -> None:
    assert valid_trace_id(new_trace_id())
    assert valid_trace_id("123e4567-e89b-12d3-a456-426614174000")
    assert not valid_trace_id("")
    assert not valid_trace_id("not-a-uuid")
    assert not valid_trace_id("123e4567-e89b-12d3-a456-426614174000\nINJECTED")
    assert not valid_trace_id("x" * 500)


def _logger_with_stream() -> tuple[logging.Logger, io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger(f"gei.test.{new_trace_id()}")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    return logger, stream


def test_json_formatter_emits_one_json_object_with_core_fields() -> None:
    logger, stream = _logger_with_stream()
    token = trace_id_var.set("123e4567-e89b-12d3-a456-426614174000")
    try:
        logger.info("request", extra={"fields": {"method": "GET", "status": 200}})
    finally:
        trace_id_var.reset(token)
    line = stream.getvalue().strip()
    assert "\n" not in line
    record = json.loads(line)
    assert record["message"] == "request"
    assert record["level"] == "INFO"
    assert record["trace_id"] == "123e4567-e89b-12d3-a456-426614174000"
    assert record["method"] == "GET"
    assert record["status"] == 200
    assert record["ts"].endswith("Z")


def test_json_formatter_redacts_fields_message_and_exception() -> None:
    logger, stream = _logger_with_stream()
    try:
        raise RuntimeError("db down password=hunter2")  # noqa: TRY301
    except RuntimeError:
        logger.exception(
            "failed with token=abc999",
            extra={"fields": {"headers": {"Authorization": "Bearer zzz"}, "user": "owner"}},
        )
    output = stream.getvalue()
    for secret in ("hunter2", "abc999", "zzz"):
        assert secret not in output
    record = json.loads(output.strip())
    assert record["user"] == "owner"
    assert "RuntimeError" in record["exc"]


def test_json_formatter_cannot_be_overridden_by_fields() -> None:
    logger, stream = _logger_with_stream()
    logger.info("real", extra={"fields": {"message": "spoofed", "level": "FAKE"}})
    record = json.loads(stream.getvalue().strip())
    assert record["message"] == "real"
    assert record["level"] == "INFO"
