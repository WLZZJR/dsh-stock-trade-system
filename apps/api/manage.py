"""Management commands: ``python -m api.manage create-owner --email you@example.com`` (D2).

The password is read from ``GEI_OWNER_PASSWORD`` or prompted for twice; it is never a command-line
argument (those leak into shell history and process lists) and is never printed.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Any

import psycopg

from application.config import ConfigError, load_settings
from application.owner import DEFAULT_WORKSPACE_NAME, OwnerExistsError, create_owner
from data_engine.auth_repository import PgAuthRepository

PASSWORD_ENV = "GEI_OWNER_PASSWORD"  # noqa: S105 - the variable's name, not a secret
CONNECT_TIMEOUT_SECONDS = 5

Connect = Callable[[], AbstractContextManager[psycopg.Connection[Any]]]


def read_password(environ: Mapping[str, str], prompt: Callable[[str], str]) -> str:
    from_env = environ.get(PASSWORD_ENV)
    if from_env:
        return from_env
    first = prompt("Owner password: ")
    if not first:
        raise ValueError("password must not be empty")
    if first != prompt("Repeat password: "):
        raise ValueError("passwords do not match")
    return first


def _connect_from_settings() -> AbstractContextManager[psycopg.Connection[Any]]:
    settings = load_settings()
    return psycopg.connect(
        settings.database_url.get_secret_value(),
        autocommit=True,
        connect_timeout=CONNECT_TIMEOUT_SECONDS,
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    prompt: Callable[[str], str] = getpass.getpass,
    connect: Connect = _connect_from_settings,
) -> int:
    parser = argparse.ArgumentParser(prog="api.manage")
    commands = parser.add_subparsers(dest="command", required=True)
    owner = commands.add_parser("create-owner", help="create the first (Owner) user")
    owner.add_argument("--email", required=True)
    owner.add_argument("--workspace-name", default=DEFAULT_WORKSPACE_NAME)
    args = parser.parse_args(argv)

    try:
        password = read_password(os.environ if environ is None else environ, prompt)
        with connect() as conn:
            user = create_owner(
                PgAuthRepository(conn),
                args.email,
                password,
                workspace_name=args.workspace_name,
                now=datetime.now(UTC),
            )
    except (ValueError, OwnerExistsError) as exc:  # messages never contain the password
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2
    except psycopg.OperationalError:
        print("error: the database is unavailable", file=sys.stderr)
        return 2
    print(f"owner created: {user.email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
