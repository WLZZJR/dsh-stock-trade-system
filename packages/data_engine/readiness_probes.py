"""Dependency probes behind ``GET /health/ready`` (P1-25).

Each probe returns ``True`` or raises; it never returns details. Connections are short-lived with
a short timeout so an unreachable dependency fails the probe quickly instead of hanging it.
"""

from __future__ import annotations

from pathlib import Path

import psycopg
import redis
from alembic.script import ScriptDirectory

PROBE_TIMEOUT_SECONDS = 2
DEFAULT_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "database" / "migrations"


def expected_migration_head(migrations_dir: Path = DEFAULT_MIGRATIONS_DIR) -> str:
    """The single head revision of the migration scripts shipped with this code."""
    heads = ScriptDirectory(str(migrations_dir)).get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"expected exactly one migration head, found {len(heads)} heads")
    return heads[0]


def _connect(database_url: str) -> psycopg.Connection[tuple[object, ...]]:
    return psycopg.connect(database_url, connect_timeout=PROBE_TIMEOUT_SECONDS, autocommit=True)


def postgres_probe(database_url: str) -> bool:
    with _connect(database_url) as conn:
        return conn.execute("SELECT 1").fetchone() == (1,)


def migrations_probe(database_url: str, expected_head: str) -> bool:
    """True only when the database is migrated to exactly the revision this code expects."""
    with _connect(database_url) as conn:
        return conn.execute("SELECT version_num FROM alembic_version").fetchall() == [
            (expected_head,)
        ]


def redis_probe(redis_url: str) -> bool:
    client = redis.Redis.from_url(
        redis_url,
        socket_connect_timeout=PROBE_TIMEOUT_SECONDS,
        socket_timeout=PROBE_TIMEOUT_SECONDS,
    )
    try:
        return client.ping() is True
    finally:
        client.close()
