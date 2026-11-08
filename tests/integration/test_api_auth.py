"""P1-23: login / logout / me and session enforcement, end to end on PostgreSQL 16."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime

import psycopg
import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from masterdata import Builder

from api.deps import SESSION_COOKIE, get_connection, get_password_hasher, get_settings
from api.main import create_app
from application.config import Settings
from application.owner import create_owner
from data_engine.auth_repository import PgAuthRepository

pytestmark = pytest.mark.integration

Conn = psycopg.Connection[tuple[object, ...]]
FAST = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
EMAIL = "owner@example.com"
PASSWORD = "correct horse battery staple"  # noqa: S105 - fixture value, not a credential
WRONG = "not the right password"  # noqa: S105 - fixture value, not a credential


def settings(env: str = "dev", ttl: int = 60) -> Settings:
    return Settings(
        env=env,  # type: ignore[arg-type]
        session_ttl_minutes=ttl,
        database_url="postgresql://unused/unused",  # type: ignore[arg-type]
        redis_url="redis://unused/0",  # type: ignore[arg-type]
    )


def make_client(db: Conn, env: str = "dev", ttl: int = 60) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_connection] = lambda: db
    app.dependency_overrides[get_settings] = lambda: settings(env, ttl)
    app.dependency_overrides[get_password_hasher] = lambda: FAST
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client(db: Conn) -> Iterator[TestClient]:
    create_owner(
        PgAuthRepository(db),
        EMAIL,
        PASSWORD,
        hasher=FAST,
        now=datetime.now(UTC),
    )
    yield make_client(db)


def login(client: TestClient, email: str = EMAIL, password: str = PASSWORD):  # type: ignore[no-untyped-def]
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def cookie_of(response) -> str:  # type: ignore[no-untyped-def]
    return str(response.cookies[SESSION_COOKIE])


def auth(token: str) -> dict[str, str]:
    return {"Cookie": f"{SESSION_COOKIE}={token}"}


# --- login -------------------------------------------------------------------------------


def test_login_returns_the_user_and_sets_a_hardened_cookie(client: TestClient) -> None:
    response = login(client)
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == EMAIL and body["user"]["role"] == "owner"
    assert "password" not in response.text and "token" not in body
    cookie = response.headers["set-cookie"].lower()
    assert f"{SESSION_COOKIE}=" in cookie
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie
    assert "max-age=3600" in cookie
    assert "secure" not in cookie  # dev over plain http
    assert response.headers["cache-control"] == "no-store"


def test_cookie_is_secure_in_production(db: Conn) -> None:
    create_owner(
        PgAuthRepository(db),
        EMAIL,
        PASSWORD,
        hasher=FAST,
        now=datetime.now(UTC),
    )
    response = login(make_client(db, env="prod"))
    assert "secure" in response.headers["set-cookie"].lower()


def test_only_the_token_hash_is_stored(client: TestClient, db: Conn) -> None:
    token = cookie_of(login(client))
    rows = db.execute("SELECT token_hash FROM auth_sessions").fetchall()
    assert rows == [(hashlib.sha256(token.encode()).hexdigest(),)]
    everything = str(db.execute("SELECT * FROM auth_sessions").fetchall()) + str(
        db.execute("SELECT * FROM audit_logs").fetchall()
    )
    assert token not in everything
    assert PASSWORD not in everything


def test_each_login_gets_a_new_token(client: TestClient) -> None:
    first, second = cookie_of(login(client)), cookie_of(login(client))
    assert first != second
    assert client.get("/api/v1/auth/me", headers=auth(first)).status_code == 200
    assert client.get("/api/v1/auth/me", headers=auth(second)).status_code == 200


def test_bad_credentials_are_a_generic_401_for_every_cause(client: TestClient, db: Conn) -> None:
    wrong_password = login(client, password=WRONG)
    unknown_user = login(client, email="nobody@example.com")
    db.execute("UPDATE users SET status = 'disabled'")
    disabled = login(client)
    for response in (wrong_password, unknown_user, disabled):
        assert response.status_code == 401
        assert response.json()["code"] == "UNAUTHENTICATED"
        assert SESSION_COOKIE not in response.cookies
    assert (
        wrong_password.json()["detail"]
        == unknown_user.json()["detail"]
        == disabled.json()["detail"]
    )


def test_login_success_and_failure_are_both_audited_without_secrets(
    client: TestClient, db: Conn
) -> None:
    login(client, password=WRONG)
    login(client)
    actions = [
        r[0]
        for r in db.execute(
            "SELECT action FROM audit_logs WHERE action LIKE 'auth.login_%' ORDER BY created_at"
        ).fetchall()
    ]
    assert actions == ["auth.login_failed", "auth.login_succeeded"]
    blob = str(db.execute("SELECT details_json FROM audit_logs").fetchall())
    assert WRONG not in blob and PASSWORD not in blob and EMAIL not in blob  # digest only


def test_repeated_failures_are_throttled_with_retry_after(client: TestClient, db: Conn) -> None:
    for _ in range(5):
        assert login(client, password=WRONG).status_code == 401
    blocked = login(client)  # the right password is refused while throttled
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "RATE_LIMITED"
    assert int(blocked.headers["retry-after"]) > 0
    assert blocked.json()["retry_after"] == int(blocked.headers["retry-after"])
    assert SESSION_COOKIE not in blocked.cookies
    assert db.execute(
        "SELECT count(*) FROM audit_logs WHERE action = 'auth.login_throttled'"
    ).fetchone() == (1,)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"email": EMAIL},
        {"password": PASSWORD},
        {"email": "x" * 300, "password": PASSWORD},
        {"email": EMAIL, "password": "p" * 1025},
        {"email": EMAIL, "password": ""},
    ],
)
def test_malformed_login_bodies_are_422_and_never_echoed(
    client: TestClient, payload: dict[str, str]
) -> None:
    response = client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert "p" * 1025 not in response.text


# --- me / logout / session lifecycle -----------------------------------------------------


def test_me_returns_the_identity(client: TestClient) -> None:
    token = cookie_of(login(client))
    response = client.get("/api/v1/auth/me", headers=auth(token))
    assert response.status_code == 200
    body = response.json()
    assert (body["email"], body["role"]) == (EMAIL, "owner")
    assert body["workspace_id"] and body["user_id"]
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("cookie", [None, "", "garbage", "x" * 2000])
def test_me_without_a_valid_session_is_401(client: TestClient, cookie: str | None) -> None:
    headers = auth(cookie) if cookie is not None else {}
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHENTICATED"
    assert response.headers["content-type"] == "application/problem+json"


def test_a_bearer_header_is_not_a_session(client: TestClient) -> None:
    token = cookie_of(login(client))
    client.cookies.clear()  # only the Authorization header is sent below
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_logout_revokes_the_session_and_clears_the_cookie(client: TestClient, db: Conn) -> None:
    token = cookie_of(login(client))
    response = client.post("/api/v1/auth/logout", headers=auth(token))
    assert response.status_code == 204
    assert response.content == b""
    cleared = response.headers["set-cookie"].lower()
    assert f"{SESSION_COOKIE}=" in cleared and "max-age=0" in cleared
    assert client.get("/api/v1/auth/me", headers=auth(token)).status_code == 401
    assert db.execute("SELECT revoked_at IS NOT NULL FROM auth_sessions").fetchone() == (True,)
    assert db.execute(
        "SELECT count(*) FROM audit_logs WHERE action = 'auth.logout'"
    ).fetchone() == (1,)


def test_logout_without_a_session_is_401(client: TestClient) -> None:
    assert client.post("/api/v1/auth/logout").status_code == 401


def test_an_expired_session_is_rejected(client: TestClient, db: Conn) -> None:
    token = cookie_of(login(client))
    db.execute("UPDATE auth_sessions SET expires_at = now() - interval '1 second'")
    assert client.get("/api/v1/auth/me", headers=auth(token)).status_code == 401


def test_a_session_revoked_in_the_database_is_rejected(client: TestClient, db: Conn) -> None:
    token = cookie_of(login(client))
    db.execute("UPDATE auth_sessions SET revoked_at = now()")
    assert client.get("/api/v1/auth/me", headers=auth(token)).status_code == 401


def test_disabling_the_user_ends_existing_sessions(client: TestClient, db: Conn) -> None:
    token = cookie_of(login(client))
    db.execute("UPDATE users SET status = 'disabled'")
    assert client.get("/api/v1/auth/me", headers=auth(token)).status_code == 401


# --- business routes need a session ------------------------------------------------------


def test_instrument_endpoints_require_a_session(client: TestClient, db: Conn) -> None:
    build = Builder(db)
    _, _, listing = build.stock("Acme Corp", "ACME")
    urls = [
        "/api/v1/instruments/resolve?query=ACME",
        f"/api/v1/instruments/{listing}",
    ]
    for url in urls:
        assert client.get(url).status_code == 401
    token = cookie_of(login(client))
    for url in urls:
        assert client.get(url, headers=auth(token)).status_code == 200


def test_health_live_stays_public(client: TestClient) -> None:
    assert client.get("/health/live").status_code == 200
