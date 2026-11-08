"""FastAPI dependencies: settings, a short-lived database connection, repositories, clock."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any

import psycopg
from argon2 import PasswordHasher
from fastapi import Cookie, Depends, Request

from application import problems
from application.auth import AuthService
from application.config import Settings
from application.instrument_resolution import InstrumentRepository
from application.problems import ProblemError
from application.security import DEFAULT_HASHER
from data_engine.auth_repository import PgAuthRepository
from data_engine.instrument_repository import PgInstrumentRepository
from domain.auth import Identity

SESSION_COOKIE = "gei_session"
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


def get_password_hasher() -> PasswordHasher:
    return DEFAULT_HASHER


def get_auth_service(
    conn: Annotated[psycopg.Connection[Any], Depends(get_connection)],
    settings: Annotated[Settings, Depends(get_settings)],
    hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
) -> AuthService:
    return AuthService(
        PgAuthRepository(conn),
        session_ttl=timedelta(minutes=settings.session_ttl_minutes),
        hasher=hasher,
    )


def session_token(token: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None) -> str:
    """The session cookie, or 401 before any database work happens."""
    if not token:
        raise ProblemError(problems.UNAUTHENTICATED, "Authentication required.")
    return token


def require_session(
    token: Annotated[str, Depends(session_token)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> Identity:
    """Every business route depends on this; ``workspace_id`` is taken from the result only."""
    identity = service.authenticate(token)
    if identity is None:
        raise ProblemError(problems.UNAUTHENTICATED, "Authentication required.")
    return identity


def get_workspace_id(identity: Annotated[Identity, Depends(require_session)]) -> uuid.UUID:
    """The caller's workspace. Taken from the session only, never from request input (P1-24)."""
    return identity.workspace_id
