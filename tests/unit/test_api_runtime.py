"""P1-20: API startup configures redacted logging and never runs uvicorn's raw access log."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from application.config import ConfigError

DOCKERFILE = Path(__file__).resolve().parents[2] / "deploy" / "api.Dockerfile"


@pytest.fixture(autouse=True)
def _restore_gei_logger() -> Iterator[None]:
    logger = logging.getLogger("gei")
    previous = (logger.handlers, logger.level, logger.propagate)
    yield
    logger.handlers, logger.level, logger.propagate = previous


def _env(monkeypatch: pytest.MonkeyPatch, **values: str) -> None:
    for name in ("GEI_ENV", "GEI_LOG_LEVEL", "GEI_DATABASE_URL", "GEI_REDIS_URL"):
        monkeypatch.delenv(name, raising=False)
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_startup_applies_the_configured_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(
        monkeypatch,
        GEI_LOG_LEVEL="WARNING",
        GEI_DATABASE_URL="postgresql://u:p@localhost/db",
        GEI_REDIS_URL="redis://localhost:6379/0",
    )
    with TestClient(create_app()):
        assert logging.getLogger("gei").level == logging.WARNING


def test_startup_fails_fast_without_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    _env(monkeypatch)
    with pytest.raises(ConfigError, match="GEI_DATABASE_URL"), TestClient(create_app()):
        pass


def test_uvicorn_access_log_is_disabled_because_it_prints_query_strings() -> None:
    command = next(
        line for line in DOCKERFILE.read_text(encoding="utf-8").splitlines() if "uvicorn" in line
    )
    assert "--no-access-log" in command
