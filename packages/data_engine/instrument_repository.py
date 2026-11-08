"""PostgreSQL implementation of the instrument lookups used by disambiguation (P1-21).

Read-only. A listing is a candidate when its status is ``active`` or ``suspended`` and
``valid_from <= as_of < valid_to`` (ticker reuse after a delisting therefore never matches the
old security). Identifier validity is compared on whole days in UTC. Every value is a bound
parameter; the only text spliced into SQL is the constant fragments below.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

import psycopg

from domain.instruments import InstrumentRecord

_LOOKUP_ID_TYPES = ("isin", "figi", "composite_figi", "share_class_figi")

_LIVE_LISTING = """
    l.status IN ('active', 'suspended')
    AND l.valid_from <= %(as_of)s AND %(as_of)s < l.valid_to
    AND (%(market)s::text IS NULL OR v.country_code = %(market)s)
"""

_IDENTIFIER_VALID_AT = """
    (x.valid_from AT TIME ZONE 'UTC')::date <= %(as_of)s
    AND %(as_of)s < (x.valid_to AT TIME ZONE 'UTC')::date
"""

_BY_TICKER = f"""
    SELECT l.id FROM listings l JOIN venues v ON v.id = l.venue_id
    WHERE upper(l.ticker) = %(ticker)s AND {_LIVE_LISTING}
    ORDER BY l.ticker, v.mic, l.id
"""  # noqa: S608 - fragments are module constants, values are bound

_BY_IDENTIFIER = f"""
    SELECT l.id, l.ticker, v.mic
    FROM identifiers x
    JOIN listings l ON (
        (x.entity_type = 'listing' AND l.id = x.entity_id)
        OR (x.entity_type = 'security' AND l.security_id = x.entity_id)
        OR (x.entity_type = 'issuer' AND EXISTS (
            SELECT 1 FROM securities s WHERE s.id = l.security_id AND s.issuer_id = x.entity_id))
    )
    JOIN venues v ON v.id = l.venue_id
    WHERE x.id_type = ANY(%(id_types)s) AND x.id_value = %(value)s
      AND {_IDENTIFIER_VALID_AT} AND {_LIVE_LISTING}
    GROUP BY l.id, l.ticker, v.mic
    ORDER BY l.ticker, v.mic, l.id
"""  # noqa: S608 - fragments are module constants, values are bound

_NAME_EXACT = "lower(i.legal_name) = lower(%(name)s) OR lower(i.common_name) = lower(%(name)s)"
_NAME_PREFIX = (
    "i.legal_name ILIKE %(pattern)s ESCAPE '\\' OR i.common_name ILIKE %(pattern)s ESCAPE '\\'"
)


def _by_name(condition: str) -> str:
    return f"""
        SELECT l.id FROM listings l
        JOIN securities s ON s.id = l.security_id
        JOIN issuers i ON i.id = s.issuer_id
        JOIN venues v ON v.id = l.venue_id
        WHERE ({condition}) AND {_LIVE_LISTING}
        ORDER BY l.ticker, v.mic, l.id
        LIMIT %(limit)s
    """  # noqa: S608 - fragments are module constants, values are bound


_RECORDS = f"""
    SELECT l.id, s.issuer_id, s.id, i.legal_name, l.ticker, v.mic, l.trading_currency,
      (SELECT x.id_value FROM identifiers x
        WHERE x.entity_type = 'security' AND x.entity_id = s.id AND x.id_type = 'isin'
          AND {_IDENTIFIER_VALID_AT}
        ORDER BY x.valid_from DESC LIMIT 1),
      (SELECT x.id_value FROM identifiers x
        WHERE x.entity_type = 'listing' AND x.entity_id = l.id AND x.id_type = 'figi'
          AND {_IDENTIFIER_VALID_AT}
        ORDER BY x.valid_from DESC LIMIT 1)
    FROM listings l
    JOIN securities s ON s.id = l.security_id
    JOIN issuers i ON i.id = s.issuer_id
    JOIN venues v ON v.id = l.venue_id
    WHERE l.id = ANY(%(ids)s)
"""  # noqa: S608 - fragments are module constants, values are bound


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class PgInstrumentRepository:
    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn

    def _ids(self, query: str, params: Mapping[str, object]) -> list[uuid.UUID]:
        return [row[0] for row in self._conn.execute(query, params).fetchall()]

    def listing_ids_by_ticker(
        self, ticker: str, *, market: str | None, as_of: date
    ) -> list[uuid.UUID]:
        return self._ids(_BY_TICKER, {"ticker": ticker.upper(), "market": market, "as_of": as_of})

    def listing_ids_by_identifier(
        self, value: str, *, market: str | None, as_of: date
    ) -> list[uuid.UUID]:
        params = {
            "value": value,
            "id_types": list(_LOOKUP_ID_TYPES),
            "market": market,
            "as_of": as_of,
        }
        return self._ids(_BY_IDENTIFIER, params)

    def listing_ids_by_name(
        self, name: str, *, prefix: bool, market: str | None, as_of: date, limit: int
    ) -> list[uuid.UUID]:
        params: dict[str, object] = {"market": market, "as_of": as_of, "limit": limit}
        if prefix:
            params["pattern"] = _escape_like(name) + "%"
            return self._ids(_by_name(_NAME_PREFIX), params)
        params["name"] = name
        return self._ids(_by_name(_NAME_EXACT), params)

    def records(self, listing_ids: Sequence[uuid.UUID], *, as_of: date) -> list[InstrumentRecord]:
        if not listing_ids:
            return []
        rows = self._conn.execute(_RECORDS, {"ids": list(listing_ids), "as_of": as_of}).fetchall()
        return [
            InstrumentRecord(
                listing_id=row[0],
                issuer_id=row[1],
                security_id=row[2],
                issuer_name=row[3],
                ticker=row[4],
                venue_mic=row[5],
                currency=row[6],
                isin=row[7],
                figi=row[8],
            )
            for row in rows
        ]
