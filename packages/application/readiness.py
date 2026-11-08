"""Readiness aggregation for ``GET /health/ready`` (P1-25).

The probe endpoint is public, so it reports only which dependency is up or down. Why one failed
(host names, ports, driver messages, which may include credentials) is never returned and never
logged: only the exception *type* is written to the log.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass

logger = logging.getLogger("gei.readiness")


@dataclass(frozen=True)
class ReadinessResult:
    checks: dict[str, bool]

    @property
    def ready(self) -> bool:
        return all(self.checks.values())


def check_readiness(probes: Mapping[str, Callable[[], bool]]) -> ReadinessResult:
    """Run every probe (one failure does not hide the others); only an explicit ``True`` passes."""
    checks: dict[str, bool] = {}
    for name, probe in probes.items():
        try:
            checks[name] = probe() is True
        except Exception as exc:
            checks[name] = False
            logger.warning(
                "readiness_check_failed",
                extra={"fields": {"check": name, "error_type": type(exc).__name__}},
            )
    return ReadinessResult(checks)
