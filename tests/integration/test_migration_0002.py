"""P1-11: migration 0002 — workspaces, users, members, sessions, append-only audit_logs."""

from __future__ import annotations

from collections.abc import Callable

import psycopg
import pytest
from dbtools import downgrade, upgrade
from sqlalchemy.engine import URL

pytestmark = pytest.mark.integration

Conn = psycopg.Connection[tuple[object, ...]]
TOKEN = "a" * 64


def _workspace(db: Conn, name: str = "ws") -> object:
    row = db.execute("INSERT INTO workspaces (name) VALUES (%s) RETURNING id", (name,)).fetchone()
    assert row is not None
    return row[0]


def _user(db: Conn, email: str = "owner@example.test") -> object:
    row = db.execute(
        "INSERT INTO users (email, password_hash) VALUES (%s, 'argon2-placeholder') RETURNING id",
        (email,),
    ).fetchone()
    assert row is not None
    return row[0]


def test_audit_logs_reject_update_delete(db: Conn) -> None:
    db.execute(
        "INSERT INTO audit_logs (actor_type, action, resource_type) "
        "VALUES ('system', 'seed', 'workspace')"
    )
    with pytest.raises(psycopg.errors.RestrictViolation, match="append-only"), db.transaction():
        db.execute("UPDATE audit_logs SET action = 'tampered'")
    with pytest.raises(psycopg.errors.RestrictViolation, match="append-only"), db.transaction():
        db.execute("DELETE FROM audit_logs")
    row = db.execute("SELECT count(*), min(action) FROM audit_logs").fetchone()
    assert row == (1, "seed")


def test_audit_logs_actor_type_is_checked(db: Conn) -> None:
    with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
        db.execute(
            "INSERT INTO audit_logs (actor_type, action, resource_type) "
            "VALUES ('robot', 'x', 'workspace')"
        )


def test_audit_logs_details_default_to_empty_object_and_workspace_is_optional(db: Conn) -> None:
    row = db.execute(
        "INSERT INTO audit_logs (actor_type, action, resource_type) "
        "VALUES ('service', 'login_failed', 'user') RETURNING workspace_id, details_json"
    ).fetchone()
    assert row == (None, {})


def test_audit_logs_workspace_fk_blocks_workspace_delete(db: Conn) -> None:
    ws = _workspace(db)
    db.execute(
        "INSERT INTO audit_logs (workspace_id, actor_type, action, resource_type) "
        "VALUES (%s, 'system', 'created', 'workspace')",
        (ws,),
    )
    with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
        db.execute("DELETE FROM workspaces WHERE id = %s", (ws,))


def test_users_email_unique_and_status_checked(db: Conn) -> None:
    _user(db)
    with pytest.raises(psycopg.errors.UniqueViolation), db.transaction():
        _user(db)
    with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
        db.execute(
            "INSERT INTO users (email, password_hash, status) "
            "VALUES ('x@example.test', 'h', 'banned')"
        )
    row = db.execute("SELECT status FROM users WHERE email = 'owner@example.test'").fetchone()
    assert row == ("active",)


def test_workspace_members_role_checked_and_fk_enforced(db: Conn) -> None:
    ws, user = _workspace(db), _user(db)
    db.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES (%s, %s, 'owner')",
        (ws, user),
    )
    with pytest.raises(psycopg.errors.UniqueViolation), db.transaction():
        db.execute(
            "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES (%s, %s, 'viewer')",
            (ws, user),
        )
    other = _user(db, "other@example.test")
    with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
        db.execute(
            "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES (%s, %s, 'admin')",
            (ws, other),
        )
    with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
        db.execute(
            "INSERT INTO workspace_members (workspace_id, user_id, role) "
            "VALUES (gen_random_uuid(), %s, 'viewer')",
            (other,),
        )


def test_deleting_user_cascades_to_memberships_and_sessions(db: Conn) -> None:
    ws, user = _workspace(db), _user(db)
    db.execute(
        "INSERT INTO workspace_members (workspace_id, user_id, role) VALUES (%s, %s, 'owner')",
        (ws, user),
    )
    db.execute(
        "INSERT INTO auth_sessions (user_id, token_hash, expires_at) "
        "VALUES (%s, %s, now() + interval '1 day')",
        (user, TOKEN),
    )
    db.execute("DELETE FROM users WHERE id = %s", (user,))
    assert db.execute("SELECT count(*) FROM workspace_members").fetchone() == (0,)
    assert db.execute("SELECT count(*) FROM auth_sessions").fetchone() == (0,)


def test_auth_sessions_store_only_unique_64_char_token_hash(db: Conn) -> None:
    user = _user(db)
    db.execute(
        "INSERT INTO auth_sessions (user_id, token_hash, expires_at) "
        "VALUES (%s, %s, now() + interval '1 day')",
        (user, TOKEN),
    )
    with pytest.raises(psycopg.errors.UniqueViolation), db.transaction():
        db.execute(
            "INSERT INTO auth_sessions (user_id, token_hash, expires_at) "
            "VALUES (%s, %s, now() + interval '1 day')",
            (user, TOKEN),
        )
    with pytest.raises(psycopg.errors.StringDataRightTruncation), db.transaction():
        db.execute(
            "INSERT INTO auth_sessions (user_id, token_hash, expires_at) "
            "VALUES (%s, %s, now() + interval '1 day')",
            (user, "b" * 65),
        )
    with pytest.raises(psycopg.errors.NotNullViolation), db.transaction():
        db.execute(
            "INSERT INTO auth_sessions (user_id, token_hash) VALUES (%s, %s)", (user, "c" * 64)
        )
    row = db.execute(
        "SELECT revoked_at FROM auth_sessions WHERE token_hash = %s", (TOKEN,)
    ).fetchone()
    assert row == (None,)


def test_downgrade_to_0001_removes_only_0002_objects(
    empty_database: URL, connect: Callable[[URL], Conn]
) -> None:
    upgrade(empty_database)
    downgrade(empty_database, "0001")
    with connect(empty_database) as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ).fetchall()
    assert {r[0] for r in rows} == {"alembic_version", "currencies"}
    upgrade(empty_database)
