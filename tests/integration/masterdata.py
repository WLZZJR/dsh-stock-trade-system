"""Shared master-data builder for integration tests (rolled-back transaction per test)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import psycopg

from data_engine.seeding import apply_seeds
from data_engine.sources import get_source_id

Conn = psycopg.Connection[tuple[object, ...]]
FAR_FUTURE = date(9999, 12, 31)
LONG_AGO = datetime(2010, 1, 1, tzinfo=UTC)


def _scalar(db: Conn, query: str, params: tuple[object, ...] = ()) -> object:
    row = db.execute(query, params).fetchone()
    assert row is not None
    return row[0]


def _uuid(value: object) -> uuid.UUID:
    assert isinstance(value, uuid.UUID)
    return value


class Builder:
    """Creates master data inside the test's rolled-back transaction."""

    def __init__(self, db: Conn) -> None:
        self.db = db
        apply_seeds(db)  # currencies, venues XNYS/XNAS/XASE, manual_import source
        self.source_id = get_source_id(db, "manual_import")
        db.execute(
            "INSERT INTO venues (mic, name, country_code, timezone) "
            "VALUES ('XLON', 'London Stock Exchange', 'GB', 'Europe/London') "
            "ON CONFLICT DO NOTHING"
        )

    def issuer(self, legal_name: str, common_name: str | None = None) -> uuid.UUID:
        return _uuid(
            _scalar(
                self.db,
                "INSERT INTO issuers (legal_name, common_name) VALUES (%s, %s) RETURNING id",
                (legal_name, common_name),
            )
        )

    def security(self, issuer: uuid.UUID) -> uuid.UUID:
        return _uuid(
            _scalar(
                self.db,
                "INSERT INTO securities (issuer_id, security_type) "
                "VALUES (%s, 'common_stock') RETURNING id",
                (issuer,),
            )
        )

    def listing(
        self,
        security: uuid.UUID,
        ticker: str,
        mic: str = "XNAS",
        status: str = "active",
        valid_from: date = date(2000, 1, 1),
        valid_to: date = FAR_FUTURE,
        currency: str = "USD",
    ) -> uuid.UUID:
        return _uuid(
            _scalar(
                self.db,
                "INSERT INTO listings (security_id, venue_id, ticker, trading_currency, status, "
                "valid_from, valid_to) VALUES (%s, (SELECT id FROM venues WHERE mic = %s), "
                "%s, %s, %s, %s, %s) RETURNING id",
                (security, mic, ticker, currency, status, valid_from, valid_to),
            )
        )

    def identifier(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
        id_type: str,
        id_value: str,
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
    ) -> None:
        self.db.execute(
            "INSERT INTO identifiers (entity_type, entity_id, id_type, id_value, source_id, "
            "valid_from, valid_to) VALUES (%s, %s, %s, %s, %s, "
            "COALESCE(%s, '-infinity'::timestamptz), COALESCE(%s, 'infinity'::timestamptz))",
            (entity_type, entity_id, id_type, id_value, self.source_id, valid_from, valid_to),
        )

    def stock(
        self,
        name: str,
        ticker: str,
        mic: str = "XNAS",
        status: str = "active",
        valid_from: date = date(2000, 1, 1),
        valid_to: date = FAR_FUTURE,
        currency: str = "USD",
    ) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
        issuer = self.issuer(name)
        security = self.security(issuer)
        listing = self.listing(security, ticker, mic, status, valid_from, valid_to, currency)
        return issuer, security, listing
