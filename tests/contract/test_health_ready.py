"""P1-25: /health/ready is 200 only when every dependency is up, and never explains a failure."""

from __future__ import annotations

from collections.abc import Callable, Mapping

import pytest
from fastapi.testclient import TestClient

from api.deps import get_readiness_probes
from api.main import create_app

Probes = Mapping[str, Callable[[], bool]]
SECRET = "hunter2-10.0.0.5"  # noqa: S105 - fixture value, not a credential


def client_with(probes: Probes) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_readiness_probes] = lambda: probes
    return TestClient(app, raise_server_exceptions=False)


def test_all_dependencies_up_is_200() -> None:
    client = client_with(
        {"postgres": lambda: True, "redis": lambda: True, "migrations": lambda: True}
    )
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"postgres": "ok", "redis": "ok", "migrations": "ok"},
    }
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-trace-id"]


def test_it_is_public_no_session_needed() -> None:
    assert client_with({"postgres": lambda: True}).get("/health/ready").status_code == 200


@pytest.mark.parametrize("down", ["postgres", "redis", "migrations"])
def test_any_dependency_down_is_503_naming_only_which_one(down: str) -> None:
    probes = {name: (lambda: True) for name in ("postgres", "redis", "migrations")}
    probes[down] = lambda: False
    response = client_with(probes).get("/health/ready")
    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "SERVICE_UNAVAILABLE"
    assert body["trace_id"] == response.headers["x-trace-id"]
    assert body["checks"] == {n: ("fail" if n == down else "ok") for n in probes}
    assert response.headers["cache-control"] == "no-store"


def test_probe_exceptions_are_a_failed_check_and_never_leak() -> None:
    def broken() -> bool:
        raise ConnectionError(f"could not connect to {SECRET}")

    response = client_with({"postgres": broken, "redis": lambda: True}).get("/health/ready")
    assert response.status_code == 503
    assert response.json()["checks"] == {"postgres": "fail", "redis": "ok"}
    assert SECRET not in response.text
    assert "ConnectionError" not in response.text


def test_the_body_contains_nothing_but_status_names_and_the_problem_fields() -> None:
    body = client_with({"postgres": lambda: False}).get("/health/ready").json()
    assert set(body) == {"type", "title", "status", "code", "detail", "trace_id", "checks"}
    assert set(body["checks"].values()) <= {"ok", "fail"}
