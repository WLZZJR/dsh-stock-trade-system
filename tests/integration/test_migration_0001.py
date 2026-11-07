"""P1-10: migration 0001 — extensions, trg_forbid_mutation, currencies; up/down round trip."""

from __future__ import annotations

from collections.abc import Callable

import psycopg
import pytest
from dbtools import downgrade, upgrade
from sqlalchemy.engine import URL

pytestmark = pytest.mark.integration

Connect = Callable[[URL], "psycopg.Connection[tuple[object, ...]]"]


def _tables(conn: psycopg.Connection[tuple[object, ...]]) -> set[str]:
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    ).fetchall()
    return {str(r[0]) for r in rows}


def _extensions(conn: psycopg.Connection[tuple[object, ...]]) -> set[str]:
    rows = conn.execute("SELECT extname FROM pg_extension").fetchall()
    return {str(r[0]) for r in rows}


def _functions(conn: psycopg.Connection[tuple[object, ...]]) -> set[str]:
    rows = conn.execute(
        "SELECT proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'public'"
    ).fetchall()
    return {str(r[0]) for r in rows}


def test_upgrade_creates_extensions_function_and_currencies(
    empty_database: URL, connect: Connect
) -> None:
    upgrade(empty_database, "0001")
    with connect(empty_database) as conn:
        assert {"pgcrypto", "btree_gist"} <= _extensions(conn)
        assert "trg_forbid_mutation" in _functions(conn)
        assert "currencies" in _tables(conn)


def test_upgrade_downgrade_upgrade_round_trip(empty_database: URL, connect: Connect) -> None:
    upgrade(empty_database)
    downgrade(empty_database, "base")
    with connect(empty_database) as conn:
        assert _tables(conn) == {"alembic_version"}
        assert "trg_forbid_mutation" not in _functions(conn)
        assert not {"pgcrypto", "btree_gist"} & _extensions(conn)
    upgrade(empty_database)
    with connect(empty_database) as conn:
        assert "currencies" in _tables(conn)


def test_currencies_code_is_three_chars_and_unique(
    db: psycopg.Connection[tuple[object, ...]],
) -> None:
    db.execute("INSERT INTO currencies (code, name) VALUES ('ZZZ', 'Test currency')")
    row = db.execute("SELECT minor_unit FROM currencies WHERE code = 'ZZZ'").fetchone()
    assert row == (2,)  # default minor unit
    with pytest.raises(psycopg.errors.UniqueViolation), db.transaction():
        db.execute("INSERT INTO currencies (code, name) VALUES ('ZZZ', 'Duplicate')")
    with pytest.raises(psycopg.errors.StringDataRightTruncation), db.transaction():
        db.execute("INSERT INTO currencies (code, name) VALUES ('TOOLONG', 'Bad code')")


def test_forbid_mutation_function_raises_restrict_violation(
    db: psycopg.Connection[tuple[object, ...]],
) -> None:
    """The shared append-only trigger function must refuse with restrict_violation."""
    db.execute("CREATE TEMP TABLE append_only_probe (id int)")
    db.execute(
        "CREATE TRIGGER probe_append_only BEFORE UPDATE OR DELETE ON append_only_probe "
        "FOR EACH ROW EXECUTE FUNCTION trg_forbid_mutation()"
    )
    db.execute("INSERT INTO append_only_probe VALUES (1)")
    with pytest.raises(psycopg.errors.RestrictViolation, match="append-only"), db.transaction():
        db.execute("UPDATE append_only_probe SET id = 2")
    with pytest.raises(psycopg.errors.RestrictViolation, match="append-only"), db.transaction():
        db.execute("DELETE FROM append_only_probe")
