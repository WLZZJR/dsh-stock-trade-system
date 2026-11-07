"""Integration smoke test against the real PostgreSQL 16 (D5: no SQLite stand-ins)."""

import os

import psycopg
import pytest

pytestmark = pytest.mark.integration


def _database_url() -> str:
    url = os.environ.get("GEI_DATABASE_URL")
    if not url:
        pytest.fail("GEI_DATABASE_URL is not set; integration tests need a real PostgreSQL 16")
    return url


def test_connects_to_postgres_16() -> None:
    with psycopg.connect(_database_url()) as conn:
        row = conn.execute("SELECT current_setting('server_version_num')::int").fetchone()
    assert row is not None
    assert row[0] // 10000 == 16


def test_required_extensions_are_available() -> None:
    with psycopg.connect(_database_url()) as conn:
        rows = conn.execute(
            "SELECT name FROM pg_available_extensions WHERE name IN ('pgcrypto', 'btree_gist')"
        ).fetchall()
    assert {r[0] for r in rows} == {"pgcrypto", "btree_gist"}
