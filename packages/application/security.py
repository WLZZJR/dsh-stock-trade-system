"""Password hashing and session-token primitives (P1-23, D3).

Passwords use argon2id with the library defaults (RFC 9106 low-memory profile). Session tokens are
32 random bytes; only their SHA-256 digest is ever stored, so a database leak does not yield
usable sessions. Nothing here logs or echoes a password or token.
"""

from __future__ import annotations

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 1024  # bounds the work an unauthenticated caller can force

DEFAULT_HASHER = PasswordHasher()


def check_password_policy(password: str) -> None:
    """Raises ``ValueError`` without echoing the password."""
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise ValueError(
            f"password must be {MIN_PASSWORD_LENGTH} to {MAX_PASSWORD_LENGTH} characters long"
        )


def hash_password(password: str, hasher: PasswordHasher = DEFAULT_HASHER) -> str:
    return hasher.hash(password)


def verify_password(stored: str, password: str, hasher: PasswordHasher = DEFAULT_HASHER) -> bool:
    """True only for a matching password; a malformed stored hash is simply a failure."""
    try:
        return hasher.verify(stored, password)
    except (VerificationError, InvalidHashError):
        return False


def password_needs_rehash(stored: str, hasher: PasswordHasher = DEFAULT_HASHER) -> bool:
    try:
        return hasher.check_needs_rehash(stored)
    except InvalidHashError:
        return True


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def email_digest(email: str) -> str:
    """Stable, non-reversible key for an e-mail address (audit records and throttling)."""
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
