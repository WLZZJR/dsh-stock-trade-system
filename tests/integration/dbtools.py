"""Helpers for database integration tests: temporary databases and Alembic invocation."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy.engine import URL, make_url

ROOT = Path(__file__).resolve().parents[2]


def server_url() -> URL:
    raw = os.environ.get("GEI_DATABASE_URL")
    if not raw:
        pytest.fail("GEI_DATABASE_URL is not set; integration tests need a real PostgreSQL 16")
    return make_url(raw)


def psycopg_dsn(url: URL) -> str:
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


def alembic_config(url: URL) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "database" / "migrations"))
    cfg.attributes["sqlalchemy_url"] = url
    return cfg


def upgrade(url: URL, revision: str = "head") -> None:
    command.upgrade(alembic_config(url), revision)


def downgrade(url: URL, revision: str) -> None:
    command.downgrade(alembic_config(url), revision)


@contextmanager
def temporary_database() -> Iterator[URL]:
    """Create an empty database, yield its URL, and drop it on exit."""
    admin = server_url().set(database="postgres")
    name = f"gei_test_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(psycopg_dsn(admin), autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        yield server_url().set(database=name)
    finally:
        with psycopg.connect(psycopg_dsn(admin), autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )
