"""Problem catalog for application/problem+json errors (API_CONTRACT 25.4).

Framework-free: services raise ``ProblemError``; the API layer turns it into a response.
The contract names eight categories: parameter, instrument ambiguity, missing data,
authorization, provider rate limit, task conflict, model not applicable, internal error.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Placeholder authority until the project has a real domain (the contract example uses it too).
PROBLEM_TYPE_BASE = "https://example.invalid/problems/"

RESERVED_MEMBERS = frozenset({"type", "title", "status", "code", "detail", "trace_id"})


@dataclass(frozen=True)
class ProblemSpec:
    code: str
    status: int
    title: str


VALIDATION_ERROR = ProblemSpec("VALIDATION_ERROR", 422, "Invalid request parameters")
AMBIGUOUS_INSTRUMENT = ProblemSpec("AMBIGUOUS_INSTRUMENT", 409, "Instrument is ambiguous")
MISSING_REQUIRED_FIELD = ProblemSpec("MISSING_REQUIRED_FIELD", 422, "Required data unavailable")
UNAUTHENTICATED = ProblemSpec("UNAUTHENTICATED", 401, "Authentication required")
FORBIDDEN = ProblemSpec("FORBIDDEN", 403, "Access denied")
NOT_FOUND = ProblemSpec("NOT_FOUND", 404, "Resource not found")
METHOD_NOT_ALLOWED = ProblemSpec("METHOD_NOT_ALLOWED", 405, "Method not allowed")
RATE_LIMITED = ProblemSpec("RATE_LIMITED", 429, "Too many requests")
TASK_CONFLICT = ProblemSpec("TASK_CONFLICT", 409, "Task conflict")
MODEL_NOT_APPLICABLE = ProblemSpec("MODEL_NOT_APPLICABLE", 422, "Model not applicable")
SERVICE_UNAVAILABLE = ProblemSpec("SERVICE_UNAVAILABLE", 503, "Service unavailable")
INTERNAL_ERROR = ProblemSpec("INTERNAL_ERROR", 500, "Internal server error")

CATALOG: tuple[ProblemSpec, ...] = (
    VALIDATION_ERROR,
    AMBIGUOUS_INSTRUMENT,
    MISSING_REQUIRED_FIELD,
    UNAUTHENTICATED,
    FORBIDDEN,
    NOT_FOUND,
    METHOD_NOT_ALLOWED,
    RATE_LIMITED,
    TASK_CONFLICT,
    MODEL_NOT_APPLICABLE,
    SERVICE_UNAVAILABLE,
    INTERNAL_ERROR,
)


def problem_type(spec: ProblemSpec) -> str:
    return PROBLEM_TYPE_BASE + spec.code.lower().replace("_", "-")


class ProblemError(Exception):
    """An expected, client-visible failure. ``detail`` and extensions must be safe to expose."""

    def __init__(self, spec: ProblemSpec, detail: str, /, **extensions: Any) -> None:
        clash = sorted(RESERVED_MEMBERS & extensions.keys())
        if clash:
            raise ValueError(f"extension members must not reuse standard names: {', '.join(clash)}")
        super().__init__(f"{spec.code}: {detail}")
        self.spec = spec
        self.detail = detail
        self.extensions = extensions
