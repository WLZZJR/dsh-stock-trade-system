"""P1-23: login, throttling, sessions and audit rules, against an in-memory repository."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from argon2 import PasswordHasher

from application import problems
from application.auth import (
    BASE_DELAY,
    MAX_DELAY,
    MAX_FREE_FAILURES,
    WINDOW,
    AuthService,
    login_delay,
)
from application.problems import ProblemError
from application.security import email_digest, hash_password, hash_token
from domain.auth import SessionLookup, UserRecord

FAST = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
EMAIL = "owner@example.com"
PASSWORD = "correct horse battery staple"  # noqa: S105 - fixture value, not a credential
T0 = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
TTL = timedelta(hours=12)
WORKSPACE = uuid.uuid4()


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class CountingHasher(PasswordHasher):
    def __init__(self) -> None:
        super().__init__(time_cost=1, memory_cost=8, parallelism=1)
        self.verifications = 0

    def verify(self, hash: str | bytes, password: str | bytes) -> bool:  # noqa: A002
        self.verifications += 1
        return super().verify(hash, password)


@dataclass
class AuditEntry:
    action: str
    actor_user_id: uuid.UUID | None
    workspace_id: uuid.UUID | None
    resource_type: str
    resource_id: uuid.UUID | None
    details: dict[str, Any]
    at: datetime


@dataclass
class FakeRepo:
    users: dict[str, UserRecord] = field(default_factory=dict)
    sessions: dict[str, dict[str, Any]] = field(default_factory=dict)  # by token_hash
    audit: list[AuditEntry] = field(default_factory=list)
    password_updates: list[tuple[uuid.UUID, str]] = field(default_factory=list)

    def find_user_by_email(self, email: str) -> UserRecord | None:
        return self.users.get(email)

    def recent_login_failures(
        self, email_sha256: str, *, since: datetime
    ) -> tuple[int, datetime | None]:
        successes = [
            e.at
            for e in self.audit
            if e.action == "auth.login_succeeded" and e.details["email_sha256"] == email_sha256
        ]
        floor = max([since, *successes])
        failures = [
            e.at
            for e in self.audit
            if e.action == "auth.login_failed"
            and e.details["email_sha256"] == email_sha256
            and e.at > floor
        ]
        return len(failures), max(failures, default=None)

    def record_login_success(
        self,
        user: UserRecord,
        *,
        token_hash: str,
        now: datetime,
        expires_at: datetime,
        details: dict[str, Any],
    ) -> uuid.UUID:
        session_id = uuid.uuid4()
        self.sessions[token_hash] = {
            "id": session_id,
            "user": user,
            "expires_at": expires_at,
            "revoked_at": None,
        }
        self._audit("auth.login_succeeded", user, details, now)
        return session_id

    def record_login_event(
        self, action: str, user: UserRecord | None, *, now: datetime, details: dict[str, Any]
    ) -> None:
        self._audit(action, user, details, now)

    def find_session(self, token_hash: str) -> SessionLookup | None:
        row = self.sessions.get(token_hash)
        if row is None:
            return None
        user: UserRecord = row["user"]
        return SessionLookup(
            session_id=row["id"],
            user_id=user.id,
            email=user.email,
            user_status=user.status,
            workspace_id=user.workspace_id,
            role=user.role,
            expires_at=row["expires_at"],
            revoked_at=row["revoked_at"],
        )

    def revoke_session(self, session_id: uuid.UUID, *, now: datetime) -> None:
        for row in self.sessions.values():
            if row["id"] == session_id:
                row["revoked_at"] = now
                self._audit("auth.logout", row["user"], {"session_id": str(session_id)}, now)

    def update_password_hash(self, user_id: uuid.UUID, password_hash: str) -> None:
        self.password_updates.append((user_id, password_hash))

    def _audit(
        self, action: str, user: UserRecord | None, details: dict[str, Any], now: datetime
    ) -> None:
        self.audit.append(
            AuditEntry(
                action,
                user.id if user else None,
                user.workspace_id if user else None,
                "user" if user else "login",
                user.id if user else None,
                details,
                now,
            )
        )


def make_user(status: str = "active", password_hash: str | None = None) -> UserRecord:
    return UserRecord(
        id=uuid.uuid4(),
        email=EMAIL,
        password_hash=password_hash or hash_password(PASSWORD, FAST),
        status=status,
        workspace_id=WORKSPACE,
        role="owner",
    )


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def repo() -> FakeRepo:
    return FakeRepo(users={EMAIL: make_user()})


@pytest.fixture
def service(repo: FakeRepo, clock: Clock) -> AuthService:
    return AuthService(repo, session_ttl=TTL, hasher=FAST, clock=clock)


WRONG = "wrong password!!"  # noqa: S105 - fixture value, not a credential


def fail(service: AuthService, email: str = EMAIL, password: str = WRONG) -> None:
    with pytest.raises(ProblemError) as exc:
        service.login(email, password)
    assert exc.value.spec is problems.UNAUTHENTICATED


def throttled(service: AuthService, password: str = PASSWORD) -> ProblemError:
    with pytest.raises(ProblemError) as exc:
        service.login(EMAIL, password)
    assert exc.value.spec is problems.RATE_LIMITED
    return exc.value


# --- login -------------------------------------------------------------------------------


def test_login_creates_a_session_and_stores_only_the_token_hash(
    service: AuthService, repo: FakeRepo
) -> None:
    result = service.login(EMAIL, PASSWORD)
    assert result.expires_at == T0 + TTL
    assert result.email == EMAIL and result.role == "owner" and result.workspace_id == WORKSPACE
    assert list(repo.sessions) == [hash_token(result.token)]
    assert result.token not in json.dumps(repo.audit, default=str)


def test_login_is_audited_without_secrets(service: AuthService, repo: FakeRepo) -> None:
    result = service.login(EMAIL, PASSWORD)
    (entry,) = repo.audit
    assert entry.action == "auth.login_succeeded"
    assert entry.details["email_sha256"] == email_digest(EMAIL)
    blob = json.dumps(entry.details)
    assert PASSWORD not in blob and result.token not in blob


def test_email_is_trimmed_and_case_insensitive(service: AuthService) -> None:
    assert service.login("  Owner@Example.COM ", PASSWORD).email == EMAIL


def test_wrong_password_unknown_user_and_disabled_user_look_identical(
    repo: FakeRepo, clock: Clock
) -> None:
    repo.users["disabled@example.com"] = UserRecord(
        id=uuid.uuid4(),
        email="disabled@example.com",
        password_hash=hash_password(PASSWORD, FAST),
        status="disabled",
        workspace_id=WORKSPACE,
        role="owner",
    )
    service = AuthService(repo, session_ttl=TTL, hasher=FAST, clock=clock)
    messages = set()
    for email, password in [
        (EMAIL, "wrong password!!"),
        ("nobody@example.com", PASSWORD),
        ("disabled@example.com", PASSWORD),  # right password, still refused
    ]:
        with pytest.raises(ProblemError) as exc:
            service.login(email, password)
        assert exc.value.spec is problems.UNAUTHENTICATED
        messages.add(exc.value.detail)
    assert len(messages) == 1
    assert repo.sessions == {}


def test_failures_are_audited_with_an_internal_reason(service: AuthService, repo: FakeRepo) -> None:
    fail(service)
    fail(service, email="nobody@example.com")
    reasons = [e.details["reason"] for e in repo.audit if e.action == "auth.login_failed"]
    assert reasons == ["bad_password", "unknown_user"]
    assert "wrong password!!" not in json.dumps(repo.audit, default=str)


def test_unknown_user_still_costs_one_password_verification(repo: FakeRepo, clock: Clock) -> None:
    hasher = CountingHasher()
    service = AuthService(repo, session_ttl=TTL, hasher=hasher, clock=clock)
    before = hasher.verifications
    fail(service, email="nobody@example.com")
    assert hasher.verifications - before == 1  # same work as a real account: no timing oracle


def test_login_upgrades_an_outdated_password_hash(repo: FakeRepo, clock: Clock) -> None:
    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    stronger = PasswordHasher(time_cost=2, memory_cost=16, parallelism=1)
    user = make_user(password_hash=hash_password(PASSWORD, weak))
    repo.users[EMAIL] = user
    AuthService(repo, session_ttl=TTL, hasher=stronger, clock=clock).login(EMAIL, PASSWORD)
    ((user_id, new_hash),) = repo.password_updates
    assert user_id == user.id
    assert stronger.verify(new_hash, PASSWORD)


def test_no_rehash_when_the_hash_is_current(service: AuthService, repo: FakeRepo) -> None:
    service.login(EMAIL, PASSWORD)
    assert repo.password_updates == []


# --- throttling --------------------------------------------------------------------------


def test_after_five_failures_even_the_right_password_is_throttled(
    service: AuthService, repo: FakeRepo
) -> None:
    for _ in range(MAX_FREE_FAILURES):
        fail(service)
    error = throttled(service)
    assert error.extensions["retry_after"] == int(BASE_DELAY.total_seconds())
    assert error.headers["Retry-After"] == str(int(BASE_DELAY.total_seconds()))
    assert repo.sessions == {}


def test_four_failures_do_not_throttle(service: AuthService) -> None:
    for _ in range(MAX_FREE_FAILURES - 1):
        fail(service)
    assert service.login(EMAIL, PASSWORD).token


def test_throttled_attempts_are_audited_but_not_counted_as_failures(
    service: AuthService, repo: FakeRepo
) -> None:
    for _ in range(MAX_FREE_FAILURES):
        fail(service)
    throttled(service)
    throttled(service)
    actions = [e.action for e in repo.audit]
    assert actions.count("auth.login_failed") == MAX_FREE_FAILURES
    assert actions.count("auth.login_throttled") == 2


def test_throttle_lifts_after_the_delay_and_backs_off_exponentially(
    service: AuthService, clock: Clock
) -> None:
    for _ in range(MAX_FREE_FAILURES):
        fail(service)
    clock.advance(BASE_DELAY.total_seconds() - 1)
    assert throttled(service).extensions["retry_after"] == 1
    clock.advance(2)  # delay over: a wrong password is evaluated again (failure number 6)
    fail(service)
    error = throttled(service)
    assert error.extensions["retry_after"] == int(BASE_DELAY.total_seconds()) * 2


def test_successful_login_after_the_delay_resets_the_counter(
    service: AuthService, clock: Clock
) -> None:
    for _ in range(MAX_FREE_FAILURES):
        fail(service)
    clock.advance(BASE_DELAY.total_seconds() + 1)
    service.login(EMAIL, PASSWORD)
    clock.advance(1)
    for _ in range(MAX_FREE_FAILURES - 1):
        fail(service)  # a fresh count: still below the limit
    assert service.login(EMAIL, PASSWORD).token


def test_login_delay_schedule_doubles_and_is_capped() -> None:
    seconds = [int(login_delay(n).total_seconds()) for n in range(0, 10)]
    assert seconds[:MAX_FREE_FAILURES] == [0] * MAX_FREE_FAILURES
    assert seconds[MAX_FREE_FAILURES:] == [30, 60, 120, 240, 480]
    assert login_delay(MAX_FREE_FAILURES + 20) == MAX_DELAY
    assert login_delay(10_000) == MAX_DELAY  # no overflow for absurd counts


def test_failures_outside_the_window_are_forgotten(service: AuthService, clock: Clock) -> None:
    for _ in range(MAX_FREE_FAILURES):
        fail(service)
    clock.advance(WINDOW.total_seconds() + 1)
    fail(service)  # evaluated normally, not throttled


def test_unknown_emails_are_throttled_too(service: AuthService) -> None:
    for _ in range(MAX_FREE_FAILURES):
        fail(service, email="nobody@example.com")
    with pytest.raises(ProblemError) as exc:
        service.login("nobody@example.com", PASSWORD)
    assert exc.value.spec is problems.RATE_LIMITED  # existence of the account is not revealed


def test_throttling_is_per_account(service: AuthService, repo: FakeRepo) -> None:
    other = "second@example.com"
    repo.users[other] = UserRecord(
        id=uuid.uuid4(),
        email=other,
        password_hash=hash_password(PASSWORD, FAST),
        status="active",
        workspace_id=WORKSPACE,
        role="viewer",
    )
    for _ in range(MAX_FREE_FAILURES):
        fail(service)
    assert service.login(other, PASSWORD).email == other


# --- sessions ----------------------------------------------------------------------------


def test_authenticate_returns_the_identity_for_a_live_session(service: AuthService) -> None:
    token = service.login(EMAIL, PASSWORD).token
    identity = service.authenticate(token)
    assert identity is not None
    assert (identity.email, identity.role, identity.workspace_id) == (EMAIL, "owner", WORKSPACE)


@pytest.mark.parametrize("token", ["", "unknown-token", "x" * 5000])
def test_authenticate_rejects_unknown_empty_or_oversized_tokens(
    service: AuthService, token: str
) -> None:
    assert service.authenticate(token) is None


def test_authenticate_rejects_an_expired_session(service: AuthService, clock: Clock) -> None:
    token = service.login(EMAIL, PASSWORD).token
    clock.advance(TTL.total_seconds() - 1)
    assert service.authenticate(token) is not None
    clock.advance(1)  # expires_at itself is already expired
    assert service.authenticate(token) is None


def test_authenticate_rejects_a_revoked_session(service: AuthService) -> None:
    token = service.login(EMAIL, PASSWORD).token
    identity = service.authenticate(token)
    assert identity is not None
    service.logout(identity)
    assert service.authenticate(token) is None


def test_authenticate_rejects_a_disabled_user(service: AuthService, repo: FakeRepo) -> None:
    token = service.login(EMAIL, PASSWORD).token
    user = repo.users[EMAIL]
    repo.sessions[hash_token(token)]["user"] = UserRecord(
        id=user.id,
        email=user.email,
        password_hash=user.password_hash,
        status="disabled",
        workspace_id=user.workspace_id,
        role=user.role,
    )
    assert service.authenticate(token) is None


def test_logout_is_audited(service: AuthService, repo: FakeRepo) -> None:
    identity = service.authenticate(service.login(EMAIL, PASSWORD).token)
    assert identity is not None
    service.logout(identity)
    assert [e.action for e in repo.audit] == ["auth.login_succeeded", "auth.logout"]
