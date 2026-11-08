"""P1-23: PgAuthRepository against real PostgreSQL 16 (sessions, audit, failure window)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from data_engine.auth_repository import PgAuthRepository
from domain.auth import UserRecord

pytestmark = pytest.mark.integration

Conn = psycopg.Connection[tuple[object, ...]]
T0 = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
HASH = "$argon2id$v=19$m=8,t=1,p=1$c29tZXNhbHQ$aGFzaGhhc2hoYXNoaGFzaA"
DIGEST = "a" * 64
OTHER_DIGEST = "b" * 64


@pytest.fixture
def repo(db: Conn) -> PgAuthRepository:
    return PgAuthRepository(db)


def owner(repo: PgAuthRepository, email: str = "owner@example.com") -> UserRecord:
    user = repo.create_owner_if_none(email, HASH, "Default workspace", now=T0)
    assert user is not None
    return user


def audit_rows(db: Conn, action: str | None = None) -> list[tuple[object, ...]]:
    query = (
        "SELECT action, actor_type, actor_id, workspace_id, resource_type, details_json "
        "FROM audit_logs"
    )
    if action:
        return db.execute(query + " WHERE action = %s ORDER BY created_at", (action,)).fetchall()
    return db.execute(query + " ORDER BY created_at").fetchall()


# --- owner creation ----------------------------------------------------------------------


def test_create_owner_creates_user_workspace_membership_and_audit(
    repo: PgAuthRepository, db: Conn
) -> None:
    user = repo.create_owner_if_none("Owner@Example.com ", HASH, "Default workspace", now=T0)
    assert user is not None
    assert user.email == "owner@example.com"  # stored normalised
    assert (user.status, user.role, user.password_hash) == ("active", "owner", HASH)
    member = db.execute(
        "SELECT role FROM workspace_members WHERE user_id = %s AND workspace_id = %s",
        (user.id, user.workspace_id),
    ).fetchone()
    assert member == ("owner",)
    (entry,) = audit_rows(db, "auth.owner_created")
    assert entry[1] == "system"
    assert entry[3] == user.workspace_id
    assert HASH not in json.dumps(entry[5])


def test_create_owner_refuses_when_any_user_exists(repo: PgAuthRepository, db: Conn) -> None:
    owner(repo)
    assert repo.create_owner_if_none("second@example.com", HASH, "Other", now=T0) is None
    assert db.execute("SELECT count(*) FROM users").fetchone() == (1,)
    assert db.execute("SELECT count(*) FROM workspaces").fetchone() == (1,)


# --- users and sessions ------------------------------------------------------------------


def test_find_user_by_email(repo: PgAuthRepository) -> None:
    user = owner(repo)
    assert repo.find_user_by_email("owner@example.com") == user
    assert repo.find_user_by_email("nobody@example.com") is None


def test_login_success_creates_session_and_audit_atomically(
    repo: PgAuthRepository, db: Conn
) -> None:
    user = owner(repo)
    session_id = repo.record_login_success(
        user,
        token_hash="c" * 64,
        now=T0,
        expires_at=T0 + timedelta(hours=12),
        details={"email_sha256": DIGEST},
    )
    lookup = repo.find_session("c" * 64)
    assert lookup is not None
    assert lookup.session_id == session_id
    assert (lookup.user_id, lookup.email, lookup.role) == (user.id, user.email, "owner")
    assert lookup.workspace_id == user.workspace_id
    assert lookup.expires_at == T0 + timedelta(hours=12)
    assert lookup.revoked_at is None
    (entry,) = audit_rows(db, "auth.login_succeeded")
    assert (entry[1], entry[2], entry[4]) == ("user", user.id, "auth_session")


def test_find_session_unknown_token_is_none(repo: PgAuthRepository) -> None:
    assert repo.find_session("d" * 64) is None


def test_a_user_without_workspace_membership_has_no_usable_session(
    repo: PgAuthRepository, db: Conn
) -> None:
    user_id = db.execute(
        "INSERT INTO users (email, password_hash) VALUES ('lonely@example.com', %s) RETURNING id",
        (HASH,),
    ).fetchone()
    assert user_id is not None
    db.execute(
        "INSERT INTO auth_sessions (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
        (user_id[0], "e" * 64, T0 + timedelta(hours=1)),
    )
    assert repo.find_session("e" * 64) is None


def test_revoke_sets_revoked_at_audits_and_is_idempotent(repo: PgAuthRepository, db: Conn) -> None:
    user = owner(repo)
    session_id = repo.record_login_success(
        user, token_hash="c" * 64, now=T0, expires_at=T0 + timedelta(hours=1), details={}
    )
    later = T0 + timedelta(minutes=5)
    repo.revoke_session(session_id, now=later)
    repo.revoke_session(session_id, now=later + timedelta(minutes=1))
    lookup = repo.find_session("c" * 64)
    assert lookup is not None and lookup.revoked_at == later
    assert len(audit_rows(db, "auth.logout")) == 1


def test_update_password_hash(repo: PgAuthRepository) -> None:
    user = owner(repo)
    repo.update_password_hash(user.id, HASH + "x")
    updated = repo.find_user_by_email(user.email)
    assert updated is not None and updated.password_hash == HASH + "x"


# --- failure window ----------------------------------------------------------------------


def fail(repo: PgAuthRepository, at: datetime, digest: str = DIGEST) -> None:
    repo.record_login_event(
        "auth.login_failed",
        None,
        now=at,
        details={"email_sha256": digest, "reason": "bad_password"},
    )


def test_failures_are_counted_within_the_window_per_account(repo: PgAuthRepository) -> None:
    since = T0 - timedelta(minutes=15)
    assert repo.recent_login_failures(DIGEST, since=since) == (0, None)
    fail(repo, T0 - timedelta(minutes=20))  # outside the window
    fail(repo, T0 - timedelta(minutes=2))
    fail(repo, T0 - timedelta(minutes=1))
    fail(repo, T0, digest=OTHER_DIGEST)  # someone else's
    assert repo.recent_login_failures(DIGEST, since=since) == (2, T0 - timedelta(minutes=1))


def test_a_successful_login_resets_the_count(repo: PgAuthRepository) -> None:
    user = owner(repo)
    digest = DIGEST
    fail(repo, T0 - timedelta(minutes=3), digest)
    fail(repo, T0 - timedelta(minutes=2), digest)
    repo.record_login_success(
        user,
        token_hash="c" * 64,
        now=T0 - timedelta(minutes=1),
        expires_at=T0 + timedelta(hours=1),
        details={"email_sha256": digest},
    )
    since = T0 - timedelta(minutes=15)
    assert repo.recent_login_failures(digest, since=since) == (0, None)
    fail(repo, T0, digest)
    assert repo.recent_login_failures(digest, since=since) == (1, T0)


def test_throttled_events_do_not_count_as_failures(repo: PgAuthRepository) -> None:
    repo.record_login_event(
        "auth.login_throttled", None, now=T0, details={"email_sha256": DIGEST, "retry_after": 30}
    )
    assert repo.recent_login_failures(DIGEST, since=T0 - timedelta(minutes=15)) == (0, None)


def test_known_user_failures_are_attributed_to_the_user(repo: PgAuthRepository, db: Conn) -> None:
    user = owner(repo)
    repo.record_login_event(
        "auth.login_failed",
        user,
        now=T0,
        details={"email_sha256": DIGEST, "reason": "bad_password"},
    )
    (entry,) = audit_rows(db, "auth.login_failed")
    assert (entry[1], entry[2], entry[3]) == ("user", user.id, user.workspace_id)


def test_audit_log_stays_append_only_through_the_repository(
    repo: PgAuthRepository, db: Conn
) -> None:
    fail(repo, T0)
    with pytest.raises(psycopg.errors.RestrictViolation), db.transaction():
        db.execute("DELETE FROM audit_logs WHERE action = 'auth.login_failed'")
