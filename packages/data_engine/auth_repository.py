"""PostgreSQL implementation of the authentication persistence (P1-23).

Every multi-statement operation runs in one transaction (a savepoint when the caller already has
one). Timestamps are passed in by the service, so the clock is single-sourced. Only digests are
stored: the session token's SHA-256, and an e-mail digest inside audit details; never a password
or a token.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from domain.auth import SessionLookup, UserRecord

_USER_COLUMNS = """
    u.id, u.email, u.password_hash, u.status, m.workspace_id, m.role
"""

_AUDIT = """
    INSERT INTO audit_logs
      (workspace_id, actor_type, actor_id, action, resource_type, resource_id, details_json,
       created_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
"""


def _normalise(email: str) -> str:
    return email.strip().lower()


def _required(row: tuple[Any, ...] | None) -> tuple[Any, ...]:
    """INSERT ... RETURNING and aggregate queries always yield a row; guard against surprises."""
    if row is None:
        raise RuntimeError("expected a row from the database")
    return row


def _user(row: tuple[Any, ...]) -> UserRecord:
    return UserRecord(
        id=row[0],
        email=row[1],
        password_hash=row[2],
        status=row[3],
        workspace_id=row[4],
        role=row[5],
    )


class PgAuthRepository:
    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn

    def find_user_by_email(self, email: str) -> UserRecord | None:
        row = self._conn.execute(
            f"SELECT {_USER_COLUMNS} FROM users u "  # noqa: S608 - constant column list
            "JOIN workspace_members m ON m.user_id = u.id "
            "WHERE u.email = %s ORDER BY m.created_at LIMIT 1",
            (_normalise(email),),
        ).fetchone()
        return _user(row) if row else None

    def recent_login_failures(
        self, email_sha256: str, *, since: datetime
    ) -> tuple[int, datetime | None]:
        row = self._conn.execute(
            """
            SELECT count(*), max(created_at) FROM audit_logs
            WHERE action = 'auth.login_failed' AND details_json ->> 'email_sha256' = %(digest)s
              AND created_at > GREATEST(
                %(since)s,
                COALESCE((SELECT max(created_at) FROM audit_logs
                          WHERE action = 'auth.login_succeeded'
                            AND details_json ->> 'email_sha256' = %(digest)s),
                         '-infinity'::timestamptz))
            """,
            {"digest": email_sha256, "since": since},
        ).fetchone()
        row = _required(row)
        return int(row[0]), row[1]

    def record_login_success(
        self,
        user: UserRecord,
        *,
        token_hash: str,
        now: datetime,
        expires_at: datetime,
        details: dict[str, Any],
    ) -> uuid.UUID:
        with self._conn.transaction():
            row = _required(
                self._conn.execute(
                    "INSERT INTO auth_sessions (user_id, token_hash, created_at, expires_at) "
                    "VALUES (%s, %s, %s, %s) RETURNING id",
                    (user.id, token_hash, now, expires_at),
                ).fetchone()
            )
            session_id: uuid.UUID = row[0]
            self._conn.execute(
                _AUDIT,
                (
                    user.workspace_id,
                    "user",
                    user.id,
                    "auth.login_succeeded",
                    "auth_session",
                    session_id,
                    Jsonb(details),
                    now,
                ),
            )
        return session_id

    def record_login_event(
        self, action: str, user: UserRecord | None, *, now: datetime, details: dict[str, Any]
    ) -> None:
        if user is None:
            params: tuple[Any, ...] = (None, "system", None, action, "login", None)
        else:
            params = (user.workspace_id, "user", user.id, action, "user", user.id)
        self._conn.execute(_AUDIT, (*params, Jsonb(details), now))

    def find_session(self, token_hash: str) -> SessionLookup | None:
        row = self._conn.execute(
            """
            SELECT s.id, s.user_id, u.email, u.status, m.workspace_id, m.role,
                   s.expires_at, s.revoked_at
            FROM auth_sessions s
            JOIN users u ON u.id = s.user_id
            JOIN workspace_members m ON m.user_id = u.id
            WHERE s.token_hash = %s
            ORDER BY m.created_at LIMIT 1
            """,
            (token_hash,),
        ).fetchone()
        if row is None:
            return None
        return SessionLookup(
            session_id=row[0],
            user_id=row[1],
            email=row[2],
            user_status=row[3],
            workspace_id=row[4],
            role=row[5],
            expires_at=row[6],
            revoked_at=row[7],
        )

    def revoke_session(self, session_id: uuid.UUID, *, now: datetime) -> None:
        with self._conn.transaction():
            row = self._conn.execute(
                "UPDATE auth_sessions SET revoked_at = %s WHERE id = %s AND revoked_at IS NULL "
                "RETURNING user_id",
                (now, session_id),
            ).fetchone()
            if row is None:  # unknown or already revoked: nothing to audit
                return
            self._conn.execute(
                _AUDIT,
                (
                    self._workspace_of(row[0]),
                    "user",
                    row[0],
                    "auth.logout",
                    "auth_session",
                    session_id,
                    Jsonb({}),
                    now,
                ),
            )

    def update_password_hash(self, user_id: uuid.UUID, password_hash: str) -> None:
        self._conn.execute(
            "UPDATE users SET password_hash = %s, updated_at = now() WHERE id = %s",
            (password_hash, user_id),
        )

    def create_owner_if_none(
        self, email: str, password_hash: str, workspace_name: str, *, now: datetime
    ) -> UserRecord | None:
        """Create the first user with its workspace; ``None`` when any user already exists."""
        with self._conn.transaction():
            # Serialise concurrent runs so two owners can never be created at once.
            self._conn.execute("SELECT pg_advisory_xact_lock(hashtext('gei.create_owner'))")
            if self._conn.execute("SELECT EXISTS (SELECT 1 FROM users)").fetchone() == (True,):
                return None
            workspace = _required(
                self._conn.execute(
                    "INSERT INTO workspaces (name) VALUES (%s) RETURNING id", (workspace_name,)
                ).fetchone()
            )
            user = _required(
                self._conn.execute(
                    "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id",
                    (_normalise(email), password_hash),
                ).fetchone()
            )
            self._conn.execute(
                "INSERT INTO workspace_members (workspace_id, user_id, role) "
                "VALUES (%s, %s, 'owner')",
                (workspace[0], user[0]),
            )
            self._conn.execute(
                _AUDIT,
                (
                    workspace[0],
                    "system",
                    None,
                    "auth.owner_created",
                    "user",
                    user[0],
                    Jsonb({}),
                    now,
                ),
            )
            return UserRecord(
                id=user[0],
                email=_normalise(email),
                password_hash=password_hash,
                status="active",
                workspace_id=workspace[0],
                role="owner",
            )

    def _workspace_of(self, user_id: uuid.UUID) -> uuid.UUID | None:
        row = self._conn.execute(
            "SELECT workspace_id FROM workspace_members WHERE user_id = %s "
            "ORDER BY created_at LIMIT 1",
            (user_id,),
        ).fetchone()
        return row[0] if row else None
