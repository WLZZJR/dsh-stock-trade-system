"""P1-23: no business route can be added without a session (D1, API_CONTRACT 24.1).

The check is behavioural and uses only public FastAPI behaviour: every operation in the generated
OpenAPI schema is called without a session cookie and must answer 401, except the explicitly
listed public ones. Adding a public route must be a deliberate edit of ``PUBLIC_API_OPERATIONS``.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import API_PREFIX, create_app

PUBLIC_API_OPERATIONS = {("POST", f"{API_PREFIX}/auth/login")}
NON_API_PATHS = {"/health/live"}
ROUTES_DIR = Path(__file__).resolve().parents[2] / "apps" / "api" / "routes"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _operations() -> list[tuple[str, str]]:
    paths = create_app().openapi()["paths"]
    return [
        (method.upper(), path)
        for path, item in paths.items()
        for method in item
        if method in HTTP_METHODS
    ]


def _api_operations() -> list[tuple[str, str]]:
    return [(m, p) for m, p in _operations() if p.startswith(API_PREFIX)]


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", lambda _: str(uuid.uuid4()), path)


def test_the_api_has_operations_to_check() -> None:
    assert len(_api_operations()) >= 5  # login, logout, me, resolve, detail


def test_only_health_live_exists_outside_the_api_prefix() -> None:
    outside = {p for _, p in _operations() if not p.startswith(API_PREFIX)}
    assert outside == NON_API_PATHS


def test_no_route_hides_itself_from_the_schema_this_test_reads() -> None:
    offenders = [
        f.name for f in ROUTES_DIR.glob("*.py") if "include_in_schema=False" in f.read_text()
    ]
    assert offenders == []


@pytest.mark.parametrize(("method", "path"), _api_operations(), ids=lambda v: str(v))
def test_api_operations_are_401_without_a_session_except_the_public_ones(
    method: str, path: str
) -> None:
    # No settings and no database override: if a protected route reached the database this would
    # fail with a 5xx instead of 401.
    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.request(method, _concrete(path))
    if (method, path) in PUBLIC_API_OPERATIONS:
        assert response.status_code != 401, f"{method} {path} is public but answered 401"
        return
    assert response.status_code == 401, f"{method} {path} is reachable without a session"
    assert response.json()["code"] == "UNAUTHENTICATED"
    assert response.headers["content-type"] == "application/problem+json"
