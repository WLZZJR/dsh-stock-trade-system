"""Instrument disambiguation (P1-21): find candidate listings, never choose one for the user.

Strategies, all exact or prefix, none fuzzy:

* a 12-character alphanumeric query is looked up as an ISIN / FIGI           -> high
* a single-word query is looked up as a ticker                               -> high
* the query is matched against issuer names, exactly and by prefix           -> high / medium

A listing found by several strategies appears once with its strongest confidence. More than
one candidate always means ``requires_user_selection``. Without ``market`` every market is
searched; no default market is assumed.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from domain.instruments import (
    Confidence,
    InstrumentMatch,
    InstrumentRecord,
    looks_like_identifier,
    normalize_market,
    normalize_query,
)

MAX_MATCHES = 20
_MIN_NAME_PREFIX = 2


class InstrumentRepository(Protocol):
    """Read-only lookups; implemented over PostgreSQL in ``data_engine``."""

    def listing_ids_by_identifier(
        self, value: str, *, market: str | None, as_of: date
    ) -> list[uuid.UUID]: ...

    def listing_ids_by_ticker(
        self, ticker: str, *, market: str | None, as_of: date
    ) -> list[uuid.UUID]: ...

    def listing_ids_by_name(
        self, name: str, *, prefix: bool, market: str | None, as_of: date, limit: int
    ) -> list[uuid.UUID]: ...

    def records(
        self, listing_ids: Sequence[uuid.UUID], *, as_of: date
    ) -> list[InstrumentRecord]: ...


@dataclass(frozen=True)
class ResolveResult:
    matches: tuple[InstrumentMatch, ...]
    requires_user_selection: bool
    truncated: bool


def resolve_instrument(
    repo: InstrumentRepository, query: str, market: str | None, *, as_of: date
) -> ResolveResult:
    """Raises ``ValueError`` for a blank query or a malformed market."""
    text = normalize_query(query)
    country = normalize_market(market) if market is not None else None

    found: dict[uuid.UUID, Confidence] = {}

    def add(ids: Sequence[uuid.UUID], confidence: Confidence) -> None:
        for listing_id in ids:
            known = found.get(listing_id)
            found[listing_id] = (
                confidence if known is None else Confidence.stronger(known, confidence)
            )

    single_word = " " not in text
    if looks_like_identifier(text):
        add(
            repo.listing_ids_by_identifier(text.upper(), market=country, as_of=as_of),
            Confidence.HIGH,
        )
    if single_word:
        add(repo.listing_ids_by_ticker(text.upper(), market=country, as_of=as_of), Confidence.HIGH)
    limit = MAX_MATCHES + 1
    add(
        repo.listing_ids_by_name(text, prefix=False, market=country, as_of=as_of, limit=limit),
        Confidence.HIGH,
    )
    if len(text) >= _MIN_NAME_PREFIX:
        add(
            repo.listing_ids_by_name(text, prefix=True, market=country, as_of=as_of, limit=limit),
            Confidence.MEDIUM,
        )

    matches = sorted(
        (
            InstrumentMatch(record, found[record.listing_id])
            for record in repo.records(list(found), as_of=as_of)
        ),
        key=lambda m: (
            m.confidence.rank,
            m.record.ticker,
            m.record.venue_mic,
            str(m.record.listing_id),
        ),
    )
    return ResolveResult(
        matches=tuple(matches[:MAX_MATCHES]),
        requires_user_selection=len(matches) > 1,
        truncated=len(matches) > MAX_MATCHES,
    )


def get_instrument(
    repo: InstrumentRepository, listing_id: uuid.UUID, *, as_of: date
) -> InstrumentRecord | None:
    """Detail for one listing by id; works for any existing listing, including delisted ones."""
    records = repo.records([listing_id], as_of=as_of)
    return records[0] if records else None
