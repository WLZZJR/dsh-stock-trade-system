"""P1-12: migration 0003 — issuers, securities, venues, listings (GIST exclusion on ticker)."""

from __future__ import annotations

from datetime import date

import psycopg
import pytest

pytestmark = pytest.mark.integration

Conn = psycopg.Connection[tuple[object, ...]]
FAR_FUTURE = date(9999, 12, 31)


def _scalar(db: Conn, query: str, params: tuple[object, ...] = ()) -> object:
    row = db.execute(query, params).fetchone()
    assert row is not None
    return row[0]


def _usd(db: Conn) -> None:
    db.execute(
        "INSERT INTO currencies (code, name) VALUES ('USD', 'US Dollar') ON CONFLICT DO NOTHING"
    )


def _security(db: Conn) -> object:
    _usd(db)
    issuer = _scalar(db, "INSERT INTO issuers (legal_name) VALUES ('Acme Corp') RETURNING id")
    return _scalar(
        db,
        "INSERT INTO securities (issuer_id, security_type) "
        "VALUES (%s, 'common_stock') RETURNING id",
        (issuer,),
    )


def _venue(db: Conn, mic: str) -> object:
    return _scalar(
        db,
        "INSERT INTO venues (mic, name, country_code, timezone) "
        "VALUES (%s, %s, 'US', 'America/New_York') RETURNING id",
        (mic, f"Venue {mic}"),
    )


def _listing(
    db: Conn,
    security: object,
    venue: object,
    ticker: str,
    valid_from: date,
    valid_to: date = FAR_FUTURE,
) -> object:
    return _scalar(
        db,
        "INSERT INTO listings "
        "(security_id, venue_id, ticker, trading_currency, valid_from, valid_to) "
        "VALUES (%s, %s, %s, 'USD', %s, %s) RETURNING id",
        (security, venue, ticker, valid_from, valid_to),
    )


def test_same_ticker_different_venue_ok(db: Conn) -> None:
    sec = _security(db)
    nyse, nasdaq = _venue(db, "XNYS"), _venue(db, "XNAS")
    _listing(db, sec, nyse, "ABC", date(2020, 1, 1))
    _listing(db, sec, nasdaq, "ABC", date(2020, 1, 1))
    assert _scalar(db, "SELECT count(*) FROM listings WHERE ticker = 'ABC'") == 2


def test_same_venue_overlapping_ticker_rejected(db: Conn) -> None:
    sec = _security(db)
    venue = _venue(db, "XNYS")
    _listing(db, sec, venue, "ABC", date(2020, 1, 1), date(2022, 1, 1))
    with pytest.raises(psycopg.errors.ExclusionViolation), db.transaction():
        _listing(db, sec, venue, "ABC", date(2021, 6, 1))


def test_same_venue_same_start_date_rejected(db: Conn) -> None:
    sec = _security(db)
    venue = _venue(db, "XNYS")
    _listing(db, sec, venue, "ABC", date(2020, 1, 1))
    with pytest.raises(psycopg.errors.ExclusionViolation), db.transaction():
        _listing(db, sec, venue, "ABC", date(2020, 1, 1), date(2021, 1, 1))


def test_ticker_reuse_after_delisting_ok(db: Conn) -> None:
    """Ranges are half-open [valid_from, valid_to): touching ranges do not overlap."""
    old_sec = _security(db)
    new_sec = _scalar(
        db,
        "INSERT INTO securities (issuer_id, security_type) "
        "VALUES ((SELECT issuer_id FROM securities WHERE id = %s), 'common_stock') RETURNING id",
        (old_sec,),
    )
    venue = _venue(db, "XNYS")
    _listing(db, old_sec, venue, "ABC", date(2015, 1, 1), date(2020, 1, 1))
    _listing(db, new_sec, venue, "ABC", date(2020, 1, 1))
    assert _scalar(db, "SELECT count(*) FROM listings WHERE ticker = 'ABC'") == 2


def test_listing_valid_range_must_be_increasing(db: Conn) -> None:
    sec = _security(db)
    venue = _venue(db, "XNYS")
    with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
        _listing(db, sec, venue, "ABC", date(2020, 1, 1), date(2020, 1, 1))
    with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
        _listing(db, sec, venue, "ABC", date(2021, 1, 1), date(2020, 1, 1))


def test_listing_status_checked_and_defaults(db: Conn) -> None:
    sec = _security(db)
    venue = _venue(db, "XNYS")
    listing = _listing(db, sec, venue, "ABC", date(2020, 1, 1))
    row = db.execute("SELECT status, valid_to FROM listings WHERE id = %s", (listing,)).fetchone()
    assert row == ("active", FAR_FUTURE)
    with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
        db.execute("UPDATE listings SET status = 'halted' WHERE id = %s", (listing,))


def test_listing_requires_known_currency_security_and_venue(db: Conn) -> None:
    sec = _security(db)
    venue = _venue(db, "XNYS")
    with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
        db.execute(
            "INSERT INTO listings (security_id, venue_id, ticker, trading_currency, valid_from) "
            "VALUES (%s, %s, 'ABC', 'XXX', '2020-01-01')",
            (sec, venue),
        )
    with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
        _listing(db, sec, "00000000-0000-0000-0000-000000000000", "ABC", date(2020, 1, 1))


def test_master_data_deletes_are_restricted(db: Conn) -> None:
    sec = _security(db)
    venue = _venue(db, "XNYS")
    _listing(db, sec, venue, "ABC", date(2020, 1, 1))
    issuer = _scalar(db, "SELECT issuer_id FROM securities WHERE id = %s", (sec,))
    for table, key in (("securities", sec), ("venues", venue), ("issuers", issuer)):
        with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
            db.execute(f"DELETE FROM {table} WHERE id = %s", (key,))  # noqa: S608


def test_venue_mic_is_unique(db: Conn) -> None:
    _venue(db, "XNYS")
    with pytest.raises(psycopg.errors.UniqueViolation), db.transaction():
        _venue(db, "XNYS")


def test_securities_nominal_currency_must_exist(db: Conn) -> None:
    issuer = _scalar(db, "INSERT INTO issuers (legal_name) VALUES ('Acme') RETURNING id")
    with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
        db.execute(
            "INSERT INTO securities (issuer_id, security_type, nominal_currency) "
            "VALUES (%s, 'adr', 'XXX')",
            (issuer,),
        )
