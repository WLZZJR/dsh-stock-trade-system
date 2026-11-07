"""P1-17 (+ migration 0008): reference-data seeds are complete, correct and idempotent."""

from __future__ import annotations

import psycopg
import pytest

from data_engine.seeding import apply_seeds
from data_engine.sources import get_source_id

pytestmark = pytest.mark.integration

Conn = psycopg.Connection[tuple[object, ...]]


def _count(db: Conn, table: str) -> int:
    row = db.execute(f"SELECT count(*) FROM {table}").fetchone()  # noqa: S608
    assert row is not None
    assert isinstance(row[0], int)
    return row[0]


def _snapshot_counts(db: Conn) -> dict[str, int]:
    tables = ("currencies", "countries", "venues", "providers", "data_sources")
    return {t: _count(db, t) for t in tables}


def test_seeding_is_idempotent(db: Conn) -> None:
    apply_seeds(db)
    first = _snapshot_counts(db)
    assert all(n > 0 for n in first.values())
    apply_seeds(db)
    apply_seeds(db)
    assert _snapshot_counts(db) == first


def test_currencies_follow_iso_4217_minor_units(db: Conn) -> None:
    apply_seeds(db)
    rows = {str(r[0]): r[1] for r in db.execute("SELECT code, minor_unit FROM currencies")}
    assert len(rows) > 150
    assert rows["USD"] == 2
    assert rows["EUR"] == 2
    assert rows["JPY"] == 0
    assert rows["KRW"] == 0
    assert rows["BHD"] == 3
    assert rows["CLF"] == 4
    assert all(len(code) == 3 and code.isupper() for code in rows)
    assert "XXX" not in rows  # codes without a numeric minor unit are not real currencies


def test_countries_cover_iso_3166_1(db: Conn) -> None:
    apply_seeds(db)
    assert _count(db, "countries") == 249
    row = db.execute(
        "SELECT alpha3, numeric_code, name FROM countries WHERE code = 'US'"
    ).fetchone()
    assert row == ("USA", "840", "United States")
    row = db.execute("SELECT name FROM countries WHERE code = 'CI'").fetchone()
    assert row == ("Côte d'Ivoire",)  # apostrophes survive seed quoting


def test_us_venues_are_seeded_with_mic_and_timezone(db: Conn) -> None:
    apply_seeds(db)
    rows = db.execute(
        "SELECT mic, country_code, timezone FROM venues "
        "WHERE mic IN ('XNYS', 'XNAS', 'XASE') ORDER BY mic"
    ).fetchall()
    assert rows == [
        ("XASE", "US", "America/New_York"),
        ("XNAS", "US", "America/New_York"),
        ("XNYS", "US", "America/New_York"),
    ]


def test_system_sources_exist_and_manual_import_yields_a_valid_source_id(db: Conn) -> None:
    apply_seeds(db)
    names = {r[0] for r in db.execute("SELECT name FROM providers").fetchall()}
    assert {"system_mock", "manual_import"} <= names
    source_id = get_source_id(db, "manual_import")
    # The id must satisfy the NOT NULL foreign key that facts and identifiers rely on.
    issuer = db.execute("INSERT INTO issuers (legal_name) VALUES ('Acme') RETURNING id").fetchone()
    assert issuer is not None
    db.execute(
        "INSERT INTO identifiers (entity_type, entity_id, id_type, id_value, source_id) "
        "VALUES ('issuer', %s, 'lei', 'SEEDTEST', %s)",
        (issuer[0], source_id),
    )
    assert get_source_id(db, "system_mock") != source_id


def test_get_source_id_unknown_provider_fails_clearly(db: Conn) -> None:
    apply_seeds(db)
    with pytest.raises(LookupError, match="no_such_provider"):
        get_source_id(db, "no_such_provider")


def test_get_source_id_before_seeding_fails_clearly(db: Conn) -> None:
    with pytest.raises(LookupError, match="manual_import"):
        get_source_id(db, "manual_import")


def test_countries_table_constraints(db: Conn) -> None:
    db.execute(
        "INSERT INTO countries (code, alpha3, numeric_code, name) VALUES ('ZZ','ZZZ','999','Z')"
    )
    with pytest.raises(psycopg.errors.UniqueViolation), db.transaction():
        db.execute(
            "INSERT INTO countries (code, alpha3, numeric_code, name) VALUES ('YY','ZZZ','998','Y')"
        )
    with pytest.raises(psycopg.errors.StringDataRightTruncation), db.transaction():
        db.execute(
            "INSERT INTO countries (code, alpha3, numeric_code, name) "
            "VALUES ('XXX','XXX','997','X')"
        )
