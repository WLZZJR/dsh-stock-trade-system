"""Creation of the first (Owner) user (P1-23, D2). There is no open registration.

Validation happens before anything is stored; the password is hashed here and only the hash is
handed to the repository. Errors never contain the password.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Protocol

from argon2 import PasswordHasher

from application.security import DEFAULT_HASHER, check_password_policy, hash_password
from domain.auth import UserRecord

DEFAULT_WORKSPACE_NAME = "Default workspace"
MAX_EMAIL_LENGTH = 254
_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


class OwnerExistsError(Exception):
    """A user already exists; this system has exactly one owner in MVP-1."""


class OwnerRepository(Protocol):
    def create_owner_if_none(
        self, email: str, password_hash: str, workspace_name: str, *, now: datetime
    ) -> UserRecord | None: ...


def create_owner(
    repo: OwnerRepository,
    email: str,
    password: str,
    *,
    workspace_name: str = DEFAULT_WORKSPACE_NAME,
    hasher: PasswordHasher = DEFAULT_HASHER,
    now: datetime,
) -> UserRecord:
    """Raises ``ValueError`` for a bad email or password and ``OwnerExistsError`` if not first."""
    normalized = email.strip().lower()
    if len(normalized) > MAX_EMAIL_LENGTH or not _EMAIL_RE.fullmatch(normalized):
        raise ValueError("email is not a valid address")
    check_password_policy(password)
    user = repo.create_owner_if_none(
        normalized, hash_password(password, hasher), workspace_name, now=now
    )
    if user is None:
        raise OwnerExistsError("an owner already exists")
    return user
