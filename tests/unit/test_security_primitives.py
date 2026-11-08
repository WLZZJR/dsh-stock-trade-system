"""P1-23: password hashing (argon2id), session tokens and the stored token hash."""

from __future__ import annotations

import re

import pytest
from argon2 import PasswordHasher

from application.security import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    check_password_policy,
    email_digest,
    hash_password,
    hash_token,
    new_session_token,
    password_needs_rehash,
    verify_password,
)

# Cheap parameters keep the suite fast; production uses the library defaults.
FAST = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
GOOD = "correct horse battery staple"


def test_hash_is_argon2id_and_salted() -> None:
    first = hash_password(GOOD, FAST)
    second = hash_password(GOOD, FAST)
    assert first.startswith("$argon2id$")
    assert first != second  # random salt per hash
    assert GOOD not in first


def test_verify_accepts_the_right_password_and_rejects_others() -> None:
    stored = hash_password(GOOD, FAST)
    assert verify_password(stored, GOOD, FAST) is True
    assert verify_password(stored, GOOD + "x", FAST) is False
    assert verify_password(stored, "", FAST) is False


@pytest.mark.parametrize("garbage", ["", "plaintext", "$argon2id$broken", "$2b$12$notargon"])
def test_verify_never_raises_on_a_malformed_stored_hash(garbage: str) -> None:
    assert verify_password(garbage, GOOD, FAST) is False


def test_needs_rehash_when_parameters_change() -> None:
    stored = hash_password(GOOD, FAST)
    stronger = PasswordHasher(time_cost=2, memory_cost=16, parallelism=1)
    assert password_needs_rehash(stored, FAST) is False
    assert password_needs_rehash(stored, stronger) is True
    assert password_needs_rehash("not-a-hash", FAST) is True


def test_policy_accepts_a_long_enough_password() -> None:
    check_password_policy("a" * MIN_PASSWORD_LENGTH)
    check_password_policy("a" * MAX_PASSWORD_LENGTH)


@pytest.mark.parametrize(
    "bad", ["", "short", "a" * (MIN_PASSWORD_LENGTH - 1), "a" * (MAX_PASSWORD_LENGTH + 1)]
)
def test_policy_rejects_too_short_or_too_long(bad: str) -> None:
    with pytest.raises(ValueError, match="password"):
        check_password_policy(bad)


def test_policy_errors_never_echo_the_password() -> None:
    secret = "tiny-S3CRET"  # noqa: S105 - fixture value, not a credential
    with pytest.raises(ValueError) as exc:
        check_password_policy(secret)
    assert secret not in str(exc.value)


def test_session_tokens_are_long_unique_and_url_safe() -> None:
    tokens = {new_session_token() for _ in range(200)}
    assert len(tokens) == 200
    for token in tokens:
        assert len(token) >= 43  # 32 random bytes, base64url without padding
        assert re.fullmatch(r"[A-Za-z0-9_\-]+", token)


def test_token_hash_is_sha256_hex_and_deterministic() -> None:
    digest = hash_token("abc")
    assert digest == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert re.fullmatch(r"[0-9a-f]{64}", hash_token(new_session_token()))
    assert hash_token("abc") == digest
    assert hash_token("abd") != digest


def test_email_digest_is_case_and_whitespace_insensitive_and_not_the_address() -> None:
    assert email_digest("Owner@Example.com ") == email_digest("owner@example.com")
    assert email_digest("a@example.com") != email_digest("b@example.com")
    assert "owner" not in email_digest("owner@example.com")
    assert re.fullmatch(r"[0-9a-f]{64}", email_digest("owner@example.com"))
