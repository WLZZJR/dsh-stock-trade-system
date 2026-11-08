"""P1-25: the probes against real PostgreSQL 16 and Redis."""

from __future__ import annotations

import os
import time

import psycopg
import pytest
import redis
from dbtools import psycopg_dsn, upgrade
from sqlalchemy.engine import URL

from data_engine.readiness_probes import (
    PROBE_TIMEOUT_SECONDS,
    expected_migration_head,
    migrations_probe,
    postgres_probe,
    redis_probe,
)

pytestmark = pytest.mark.integration

UNREACHABLE_POSTGRES = "postgresql://nobody:nothing@127.0.0.1:1/none"
UNREACHABLE_REDIS = "redis://127.0.0.1:1/0"
FAST_ENOUGH = PROBE_TIMEOUT_SECONDS + 4  # the timeout plus slack for a loaded machine


def test_postgres_probe_is_true_for_a_reachable_database(migrated_database: URL) -> None:
    assert postgres_probe(psycopg_dsn(migrated_database)) is True


def test_postgres_probe_fails_fast_when_unreachable() -> None:
    started = time.monotonic()
    with pytest.raises(psycopg.OperationalError):
        postgres_probe(UNREACHABLE_POSTGRES)
    assert time.monotonic() - started < FAST_ENOUGH


def test_migrations_probe_is_true_exactly_at_head(migrated_database: URL) -> None:
    assert migrations_probe(psycopg_dsn(migrated_database), expected_migration_head()) is True


def test_migrations_probe_is_false_for_the_wrong_revision(migrated_database: URL) -> None:
    assert migrations_probe(psycopg_dsn(migrated_database), "0001") is False


def test_migrations_probe_is_false_when_the_database_is_behind(empty_database: URL) -> None:
    upgrade(empty_database, "0007")  # head is newer than this
    assert migrations_probe(psycopg_dsn(empty_database), expected_migration_head()) is False


def test_migrations_probe_fails_on_an_unmigrated_database(empty_database: URL) -> None:
    with pytest.raises(psycopg.errors.UndefinedTable):
        migrations_probe(psycopg_dsn(empty_database), expected_migration_head())


def test_redis_probe_is_true_for_the_dev_redis() -> None:
    url = os.environ.get("GEI_REDIS_URL")
    if not url:
        pytest.skip("GEI_REDIS_URL is not set")
    try:
        assert redis_probe(url) is True
    except redis.exceptions.RedisError:
        pytest.skip("no Redis reachable at GEI_REDIS_URL (CI has only PostgreSQL)")


def test_redis_probe_fails_fast_when_unreachable() -> None:
    started = time.monotonic()
    with pytest.raises(redis.exceptions.RedisError):
        redis_probe(UNREACHABLE_REDIS)
    assert time.monotonic() - started < FAST_ENOUGH
