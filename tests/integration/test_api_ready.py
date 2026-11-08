"""P1-25: /health/ready with the real probes, real settings, real PostgreSQL and Redis."""

from __future__ import annotations

import os

import pytest
import redis
from dbtools import psycopg_dsn, upgrade
from fastapi.testclient import TestClient
from sqlalchemy.engine import URL

from api.deps import get_settings
from api.main import create_app
from application.config import Settings
from data_engine.readiness_probes import redis_probe

pytestmark = pytest.mark.integration

DEAD_REDIS = "redis://:redis-pw-1234@127.0.0.1:1/0"  # nothing listens on port 1


def real_redis_url() -> str:
    url = os.environ.get("GEI_REDIS_URL")
    if not url:
        pytest.skip("GEI_REDIS_URL is not set")
    try:
        redis_probe(url)
    except redis.exceptions.RedisError:
        pytest.skip("no Redis reachable at GEI_REDIS_URL (CI has only PostgreSQL)")
    return url


def client_for(database: URL, redis_url: str) -> tuple[TestClient, str]:
    dsn = psycopg_dsn(database)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_url=dsn,  # type: ignore[arg-type]
        redis_url=redis_url,  # type: ignore[arg-type]
    )
    return TestClient(app, raise_server_exceptions=False), dsn


def test_ready_is_200_when_the_database_is_at_head_and_redis_answers(
    migrated_database: URL,
) -> None:
    client, _ = client_for(migrated_database, real_redis_url())
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["checks"] == {"postgres": "ok", "redis": "ok", "migrations": "ok"}


def test_ready_is_503_when_the_database_is_behind_the_code(empty_database: URL) -> None:
    upgrade(empty_database, "0007")
    client, _ = client_for(empty_database, real_redis_url())
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["checks"] == {"postgres": "ok", "redis": "ok", "migrations": "fail"}


def test_ready_is_503_on_an_unmigrated_database(empty_database: URL) -> None:
    client, _ = client_for(empty_database, real_redis_url())
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["migrations"] == "fail"


def test_ready_is_503_without_redis_and_never_leaks_the_urls(migrated_database: URL) -> None:
    client, dsn = client_for(migrated_database, DEAD_REDIS)
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["checks"] == {"postgres": "ok", "redis": "fail", "migrations": "ok"}
    assert "redis-pw-1234" not in response.text and "127.0.0.1" not in response.text
    password = dsn.split("://", 1)[1].split("@", 1)[0].partition(":")[2]
    if password:
        assert password not in response.text


def test_ready_is_503_when_postgres_is_unreachable() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_url="postgresql://gei:db-pw-5678@127.0.0.1:1/gei",  # type: ignore[arg-type]
        redis_url=DEAD_REDIS,  # type: ignore[arg-type]
    )
    response = TestClient(app, raise_server_exceptions=False).get("/health/ready")
    assert response.status_code == 503
    assert response.json()["checks"] == {"postgres": "fail", "redis": "fail", "migrations": "fail"}
    assert "db-pw-5678" not in response.text
