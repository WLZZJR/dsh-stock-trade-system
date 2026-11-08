"""P1-23 / D2: `python -m api.manage create-owner` on a real database."""

from __future__ import annotations

from contextlib import nullcontext

import psycopg
import pytest

from api.manage import main, read_password
from application.security import verify_password

pytestmark = pytest.mark.integration

Conn = psycopg.Connection[tuple[object, ...]]
PASSWORD = "correct horse battery staple"  # noqa: S105 - fixture value, not a credential


def no_prompt(_: str) -> str:
    raise AssertionError("must not prompt when GEI_OWNER_PASSWORD is set")


def run(db: Conn, *args: str, environ: dict[str, str] | None = None, prompt=no_prompt) -> int:  # type: ignore[no-untyped-def]
    return main(
        ["create-owner", *args],
        environ=environ if environ is not None else {"GEI_OWNER_PASSWORD": PASSWORD},
        prompt=prompt,
        connect=lambda: nullcontext(db),
    )


def test_create_owner_stores_a_hashed_password_and_audits(
    db: Conn, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(db, "--email", "Owner@Example.com") == 0
    out = capsys.readouterr()
    assert "owner@example.com" in out.out
    assert PASSWORD not in out.out + out.err
    row = db.execute("SELECT email, password_hash, status FROM users").fetchone()
    assert row is not None
    assert row[0] == "owner@example.com" and row[2] == "active"
    assert row[1].startswith("$argon2id$") and PASSWORD not in row[1]
    assert verify_password(row[1], PASSWORD)
    assert db.execute("SELECT role FROM workspace_members").fetchone() == ("owner",)
    assert db.execute(
        "SELECT count(*) FROM audit_logs WHERE action = 'auth.owner_created'"
    ).fetchone() == (1,)


def test_a_second_owner_is_refused_with_exit_code_1(
    db: Conn, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(db, "--email", "owner@example.com") == 0
    capsys.readouterr()
    assert run(db, "--email", "second@example.com") == 1
    assert "already exists" in capsys.readouterr().err
    assert db.execute("SELECT count(*) FROM users").fetchone() == (1,)


def test_weak_password_is_refused_without_echoing_it(
    db: Conn, capsys: pytest.CaptureFixture[str]
) -> None:
    weak = "tiny-S3CRET"  # noqa: S105 - fixture value, not a credential
    assert run(db, "--email", "owner@example.com", environ={"GEI_OWNER_PASSWORD": weak}) == 1
    out = capsys.readouterr()
    assert weak not in out.out + out.err
    assert db.execute("SELECT count(*) FROM users").fetchone() == (0,)


def test_invalid_email_is_refused(db: Conn, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(db, "--email", "not-an-email") == 1
    assert "email" in capsys.readouterr().err
    assert db.execute("SELECT count(*) FROM users").fetchone() == (0,)


def test_without_env_the_password_is_prompted_twice_and_must_match(
    db: Conn, capsys: pytest.CaptureFixture[str]
) -> None:
    answers = iter([PASSWORD, PASSWORD])
    assert run(db, "--email", "owner@example.com", environ={}, prompt=lambda _: next(answers)) == 0
    answers = iter(["one password here", "another password!"])
    assert run(db, "--email", "x@example.com", environ={}, prompt=lambda _: next(answers)) == 1
    assert "do not match" in capsys.readouterr().err


def test_read_password_prefers_the_environment() -> None:
    assert read_password({"GEI_OWNER_PASSWORD": "from-env-value"}, no_prompt) == "from-env-value"


def test_read_password_rejects_an_empty_prompt_answer() -> None:
    with pytest.raises(ValueError, match="empty"):
        read_password({}, lambda _: "")
