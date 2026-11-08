"""GET /openapi.json under the API prefix: the schema is served only to a signed-in user."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter(tags=["meta"])


@router.get("/openapi.json")
def openapi_schema(request: Request) -> dict[str, Any]:
    """The generated OpenAPI document (FastAPI's public ``/docs`` and ``/openapi.json`` are off)."""
    document: dict[str, Any] = request.app.openapi()
    return document
