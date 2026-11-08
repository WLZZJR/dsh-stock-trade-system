"""P1-20: every error is problem+json with the API_CONTRACT 25.4 fields and a trace_id."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.main import create_app
from application import problems
from application.observability import new_trace_id, valid_trace_id
from application.problems import ProblemError

REQUIRED_FIELDS = {"type", "title", "status", "code", "detail", "trace_id"}
SECRET_INPUT = "SECRETVALUE-12345"  # noqa: S105 - fixture value, not a credential


def _app() -> FastAPI:
    app = create_app()

    def items(limit: int) -> dict[str, int]:
        return {"limit": limit}

    def missing() -> None:
        raise ProblemError(
            problems.MISSING_REQUIRED_FIELD,
            "Required financial facts are unavailable for the selected period.",
            missing_fields=["shares_outstanding", "net_debt"],
        )

    def boom() -> None:
        raise RuntimeError(f"internal detail {SECRET_INPUT}")

    app.add_api_route("/_t/items", items, methods=["GET"])
    app.add_api_route("/_t/missing", missing, methods=["GET"])
    app.add_api_route("/_t/boom", boom, methods=["GET"])
    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_app(), raise_server_exceptions=False)


SCENARIOS = [
    ("/no/such/route", 404, "NOT_FOUND"),
    ("/health/live", 405, "METHOD_NOT_ALLOWED"),  # request below uses POST
    ("/_t/items?limit=abc", 422, "VALIDATION_ERROR"),
    ("/_t/missing", 422, "MISSING_REQUIRED_FIELD"),
    ("/_t/boom", 500, "INTERNAL_ERROR"),
]


def _call(client: TestClient, path: str, **kwargs: Any) -> Any:
    method = "POST" if path == "/health/live" else "GET"
    return client.request(method, path, **kwargs)


def _spec(code: str) -> problems.ProblemSpec:
    return next(s for s in problems.CATALOG if s.code == code)


@pytest.mark.parametrize(("path", "status", "code"), SCENARIOS)
def test_every_error_has_the_contract_shape(
    client: TestClient, path: str, status: int, code: str
) -> None:
    response = _call(client, path)
    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body.keys() >= REQUIRED_FIELDS
    assert body["status"] == status
    assert body["code"] == code
    assert body["type"] == problems.problem_type(_spec(code))
    assert body["title"]
    assert body["detail"]
    assert valid_trace_id(body["trace_id"])


@pytest.mark.parametrize(("path", "status", "code"), SCENARIOS)
def test_trace_id_in_body_matches_response_header(
    client: TestClient, path: str, status: int, code: str
) -> None:
    response = _call(client, path)
    assert response.headers["x-trace-id"] == response.json()["trace_id"]


def test_problem_error_extensions_are_included(client: TestClient) -> None:
    body = client.get("/_t/missing").json()
    assert body["missing_fields"] == ["shares_outstanding", "net_debt"]
    assert body["detail"] == "Required financial facts are unavailable for the selected period."


def test_validation_error_lists_locations_but_never_echoes_input(client: TestClient) -> None:
    response = client.get(f"/_t/items?limit={SECRET_INPUT}")
    body = response.json()
    assert body["errors"], "validation problem must say which parameter failed"
    assert body["errors"][0]["loc"] == ["query", "limit"]
    assert SECRET_INPUT not in response.text


def test_unhandled_exception_does_not_leak_internals(client: TestClient) -> None:
    response = client.get("/_t/boom")
    assert response.status_code == 500
    assert SECRET_INPUT not in response.text
    assert "RuntimeError" not in response.text
    assert "Traceback" not in response.text


def test_successful_responses_also_carry_a_trace_id_header(client: TestClient) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert valid_trace_id(response.headers["x-trace-id"])


def test_valid_inbound_trace_id_is_honoured(client: TestClient) -> None:
    inbound = new_trace_id()
    response = client.get("/no/such/route", headers={"X-Trace-Id": inbound})
    assert response.headers["x-trace-id"] == inbound
    assert response.json()["trace_id"] == inbound


@pytest.mark.parametrize("bad", ["not-a-uuid", "x" * 300, "{{7*7}}"])
def test_invalid_inbound_trace_id_is_replaced(client: TestClient, bad: str) -> None:
    response = client.get("/no/such/route", headers={"X-Trace-Id": bad})
    trace_id = response.headers["x-trace-id"]
    assert trace_id != bad
    assert valid_trace_id(trace_id)


def test_each_request_gets_its_own_trace_id(client: TestClient) -> None:
    first = client.get("/health/live").headers["x-trace-id"]
    second = client.get("/health/live").headers["x-trace-id"]
    assert first != second
