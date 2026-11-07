"""Fixtures for database integration tests (real PostgreSQL 16, D5).

Every test session creates throw-away databases on the server named by GEI_DATABASE_URL and drops
them afterwards, so the developer's own `gei` database is never touched.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import psycopg
import pytest
from dbtools import psycopg_dsn, temporary_database, upgrade
from sqlalchemy.engine import URL


@pytest.fixture
def empty_database() -> Iterator[URL]:
    with temporary_database() as url:
        yield url


@pytest.fixture(scope="session")
def migrated_database() -> Iterator[URL]:
    """One database migrated to head, shared by constraint tests (each rolls back)."""
    with temporary_database() as url:
        upgrade(url)
        yield url


@pytest.fixture
def db(migrated_database: URL) -> Iterator[psycopg.Connection[tuple[object, ...]]]:
    """A connection inside a transaction that is always rolled back."""
    conn = psycopg.connect(psycopg_dsn(migrated_database))
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


@pytest.fixture
def connect() -> Callable[[URL], psycopg.Connection[tuple[object, ...]]]:
    return lambda url: psycopg.connect(psycopg_dsn(url), autocommit=True)
