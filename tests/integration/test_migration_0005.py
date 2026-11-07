"""P1-14: migration 0005 — identifiers (GIST exclusion, entity triggers, delete protection)."""

from __future__ import annotations

import psycopg
import pytest

pytestmark = pytest.mark.integration

Conn = psycopg.Connection[tuple[object, ...]]
MISSING = "00000000-0000-0000-0000-000000000000"


def _scalar(db: Conn, query: str, params: tuple[object, ...] = ()) -> object:
    row = db.execute(query, params).fetchone()
    assert row is not None
    return row[0]


def _source(db: Conn) -> object:
    return _scalar(
        db,
        "INSERT INTO data_sources (source_name, source_type) "
        "VALUES ('test', 'manual') RETURNING id",
    )


def _issuer(db: Conn, name: str = "Acme Corp") -> object:
    return _scalar(db, "INSERT INTO issuers (legal_name) VALUES (%s) RETURNING id", (name,))


def _identify(
    db: Conn,
    source: object,
    entity_id: object,
    value: str = "US0378331005",
    *,
    entity_type: str = "issuer",
    id_type: str = "isin",
    valid_from: str = "-infinity",
    valid_to: str = "infinity",
) -> object:
    return _scalar(
        db,
        "INSERT INTO identifiers "
        "(entity_type, entity_id, id_type, id_value, source_id, valid_from, valid_to) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (entity_type, entity_id, id_type, value, source, valid_from, valid_to),
    )


def test_identifier_overlap_rejected(db: Conn) -> None:
    src = _source(db)
    first, second = _issuer(db), _issuer(db, "Other Corp")
    _identify(db, src, first, valid_from="2020-01-01", valid_to="2022-01-01")
    with pytest.raises(psycopg.errors.ExclusionViolation), db.transaction():
        _identify(db, src, second, valid_from="2021-06-01")


def test_identifier_open_ended_defaults_overlap_any_period(db: Conn) -> None:
    src = _source(db)
    first, second = _issuer(db), _issuer(db, "Other Corp")
    _identify(db, src, first)  # defaults: -infinity .. infinity
    with pytest.raises(psycopg.errors.ExclusionViolation), db.transaction():
        _identify(db, src, second, valid_from="2030-01-01", valid_to="2031-01-01")


def test_identifier_same_value_different_period_ok(db: Conn) -> None:
    """Half-open ranges: the value may move to another entity when the previous period ends."""
    src = _source(db)
    first, second = _issuer(db), _issuer(db, "Other Corp")
    _identify(db, src, first, valid_from="-infinity", valid_to="2022-01-01")
    _identify(db, src, second, valid_from="2022-01-01", valid_to="infinity")
    assert _scalar(db, "SELECT count(*) FROM identifiers WHERE id_value = 'US0378331005'") == 2


def test_infinite_bounds_round_trip(db: Conn) -> None:
    """Plan risk: -infinity / infinity must survive a write/read cycle unchanged."""
    src = _source(db)
    _identify(db, src, _issuer(db))
    row = db.execute(
        "SELECT valid_from = '-infinity'::timestamptz, valid_to = 'infinity'::timestamptz, "
        "isfinite(valid_from), isfinite(valid_to) FROM identifiers"
    ).fetchone()
    assert row == (True, True, False, False)


def test_same_value_for_different_entity_types_is_allowed(db: Conn) -> None:
    src = _source(db)
    issuer = _issuer(db)
    security = _scalar(
        db,
        "INSERT INTO securities (issuer_id, security_type) "
        "VALUES (%s, 'common_stock') RETURNING id",
        (issuer,),
    )
    _identify(db, src, issuer, "BBG000B9XRY4", entity_type="issuer", id_type="figi")
    _identify(db, src, security, "BBG000B9XRY4", entity_type="security", id_type="figi")


def test_identifier_nonexistent_entity_rejected(db: Conn) -> None:
    src = _source(db)
    with (
        pytest.raises(psycopg.errors.ForeignKeyViolation, match="does not exist"),
        db.transaction(),
    ):
        _identify(db, src, MISSING)
    for entity_type in ("security", "listing", "venue"):
        with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
            _identify(db, src, MISSING, entity_type=entity_type)


def test_identifier_update_to_missing_entity_rejected(db: Conn) -> None:
    src = _source(db)
    issuer = _issuer(db)
    ident = _identify(db, src, issuer)
    with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
        db.execute("UPDATE identifiers SET entity_id = %s WHERE id = %s", (MISSING, ident))
    assert _scalar(db, "SELECT entity_id FROM identifiers WHERE id = %s", (ident,)) == issuer


def test_delete_identified_entity_rejected(db: Conn) -> None:
    """Identified master data cannot be deleted (ADR-0016), for each entity type."""
    src = _source(db)
    guard = pytest.raises(psycopg.errors.ForeignKeyViolation, match="referenced by identifiers")
    for entity_type, table, id_type in (
        ("issuer", "issuers", "lei"),
        ("security", "securities", "isin"),
        ("venue", "venues", "local_code"),
        ("listing", "listings", "figi"),
    ):
        entity = _lone_entity(db, entity_type)
        _identify(db, src, entity, "LONE", entity_type=entity_type, id_type=id_type)
        with guard, db.transaction():
            db.execute(f"DELETE FROM {table} WHERE id = %s", (entity,))  # noqa: S608
        assert _scalar(db, f"SELECT count(*) FROM {table} WHERE id = %s", (entity,)) == 1  # noqa: S608


def _lone_entity(db: Conn, entity_type: str) -> object:
    """An entity with no dependants, so only the identifier guard can block its deletion."""
    if entity_type == "venue":
        return _scalar(
            db,
            "INSERT INTO venues (mic, name, timezone) VALUES ('XASE', 'AMEX', 'UTC') RETURNING id",
        )
    issuer = _issuer(db, "Lone Corp")
    if entity_type == "issuer":
        return issuer
    security = _scalar(
        db,
        "INSERT INTO securities (issuer_id, security_type) "
        "VALUES (%s, 'common_stock') RETURNING id",
        (issuer,),
    )
    if entity_type == "security":
        return security
    db.execute(
        "INSERT INTO currencies (code, name) VALUES ('USD', 'US Dollar') ON CONFLICT DO NOTHING"
    )
    venue = _scalar(
        db, "INSERT INTO venues (mic, name, timezone) VALUES ('XNYS', 'NYSE', 'UTC') RETURNING id"
    )
    return _scalar(
        db,
        "INSERT INTO listings (security_id, venue_id, ticker, trading_currency, valid_from) "
        "VALUES (%s, %s, 'ABC', 'USD', '2020-01-01') RETURNING id",
        (security, venue),
    )


def test_deleting_entity_without_identifiers_is_allowed(db: Conn) -> None:
    issuer = _issuer(db)
    db.execute("DELETE FROM issuers WHERE id = %s", (issuer,))
    assert _scalar(db, "SELECT count(*) FROM issuers") == 0


def test_identifier_type_checks_and_range_check(db: Conn) -> None:
    src = _source(db)
    issuer = _issuer(db)
    with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
        _identify(db, src, issuer, entity_type="portfolio")
    with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
        _identify(db, src, issuer, id_type="passport")
    with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
        _identify(db, src, issuer, valid_from="2022-01-01", valid_to="2022-01-01")


def test_identifier_requires_existing_source(db: Conn) -> None:
    issuer = _issuer(db)
    with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
        _identify(db, MISSING, issuer)


def test_lookup_indexes_exist(db: Conn) -> None:
    rows = db.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'identifiers'").fetchall()
    names = {r[0] for r in rows}
    assert {"idx_identifiers_lookup", "idx_identifiers_entity"} <= names
