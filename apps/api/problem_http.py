"""HTTP side of the error contract: problem+json bodies and FastAPI exception handlers."""

from __future__ import annotations

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any, cast

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

from application import problems
from application.observability import new_trace_id, trace_id_var
from application.problems import ProblemError, ProblemSpec

MEDIA_TYPE = "application/problem+json"

_BY_STATUS: dict[int, ProblemSpec] = {
    401: problems.UNAUTHENTICATED,
    403: problems.FORBIDDEN,
    404: problems.NOT_FOUND,
    405: problems.METHOD_NOT_ALLOWED,
    429: problems.RATE_LIMITED,
    503: problems.SERVICE_UNAVAILABLE,
}


def problem_response(
    spec: ProblemSpec,
    detail: str,
    trace_id: str,
    extensions: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": problems.problem_type(spec),
        "title": spec.title,
        "status": spec.status,
        "code": spec.code,
        "detail": detail,
        "trace_id": trace_id,
    }
    if extensions:
        body.update(extensions)
    return JSONResponse(
        body, status_code=spec.status, media_type=MEDIA_TYPE, headers=dict(headers or {})
    )


def _trace_id(request: Request) -> str:
    return str(getattr(request.state, "trace_id", None) or trace_id_var.get() or new_trace_id())


async def _problem_error(request: Request, exc: Exception) -> JSONResponse:
    error = cast(ProblemError, exc)
    return problem_response(
        error.spec, error.detail, _trace_id(request), error.extensions, error.headers
    )


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    failure = cast(RequestValidationError, exc)
    # Only where and what kind of failure: submitted values may be secrets and are never echoed.
    errors = [{"loc": list(e["loc"]), "type": e["type"]} for e in failure.errors()]
    return problem_response(
        problems.VALIDATION_ERROR,
        "Request parameters failed validation.",
        _trace_id(request),
        {"errors": errors},
    )


async def _http_error(request: Request, exc: Exception) -> JSONResponse:
    error = cast(StarletteHTTPException, exc)
    spec = _BY_STATUS.get(error.status_code) or ProblemSpec(
        f"HTTP_{error.status_code}", error.status_code, HTTPStatus(error.status_code).phrase
    )
    detail = error.detail if isinstance(error.detail, str) and error.detail else spec.title
    return problem_response(spec, detail, _trace_id(request), headers=error.headers)


async def _database_unavailable(request: Request, _exc: Exception) -> JSONResponse:
    # The driver message can contain host names and credentials: never expose it.
    return problem_response(
        problems.SERVICE_UNAVAILABLE, "The database is unavailable.", _trace_id(request)
    )


def register_problem_handlers(app: FastAPI) -> None:
    app.add_exception_handler(psycopg.OperationalError, _database_unavailable)
    app.add_exception_handler(ProblemError, _problem_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)


# --- OpenAPI documentation of the error contract -------------------------------------------

_STATUS_DESCRIPTIONS = {
    401: "Authentication required",
    404: "Resource not found",
    422: "Invalid request parameters",
    429: "Too many requests",
    503: "Service unavailable",
}


class ProblemOut(BaseModel):
    """application/problem+json body (API_CONTRACT 25.4); extension members may follow."""

    model_config = ConfigDict(extra="allow", title="Problem")

    type: str
    title: str
    status: int
    code: str
    detail: str
    trace_id: str


def problem_responses(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """``responses=`` for a route: which error statuses it can answer with."""
    return {status: {"description": _STATUS_DESCRIPTIONS[status]} for status in statuses}


def install_problem_openapi(app: FastAPI) -> None:
    """Document every 4xx/5xx response as problem+json and drop FastAPI's default 422 schema."""
    default_openapi = app.openapi

    def openapi() -> dict[str, Any]:
        schema = default_openapi()
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        components["Problem"] = ProblemOut.model_json_schema()
        for name in ("HTTPValidationError", "ValidationError"):
            components.pop(name, None)
        for item in schema.get("paths", {}).values():
            for operation in item.values():
                for status, response in operation.get("responses", {}).items():
                    if int(status) >= 400:
                        response["content"] = {
                            "application/problem+json": {
                                "schema": {"$ref": "#/components/schemas/Problem"}
                            }
                        }
        return schema

    app.openapi = openapi  # type: ignore[method-assign]
