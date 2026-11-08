"""P1-25: readiness aggregation never leaks why a dependency failed."""

from __future__ import annotations

import io
import logging
from collections.abc import Callable, Iterator

import pytest

from application.observability import JsonFormatter
from application.readiness import check_readiness


@pytest.fixture
def log_output() -> Iterator[io.StringIO]:
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


def test_all_probes_passing_is_ready() -> None:
    result = check_readiness({"postgres": lambda: True, "redis": lambda: True})
    assert result.ready is True
    assert result.checks == {"postgres": True, "redis": True}


def test_one_failing_probe_makes_it_not_ready_but_the_others_still_run() -> None:
    ran: list[str] = []

    def probe(name: str, ok: bool) -> Callable[[], bool]:
        def run() -> bool:
            ran.append(name)
            return ok

        return run

    result = check_readiness({"postgres": probe("postgres", False), "redis": probe("redis", True)})
    assert result.ready is False
    assert result.checks == {"postgres": False, "redis": True}
    assert ran == ["postgres", "redis"]


def test_a_probe_that_raises_counts_as_failed_and_does_not_stop_the_rest() -> None:
    def broken() -> bool:
        raise ConnectionError("boom")

    result = check_readiness({"redis": broken, "postgres": lambda: True})
    assert result.checks == {"redis": False, "postgres": True}
    assert result.ready is False


def test_exception_messages_never_reach_the_result_or_the_log(log_output: io.StringIO) -> None:
    def broken() -> bool:
        raise ConnectionError("could not connect to 10.0.0.5 password=hunter2")

    result = check_readiness({"postgres": broken})
    output = log_output.getvalue()
    assert "hunter2" not in output and "10.0.0.5" not in output
    assert "hunter2" not in repr(result)
    assert "ConnectionError" in output  # the type is enough to debug with
    assert "postgres" in output


def test_a_probe_returning_something_other_than_true_is_a_failure() -> None:
    result = check_readiness({"odd": lambda: 1})  # type: ignore[dict-item,return-value]
    assert result.checks == {"odd": False}
