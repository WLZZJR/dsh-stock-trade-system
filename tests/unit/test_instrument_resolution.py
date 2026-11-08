"""P1-21: disambiguation never chooses for the user; it ranks candidates deterministically."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

import pytest

from application.instrument_resolution import MAX_MATCHES, resolve_instrument
from domain.instruments import Confidence, InstrumentRecord

AS_OF = date(2026, 11, 8)


def _record(
    ticker: str,
    mic: str = "XNAS",
    name: str = "Acme Corp",
    isin: str | None = None,
    figi: str | None = None,
    country: str = "US",
) -> tuple[InstrumentRecord, str]:
    record = InstrumentRecord(
        issuer_id=uuid.uuid4(),
        security_id=uuid.uuid4(),
        listing_id=uuid.uuid4(),
        issuer_name=name,
        ticker=ticker,
        venue_mic=mic,
        currency="USD",
        isin=isin,
        figi=figi,
    )
    return record, country


@dataclass
class FakeRepo:
    rows: list[tuple[InstrumentRecord, str]] = field(default_factory=list)
    calls: list[tuple[str, str, str | None]] = field(default_factory=list)

    def _in_market(self, market: str | None) -> list[InstrumentRecord]:
        return [r for r, c in self.rows if market is None or c == market]

    def listing_ids_by_identifier(
        self, value: str, *, market: str | None, as_of: date
    ) -> list[uuid.UUID]:
        self.calls.append(("identifier", value, market))
        return [r.listing_id for r in self._in_market(market) if value in (r.isin, r.figi)]

    def listing_ids_by_ticker(
        self, ticker: str, *, market: str | None, as_of: date
    ) -> list[uuid.UUID]:
        self.calls.append(("ticker", ticker, market))
        return [r.listing_id for r in self._in_market(market) if r.ticker == ticker]

    def listing_ids_by_name(
        self, name: str, *, prefix: bool, market: str | None, as_of: date, limit: int
    ) -> list[uuid.UUID]:
        self.calls.append(("name_prefix" if prefix else "name_exact", name, market))
        lowered = name.lower()
        hits = [
            r.listing_id
            for r in self._in_market(market)
            if (
                r.issuer_name.lower().startswith(lowered)
                if prefix
                else r.issuer_name.lower() == lowered
            )
        ]
        return hits[:limit]

    def records(self, listing_ids: Sequence[uuid.UUID], *, as_of: date) -> list[InstrumentRecord]:
        wanted = set(listing_ids)
        return [r for r, _ in self.rows if r.listing_id in wanted]


def test_ambiguous_ticker_requires_selection() -> None:
    nasdaq, _ = _record("ABC", mic="XNAS", name="Alpha Beta Corp")
    nyse, _ = _record("ABC", mic="XNYS", name="A B C Holdings")
    result = resolve_instrument(FakeRepo([(nasdaq, "US"), (nyse, "US")]), "ABC", None, as_of=AS_OF)
    assert result.requires_user_selection is True
    assert {m.record.venue_mic for m in result.matches} == {"XNAS", "XNYS"}


def test_unique_ticker_does_not_require_selection() -> None:
    only = _record("MSFT", name="Microsoft Corporation")
    result = resolve_instrument(FakeRepo([only]), "msft", "us", as_of=AS_OF)
    assert result.requires_user_selection is False
    assert [m.record.ticker for m in result.matches] == ["MSFT"]
    assert result.matches[0].confidence is Confidence.HIGH


def test_resolve_by_isin() -> None:
    target = _record("MSFT", isin="US5949181045", name="Microsoft Corporation")
    other = _record("AAPL", isin="US0378331005", name="Apple Inc")
    result = resolve_instrument(FakeRepo([target, other]), "us5949181045", None, as_of=AS_OF)
    assert [m.record.ticker for m in result.matches] == ["MSFT"]
    assert result.requires_user_selection is False
    assert result.matches[0].confidence is Confidence.HIGH


def test_resolve_by_figi() -> None:
    target = _record("MSFT", figi="BBG000BPH459")
    result = resolve_instrument(FakeRepo([target]), "BBG000BPH459", None, as_of=AS_OF)
    assert [m.record.ticker for m in result.matches] == ["MSFT"]


def test_exact_company_name_is_high_and_prefix_is_medium() -> None:
    exact = _record("APLE", name="Apple")
    prefix = _record("AAPL", name="Apple Inc")
    result = resolve_instrument(FakeRepo([exact, prefix]), "apple", None, as_of=AS_OF)
    by_ticker = {m.record.ticker: m.confidence for m in result.matches}
    assert by_ticker == {"APLE": Confidence.HIGH, "AAPL": Confidence.MEDIUM}
    assert result.requires_user_selection is True  # two candidates: never pick one silently
    assert [m.record.ticker for m in result.matches] == ["APLE", "AAPL"]  # strongest first


def test_same_listing_found_by_several_strategies_appears_once_with_best_confidence() -> None:
    both = _record("ABC", name="ABC Corporation")  # ticker exact AND name prefix
    result = resolve_instrument(FakeRepo([both]), "ABC", None, as_of=AS_OF)
    assert len(result.matches) == 1
    assert result.matches[0].confidence is Confidence.HIGH
    assert result.requires_user_selection is False


def test_no_match_returns_empty_without_selection() -> None:
    result = resolve_instrument(FakeRepo([_record("MSFT")]), "NOPE", None, as_of=AS_OF)
    assert result.matches == ()
    assert result.requires_user_selection is False
    assert result.truncated is False


def test_market_filter_is_passed_to_every_lookup_and_normalised() -> None:
    repo = FakeRepo([_record("ABC")])
    resolve_instrument(repo, "ABC", "us", as_of=AS_OF)
    assert repo.calls
    assert all(market == "US" for _, _, market in repo.calls)


def test_missing_market_searches_all_markets_without_defaulting() -> None:
    us = _record("ABC", country="US")
    gb = _record("ABC", mic="XLON", country="GB")
    repo = FakeRepo([us, gb])
    result = resolve_instrument(repo, "ABC", None, as_of=AS_OF)
    assert all(market is None for _, _, market in repo.calls)
    assert len(result.matches) == 2
    assert result.requires_user_selection is True


def test_ticker_lookup_is_skipped_for_multi_word_queries() -> None:
    repo = FakeRepo([_record("MSFT", name="Microsoft Corporation")])
    resolve_instrument(repo, "Microsoft Corporation", None, as_of=AS_OF)
    assert "ticker" not in {kind for kind, _, _ in repo.calls}
    assert "identifier" not in {kind for kind, _, _ in repo.calls}


def test_ordering_is_deterministic_regardless_of_repository_order() -> None:
    rows = [_record("ABC", mic=mic, name="ABC Corp") for mic in ("XNYS", "XASE", "XNAS")]
    first = resolve_instrument(FakeRepo(rows), "ABC", None, as_of=AS_OF)
    second = resolve_instrument(FakeRepo(list(reversed(rows))), "ABC", None, as_of=AS_OF)
    assert [m.record.venue_mic for m in first.matches] == ["XASE", "XNAS", "XNYS"]
    assert [m.record.venue_mic for m in second.matches] == ["XASE", "XNAS", "XNYS"]


def test_results_beyond_the_cap_are_flagged_as_truncated() -> None:
    rows = [_record(f"T{i:03d}", name="Common Name Inc") for i in range(MAX_MATCHES + 5)]
    result = resolve_instrument(FakeRepo(rows), "Common Name", None, as_of=AS_OF)
    assert len(result.matches) == MAX_MATCHES
    assert result.truncated is True
    assert result.requires_user_selection is True


def test_blank_query_is_rejected() -> None:
    with pytest.raises(ValueError, match="blank"):
        resolve_instrument(FakeRepo(), "   ", None, as_of=AS_OF)


def test_invalid_market_is_rejected() -> None:
    with pytest.raises(ValueError, match="market"):
        resolve_instrument(FakeRepo(), "ABC", "USA", as_of=AS_OF)


def test_get_instrument_returns_the_record_or_none() -> None:
    from application.instrument_resolution import get_instrument

    record, _ = _record("MSFT")
    repo = FakeRepo([(record, "US")])
    assert get_instrument(repo, record.listing_id, as_of=AS_OF) == record
    assert get_instrument(repo, uuid.uuid4(), as_of=AS_OF) is None
