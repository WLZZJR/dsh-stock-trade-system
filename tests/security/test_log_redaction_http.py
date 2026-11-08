"""P1-20: logs never contain Authorization, passwords or tokens, even when requests fail."""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from application.observability import JsonFormatter

BEARER = "Bearer SECRET-BEARER-TOKEN-777"
COOKIE_VALUE = "SECRET-SESSION-COOKIE-888"
QUERY_TOKEN = "SECRET-QUERY-TOKEN-999"  # noqa: S105 - fixture value, not a credential
BODY_PASSWORD = "SECRET-BODY-PASSWORD-111"  # noqa: S105 - fixture value, not a credential
EXC_PASSWORD = "SECRET-EXC-PASSWORD-222"  # noqa: S105 - fixture value, not a credential
ALL_SECRETS = (BEARER, COOKIE_VALUE, QUERY_TOKEN, BODY_PASSWORD, EXC_PASSWORD)


@pytest.fixture
def log_output() -> Iterator[io.StringIO]:
    """Capture everything the app logs, formatted by the production formatter."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("gei")
    previous = (logger.handlers, logger.level, logger.propagate)
    logger.handlers = [handler]
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    yield stream
    logger.handlers, logger.level, logger.propagate = previous


def _client() -> TestClient:
    app = create_app()

    def boom() -> None:
        raise RuntimeError(f"upstream rejected password={EXC_PASSWORD}")

    app.add_api_route("/_t/boom", boom, methods=["GET"])
    return TestClient(app, raise_server_exceptions=False)


def test_request_log_has_no_headers_query_or_body(log_output: io.StringIO) -> None:
    response = _client().post(
        f"/health/live?token={QUERY_TOKEN}",
        headers={"Authorization": BEARER, "Cookie": f"session={COOKIE_VALUE}"},
        json={"password": BODY_PASSWORD},
    )
    assert response.status_code == 405  # POST is not allowed; the request is still logged
    output = log_output.getvalue()
    assert output, "requests must be logged"
    for secret in ALL_SECRETS:
        assert secret not in output


def test_request_log_records_method_path_status_and_trace_id(log_output: io.StringIO) -> None:
    response = _client().get("/health/live")
    entries = [json.loads(line) for line in log_output.getvalue().splitlines()]
    request_entries = [e for e in entries if e["message"] == "request"]
    assert len(request_entries) == 1
    entry = request_entries[0]
    assert entry["method"] == "GET"
    assert entry["path"] == "/health/live"
    assert entry["status"] == 200
    assert entry["trace_id"] == response.headers["x-trace-id"]
    assert isinstance(entry["duration_ms"], int | float)


def test_unhandled_exception_is_logged_with_traceback_but_redacted(
    log_output: io.StringIO,
) -> None:
    response = _client().get("/_t/boom", headers={"Authorization": BEARER})
    assert response.status_code == 500
    output = log_output.getvalue()
    for secret in ALL_SECRETS:
        assert secret not in output
    entries = [json.loads(line) for line in output.splitlines()]
    errors = [e for e in entries if e["level"] == "ERROR"]
    assert errors, "unhandled exceptions must be logged"
    assert "RuntimeError" in errors[0]["exc"]
    assert errors[0]["trace_id"] == response.headers["x-trace-id"]
    request_entry = next(e for e in entries if e["message"] == "request")
    assert request_entry["status"] == 500


def test_query_string_values_are_not_logged_on_any_route(log_output: io.StringIO) -> None:
    _client().get(f"/no/such/route?token={QUERY_TOKEN}&x={BODY_PASSWORD}")
    for secret in (QUERY_TOKEN, BODY_PASSWORD):
        assert secret not in log_output.getvalue()
