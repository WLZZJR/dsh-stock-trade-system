"""Single-user authentication service (P1-23): login, throttling, sessions, audit.

Decisions that matter for security:

* wrong password, unknown account and disabled account give the same response and cost the same
  password verification, so the endpoint reveals nothing about which accounts exist;
* failed logins are counted per account (by e-mail digest) from the append-only audit log, with
  exponential backoff; blocked attempts are audited but never verified or counted again;
* only the SHA-256 digest of a session token is stored; passwords and tokens never reach the
  audit log, exceptions or logs.

Time comes from an injected clock, so the rules are testable without sleeping.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any, Protocol

from argon2 import PasswordHasher

from application import problems
from application.problems import ProblemError
from application.security import (
    DEFAULT_HASHER,
    MAX_PASSWORD_LENGTH,
    email_digest,
    hash_password,
    hash_token,
    new_session_token,
    password_needs_rehash,
    verify_password,
)
from domain.auth import Identity, SessionLookup, UserRecord

MAX_FREE_FAILURES = 5
BASE_DELAY = timedelta(seconds=30)
MAX_DELAY = timedelta(minutes=15)
WINDOW = timedelta(minutes=15)  # only failures this recent count
MAX_TOKEN_LENGTH = 512

INVALID_CREDENTIALS = "Invalid email or password."
_MAX_EXPONENT = 16  # keeps 2**n small; far beyond what reaches MAX_DELAY


class AuthRepository(Protocol):
    """Persistence behind the service; implemented over PostgreSQL in ``data_engine``."""

    def find_user_by_email(self, email: str) -> UserRecord | None: ...

    def recent_login_failures(
        self, email_sha256: str, *, since: datetime
    ) -> tuple[int, datetime | None]:
        """Failures after ``since`` and after the account's last successful login."""
        ...

    def record_login_success(
        self,
        user: UserRecord,
        *,
        token_hash: str,
        now: datetime,
        expires_at: datetime,
        details: dict[str, Any],
    ) -> uuid.UUID:
        """Create the session and its audit entry atomically; returns the session id."""
        ...

    def record_login_event(
        self, action: str, user: UserRecord | None, *, now: datetime, details: dict[str, Any]
    ) -> None: ...

    def find_session(self, token_hash: str) -> SessionLookup | None: ...

    def revoke_session(self, session_id: uuid.UUID, *, now: datetime) -> None:
        """Revoke and audit atomically."""
        ...

    def update_password_hash(self, user_id: uuid.UUID, password_hash: str) -> None: ...


@dataclass(frozen=True)
class LoginResult:
    token: str  # shown to the caller exactly once; never stored
    expires_at: datetime
    session_id: uuid.UUID
    user_id: uuid.UUID
    email: str
    workspace_id: uuid.UUID
    role: str


def login_delay(failures: int) -> timedelta:
    """No delay for the first ``MAX_FREE_FAILURES``; then 30 s, doubling, capped."""
    if failures < MAX_FREE_FAILURES:
        return timedelta(0)
    exponent = min(failures - MAX_FREE_FAILURES, _MAX_EXPONENT)
    return min(MAX_DELAY, BASE_DELAY * (1 << exponent))


@lru_cache(maxsize=8)
def _dummy_hash(hasher: PasswordHasher) -> str:
    """Hashed once per hasher, so building a service per request stays cheap."""
    return hash_password("not-a-real-account-password", hasher)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AuthService:
    def __init__(
        self,
        repo: AuthRepository,
        *,
        session_ttl: timedelta,
        hasher: PasswordHasher = DEFAULT_HASHER,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._repo = repo
        self._ttl = session_ttl
        self._hasher = hasher
        self._clock = clock
        # Verified against when the account does not exist, so both paths do equal work.
        self._dummy_hash = _dummy_hash(hasher)

    def login(self, email: str, password: str) -> LoginResult:
        now = self._clock()
        normalized = email.strip().lower()
        digest = email_digest(normalized)

        failures, last_failure = self._repo.recent_login_failures(digest, since=now - WINDOW)
        delay = login_delay(failures)
        if last_failure is not None and now < last_failure + delay:
            retry_after = math.ceil((last_failure + delay - now).total_seconds())
            self._repo.record_login_event(
                "auth.login_throttled",
                None,
                now=now,
                details={"email_sha256": digest, "retry_after": retry_after},
            )
            error = ProblemError(
                problems.RATE_LIMITED,
                "Too many failed sign-in attempts. Try again later.",
                retry_after=retry_after,
            )
            error.headers["Retry-After"] = str(retry_after)
            raise error

        user = self._repo.find_user_by_email(normalized)
        stored = user.password_hash if user is not None else self._dummy_hash
        password_ok = len(password) <= MAX_PASSWORD_LENGTH and verify_password(
            stored, password, self._hasher
        )

        reason: str | None
        if user is None:
            reason = "unknown_user"
        elif user.status != "active":
            reason = "disabled"
        elif not password_ok:
            reason = "bad_password"
        else:
            reason = None
        if reason is not None or user is None:
            self._repo.record_login_event(
                "auth.login_failed",
                user,
                now=now,
                details={"email_sha256": digest, "reason": reason},
            )
            raise ProblemError(problems.UNAUTHENTICATED, INVALID_CREDENTIALS)

        if password_needs_rehash(user.password_hash, self._hasher):
            self._repo.update_password_hash(user.id, hash_password(password, self._hasher))
        token = new_session_token()
        expires_at = now + self._ttl
        session_id = self._repo.record_login_success(
            user,
            token_hash=hash_token(token),
            now=now,
            expires_at=expires_at,
            details={"email_sha256": digest},
        )
        return LoginResult(
            token=token,
            expires_at=expires_at,
            session_id=session_id,
            user_id=user.id,
            email=user.email,
            workspace_id=user.workspace_id,
            role=user.role,
        )

    def authenticate(self, token: str) -> Identity | None:
        """The identity behind a session token, or ``None`` for anything not valid right now."""
        if not token or len(token) > MAX_TOKEN_LENGTH:
            return None
        session = self._repo.find_session(hash_token(token))
        if session is None or session.revoked_at is not None:
            return None
        if session.expires_at <= self._clock() or session.user_status != "active":
            return None
        return Identity(
            session_id=session.session_id,
            user_id=session.user_id,
            email=session.email,
            workspace_id=session.workspace_id,
            role=session.role,
        )

    def logout(self, identity: Identity) -> None:
        self._repo.revoke_session(identity.session_id, now=self._clock())
