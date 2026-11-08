"""P1-23 / D2: the first owner is created only through a validated, audited, single-shot path."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from argon2 import PasswordHasher

from application.owner import OwnerExistsError, create_owner
from domain.auth import UserRecord

FAST = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
PASSWORD = "correct horse battery staple"  # noqa: S105 - fixture value, not a credential
NOW = datetime(2026, 11, 8, tzinfo=UTC)


@dataclass
class FakeOwnerRepo:
    exists: bool = False
    calls: list[tuple[str, str, str]] = field(default_factory=list)

    def create_owner_if_none(
        self, email: str, password_hash: str, workspace_name: str, *, now: datetime
    ) -> UserRecord | None:
        if self.exists:
            return None
        self.calls.append((email, password_hash, workspace_name))
        return UserRecord(
            id=uuid.uuid4(),
            email=email.strip().lower(),
            password_hash=password_hash,
            status="active",
            workspace_id=uuid.uuid4(),
            role="owner",
        )


def test_creates_the_owner_with_a_hashed_password() -> None:
    repo = FakeOwnerRepo()
    user = create_owner(repo, "Owner@Example.com", PASSWORD, hasher=FAST, now=NOW)
    assert user.role == "owner" and user.email == "owner@example.com"
    ((_, stored_hash, workspace),) = repo.calls
    assert stored_hash.startswith("$argon2id$")
    assert PASSWORD not in stored_hash
    assert FAST.verify(stored_hash, PASSWORD)
    assert workspace == "Default workspace"


def test_a_custom_workspace_name_is_used() -> None:
    repo = FakeOwnerRepo()
    create_owner(
        repo, "owner@example.com", PASSWORD, workspace_name="Research", hasher=FAST, now=NOW
    )
    assert repo.calls[0][2] == "Research"


@pytest.mark.parametrize(
    "email",
    ["", "no-at-sign", "a@b", "two@@example.com", "spa ce@example.com", "x" * 250 + "@example.com"],
)
def test_invalid_emails_are_rejected_before_anything_is_stored(email: str) -> None:
    repo = FakeOwnerRepo()
    with pytest.raises(ValueError, match="email"):
        create_owner(repo, email, PASSWORD, hasher=FAST, now=NOW)
    assert repo.calls == []


@pytest.mark.parametrize("weak", ["", "short", "a" * 11])
def test_weak_passwords_are_rejected_without_echoing_them(weak: str) -> None:
    repo = FakeOwnerRepo()
    with pytest.raises(ValueError, match="password") as exc:
        create_owner(repo, "owner@example.com", weak, hasher=FAST, now=NOW)
    if weak:
        assert weak not in str(exc.value)
    assert repo.calls == []


def test_a_second_owner_is_refused() -> None:
    with pytest.raises(OwnerExistsError):
        create_owner(
            FakeOwnerRepo(exists=True), "owner@example.com", PASSWORD, hasher=FAST, now=NOW
        )
