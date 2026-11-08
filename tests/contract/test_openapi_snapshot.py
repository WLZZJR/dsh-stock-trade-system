"""P1-26: an API change must update the committed OpenAPI snapshot in the same change."""

from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient

from api.deps import require_session
from api.main import create_app
from api.openapi import SNAPSHOT_PATH, generated_document, render
from domain.auth import Identity

IDENTITY = Identity(
    session_id=uuid.uuid4(),
    user_id=uuid.uuid4(),
    email="owner@example.com",
    workspace_id=uuid.uuid4(),
    role="owner",
)


def test_the_committed_snapshot_matches_the_generated_openapi_document() -> None:
    assert SNAPSHOT_PATH.exists(), "snapshot missing: run `make openapi` and commit the file"
    committed = SNAPSHOT_PATH.read_text(encoding="utf-8")
    assert committed == render(generated_document()), (
        "The API contract changed. If that is intended, run `make openapi` and commit "
        f"{SNAPSHOT_PATH.name} together with the code change."
    )


def test_the_snapshot_is_canonical_so_regenerating_never_causes_noise() -> None:
    committed = SNAPSHOT_PATH.read_text(encoding="utf-8")
    assert render(json.loads(committed)) == committed
    assert committed.endswith("\n")


def test_the_snapshot_describes_the_current_api() -> None:
    document = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert document["openapi"].startswith("3.")
    assert "/api/v1/auth/login" in document["paths"]
    assert "/api/v1/instruments/resolve" in document["paths"]
    assert "/health/ready" in document["paths"]


def test_generation_is_deterministic() -> None:
    assert render(generated_document()) == render(generated_document())


def test_the_public_schema_and_docs_pages_are_gone() -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)
    for path in ("/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect"):
        assert client.get(path).status_code == 404, path


def test_the_schema_endpoint_needs_a_session() -> None:
    response = TestClient(create_app(), raise_server_exceptions=False).get("/api/v1/openapi.json")
    assert response.status_code == 401


def test_the_schema_endpoint_serves_the_same_document() -> None:
    app = create_app()
    app.dependency_overrides[require_session] = lambda: IDENTITY
    response = TestClient(app).get("/api/v1/openapi.json")
    assert response.status_code == 200
    assert response.json() == generated_document()


def _operations() -> list[tuple[str, str, dict[str, object]]]:
    document = generated_document()
    return [
        (method.upper(), path, operation)
        for path, item in document["paths"].items()
        for method, operation in item.items()
    ]


def test_no_operation_documents_fastapis_default_validation_error() -> None:
    """Our real 422 body is problem+json; the default schema would misdescribe the contract."""
    assert "HTTPValidationError" not in json.dumps(generated_document())


def test_every_documented_error_response_is_problem_json() -> None:
    for method, path, operation in _operations():
        responses: dict[str, dict[str, object]] = operation["responses"]  # type: ignore[assignment]
        for status, response in responses.items():
            if int(status) >= 400:
                content = response.get("content", {})
                assert set(content) == {"application/problem+json"}, f"{method} {path} {status}"  # type: ignore[arg-type]


def test_every_protected_operation_documents_401_and_login_documents_its_failures() -> None:
    for method, path, operation in _operations():
        if not path.startswith("/api/v1/") or (method, path) == ("POST", "/api/v1/auth/login"):
            continue
        assert "401" in operation["responses"], f"{method} {path} does not document 401"  # type: ignore[operator]
    login = {m: o for m, p, o in _operations() if p == "/api/v1/auth/login"}["POST"]
    assert {"401", "422", "429"} <= set(login["responses"])  # type: ignore[arg-type]


def test_ready_documents_503_and_resolve_documents_422_and_503() -> None:
    operations = {(m, p): o for m, p, o in _operations()}
    assert "503" in operations[("GET", "/health/ready")]["responses"]  # type: ignore[operator]
    resolve = operations[("GET", "/api/v1/instruments/resolve")]["responses"]
    assert {"401", "422", "503"} <= set(resolve)  # type: ignore[arg-type]
    detail = operations[("GET", "/api/v1/instruments/{listing_id}")]["responses"]
    assert {"401", "404", "422", "503"} <= set(detail)  # type: ignore[arg-type]
