"""Instrument query rules and result types (P1-21). Pure: no I/O, no framework imports (D7)."""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass
from enum import Enum

_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9]{12}")
_MARKET_RE = re.compile(r"[A-Za-z]{2}")


class Confidence(Enum):
    HIGH = "high"  # exact identifier, ticker or company name
    MEDIUM = "medium"  # company-name prefix
    LOW = "low"

    @property
    def rank(self) -> int:
        """Smaller is stronger; used for ordering."""
        return _RANKS[self]

    @staticmethod
    def stronger(a: Confidence, b: Confidence) -> Confidence:
        return a if a.rank <= b.rank else b


_RANKS = {Confidence.HIGH: 0, Confidence.MEDIUM: 1, Confidence.LOW: 2}


@dataclass(frozen=True)
class InstrumentRecord:
    """One listing with its issuer, security and currently valid identifiers."""

    issuer_id: uuid.UUID
    security_id: uuid.UUID
    listing_id: uuid.UUID
    issuer_name: str
    ticker: str
    venue_mic: str
    currency: str
    isin: str | None
    figi: str | None


@dataclass(frozen=True)
class InstrumentMatch:
    record: InstrumentRecord
    confidence: Confidence


def normalize_query(raw: str) -> str:
    """Trim and collapse whitespace; a blank query is an error, never a match-everything."""
    if any(unicodedata.category(ch) == "Cc" for ch in raw if ch not in "\t\n\r"):
        raise ValueError("query must not contain control characters")
    query = " ".join(raw.split())
    if not query:
        raise ValueError("query must not be blank")
    return query


def normalize_market(raw: str) -> str:
    """A market is an ISO 3166-1 alpha-2 country code, e.g. ``US``."""
    market = raw.strip()
    if not _MARKET_RE.fullmatch(market):
        raise ValueError("market must be a two-letter country code")
    return market.upper()


def looks_like_identifier(query: str) -> bool:
    """ISIN and FIGI are both 12 alphanumeric characters."""
    return _IDENTIFIER_RE.fullmatch(query) is not None
