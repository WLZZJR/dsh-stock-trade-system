"""GET /health/live and /health/ready (API_CONTRACT 25). Public by design: no data in probes."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from api.deps import get_readiness_probes
from application import problems
from application.problems import ProblemError
from application.readiness import check_readiness

router = APIRouter(prefix="/health", tags=["health"])

NO_STORE = "no-store"


@router.get("/live")
def live() -> dict[str, str]:
    """The process is up. Deliberately checks nothing else."""
    return {"status": "ok"}


@router.get("/ready")
def ready(
    probes: Annotated[Mapping[str, Callable[[], bool]], Depends(get_readiness_probes)],
    response: Response,
) -> dict[str, object]:
    """200 only when PostgreSQL, Redis and the migration revision are all as expected.

    The body says which check failed, never why: this endpoint is unauthenticated.
    """
    result = check_readiness(probes)
    checks = {name: "ok" if ok else "fail" for name, ok in result.checks.items()}
    if not result.ready:
        error = ProblemError(
            problems.SERVICE_UNAVAILABLE, "One or more dependencies are not ready.", checks=checks
        )
        error.headers["Cache-Control"] = NO_STORE
        raise error
    response.headers["Cache-Control"] = NO_STORE
    return {"status": "ok", "checks": checks}
