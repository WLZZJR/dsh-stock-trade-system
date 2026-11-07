"""P1-19: migrations and the committed schema snapshot cannot drift apart.

D6 keeps migrations as hand-written SQL, so there are no ORM models to diff against. The
committed snapshot (database/schema_snapshot.txt) is the declared schema instead: any migration
that changes the schema without a reviewed snapshot update fails here. After an intended change:

    UPDATE_SCHEMA_SNAPSHOT=1 make test-integration
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import psycopg
import pytest
from alembic.script import ScriptDirectory
from dbtools import ROOT, alembic_config, downgrade, upgrade
from schema_dump import dump_schema
from sqlalchemy.engine import URL

pytestmark = pytest.mark.integration

Conn = psycopg.Connection[tuple[object, ...]]
SNAPSHOT = ROOT / "database" / "schema_snapshot.txt"


def _revisions_ascending(url: URL) -> list[str]:
    script = ScriptDirectory.from_config(alembic_config(url))
    return [r.revision for r in reversed(list(script.walk_revisions()))]


def test_head_schema_matches_committed_snapshot(
    empty_database: URL, connect: Callable[[URL], Conn]
) -> None:
    upgrade(empty_database)
    with connect(empty_database) as conn:
        actual = dump_schema(conn)
    if os.environ.get("UPDATE_SCHEMA_SNAPSHOT") == "1":
        SNAPSHOT.write_text(actual, encoding="utf-8", newline="\n")
    assert SNAPSHOT.exists(), "no snapshot yet: run UPDATE_SCHEMA_SNAPSHOT=1 make test-integration"
    expected = SNAPSHOT.read_text(encoding="utf-8")
    assert actual == expected, (
        "migrations changed the schema but database/schema_snapshot.txt was not updated; "
        "review the diff, then run UPDATE_SCHEMA_SNAPSHOT=1 make test-integration"
    )


def test_each_downgrade_restores_the_previous_schema_exactly(
    empty_database: URL, connect: Callable[[URL], Conn]
) -> None:
    revisions = _revisions_ascending(empty_database)
    with connect(empty_database) as conn:
        dumps: dict[str, str] = {"base": dump_schema(conn)}
    for revision in revisions:
        upgrade(empty_database, revision)
        with connect(empty_database) as conn:
            dumps[revision] = dump_schema(conn)
    assert len(set(dumps.values())) == len(dumps), "every revision must change the schema"

    previous = ["base", *revisions[:-1]]
    for revision, before in zip(reversed(revisions), reversed(previous), strict=True):
        downgrade(empty_database, "-1")
        with connect(empty_database) as conn:
            assert dump_schema(conn) == dumps[before], (
                f"downgrading {revision} did not restore the schema of {before}"
            )


def test_full_cycle_leaves_the_same_schema(
    empty_database: URL, connect: Callable[[URL], Conn]
) -> None:
    upgrade(empty_database)
    with connect(empty_database) as conn:
        first = dump_schema(conn)
    downgrade(empty_database, "base")
    upgrade(empty_database)
    with connect(empty_database) as conn:
        assert dump_schema(conn) == first


def test_snapshot_file_is_utf8_lf_and_nonempty() -> None:
    raw = Path(SNAPSHOT).read_bytes()
    assert raw and b"\r\n" not in raw
    raw.decode("utf-8")
