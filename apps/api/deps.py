"""FastAPI dependencies: settings, a short-lived database connection, repositories, clock."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Annotated, Any

import psycopg
from fastapi import Depends, Request

from application import problems
from application.config import Settings
from application.instrument_resolution import InstrumentRepository
from application.problems import ProblemError
from data_engine.instrument_repository import PgInstrumentRepository

CONNECT_TIMEOUT_SECONDS = 5  # a dead database host must not hang a request


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings  # set by the lifespan
    return settings


def get_connection(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Iterator[psycopg.Connection[Any]]:
    """One autocommit connection per request, closed afterwards.

    The driver's message can contain host names and credentials, so it is never surfaced.
    """
    try:
        conn: psycopg.Connection[Any] = psycopg.connect(
            settings.database_url.get_secret_value(),
            autocommit=True,
            connect_timeout=CONNECT_TIMEOUT_SECONDS,
        )
    except psycopg.OperationalError:
        raise ProblemError(problems.SERVICE_UNAVAILABLE, "The database is unavailable.") from None
    try:
        yield conn
    finally:
        conn.close()


def get_instrument_repository(
    conn: Annotated[psycopg.Connection[Any], Depends(get_connection)],
) -> InstrumentRepository:
    return PgInstrumentRepository(conn)


def get_today() -> date:
    return datetime.now(UTC).date()
