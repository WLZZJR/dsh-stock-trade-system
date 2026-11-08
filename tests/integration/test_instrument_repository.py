"""P1-21: PgInstrumentRepository against real PostgreSQL 16 (validity windows, market, LIKE)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import psycopg
import pytest
from masterdata import LONG_AGO, Builder

from application.instrument_resolution import resolve_instrument
from data_engine.instrument_repository import PgInstrumentRepository

pytestmark = pytest.mark.integration

Conn = psycopg.Connection[tuple[object, ...]]
AS_OF = date(2026, 11, 8)


@pytest.fixture
def build(db: Conn) -> Builder:
    return Builder(db)


@pytest.fixture
def repo(db: Conn, build: Builder) -> PgInstrumentRepository:  # build first: data must exist
    return PgInstrumentRepository(db)


# --- ticker ------------------------------------------------------------------------------


def test_ticker_lookup_is_case_insensitive_and_exact(
    build: Builder, repo: PgInstrumentRepository
) -> None:
    _, _, msft = build.stock("Microsoft Corporation", "MSFT")
    build.stock("Microsoft Holdings", "MSFTX")
    assert repo.listing_ids_by_ticker("MSFT", market=None, as_of=AS_OF) == [msft]
    assert repo.listing_ids_by_ticker("msft", market=None, as_of=AS_OF) == [msft]


def test_ticker_lookup_respects_listing_validity_and_status(
    build: Builder, repo: PgInstrumentRepository
) -> None:
    _, _, current = build.stock("New Co", "ABC", valid_from=date(2020, 1, 1))
    build.stock("Old Co", "ABC", mic="XNYS", valid_to=date(2020, 1, 1))
    build.stock("Future Co", "ABC", mic="XASE", valid_from=date(2030, 1, 1))
    build.stock("Gone Co", "ABC", mic="XLON", status="delisted", currency="GBP")
    assert repo.listing_ids_by_ticker("ABC", market=None, as_of=AS_OF) == [current]


def test_suspended_listings_are_still_candidates(
    build: Builder, repo: PgInstrumentRepository
) -> None:
    _, _, suspended = build.stock("Paused Co", "PAU", status="suspended")
    assert repo.listing_ids_by_ticker("PAU", market=None, as_of=AS_OF) == [suspended]


def test_market_filter_uses_the_venue_country(build: Builder, repo: PgInstrumentRepository) -> None:
    _, _, us = build.stock("Shared Co", "SHR", mic="XNAS")
    _, _, gb = build.stock("Shared UK", "SHR", mic="XLON", currency="GBP")
    assert repo.listing_ids_by_ticker("SHR", market="US", as_of=AS_OF) == [us]
    assert repo.listing_ids_by_ticker("SHR", market="GB", as_of=AS_OF) == [gb]
    assert set(repo.listing_ids_by_ticker("SHR", market=None, as_of=AS_OF)) == {us, gb}
    assert repo.listing_ids_by_ticker("SHR", market="JP", as_of=AS_OF) == []


# --- identifiers -------------------------------------------------------------------------


def test_isin_on_security_returns_every_listing_of_that_security(
    build: Builder, repo: PgInstrumentRepository
) -> None:
    security = build.security(build.issuer("Dual Listed Inc"))
    nasdaq = build.listing(security, "DUAL", "XNAS")
    nyse = build.listing(security, "DUAL", "XNYS")
    build.identifier("security", security, "isin", "US0000000001")
    found = repo.listing_ids_by_identifier("US0000000001", market=None, as_of=AS_OF)
    assert set(found) == {nasdaq, nyse}


def test_figi_on_listing_returns_only_that_listing(
    build: Builder, repo: PgInstrumentRepository
) -> None:
    security = build.security(build.issuer("Dual Listed Inc"))
    nasdaq = build.listing(security, "DUAL", "XNAS")
    build.listing(security, "DUAL", "XNYS")
    build.identifier("listing", nasdaq, "figi", "BBG000000001")
    assert repo.listing_ids_by_identifier("BBG000000001", market=None, as_of=AS_OF) == [nasdaq]


@pytest.mark.parametrize("id_type", ["composite_figi", "share_class_figi"])
def test_other_figi_kinds_resolve_too(
    build: Builder, repo: PgInstrumentRepository, id_type: str
) -> None:
    _, security, listing = build.stock("Acme", "ACME")
    build.identifier("security", security, id_type, "BBG000000002")
    assert repo.listing_ids_by_identifier("BBG000000002", market=None, as_of=AS_OF) == [listing]


def test_identifier_on_issuer_resolves_all_issuer_listings(
    build: Builder, repo: PgInstrumentRepository
) -> None:
    issuer = build.issuer("Group Inc")
    a = build.listing(build.security(issuer), "GRPA", "XNAS")
    b = build.listing(build.security(issuer), "GRPB", "XNAS")
    build.identifier("issuer", issuer, "figi", "BBG000000003")
    found = repo.listing_ids_by_identifier("BBG000000003", market=None, as_of=AS_OF)
    assert set(found) == {a, b}


def test_non_lookup_identifier_types_are_ignored(
    build: Builder, repo: PgInstrumentRepository
) -> None:
    _, security, _ = build.stock("Acme", "ACME")
    build.identifier("security", security, "cusip", "037833100")
    build.identifier("security", security, "vendor_symbol", "ABCDEFGHIJKL")
    assert repo.listing_ids_by_identifier("ABCDEFGHIJKL", market=None, as_of=AS_OF) == []


def test_identifier_validity_window_is_respected(
    build: Builder, repo: PgInstrumentRepository
) -> None:
    _, security, listing = build.stock("Acme", "ACME")
    mid = datetime(2020, 1, 1, tzinfo=UTC)
    build.identifier("security", security, "isin", "US0000000010", valid_to=LONG_AGO)
    build.identifier(
        "security", security, "isin", "US0000000011", valid_from=LONG_AGO, valid_to=mid
    )
    build.identifier("security", security, "isin", "US0000000012", valid_from=mid)

    def lookup(value: str, as_of: date = AS_OF) -> list[uuid.UUID]:
        return repo.listing_ids_by_identifier(value, market=None, as_of=as_of)

    assert lookup("US0000000010") == []
    assert lookup("US0000000011") == []
    assert lookup("US0000000012") == [listing]
    assert lookup("US0000000011", date(2015, 6, 1)) == [listing]  # valid back then


# --- names -------------------------------------------------------------------------------


def test_name_exact_is_case_insensitive_on_legal_and_common_name(
    build: Builder, repo: PgInstrumentRepository
) -> None:
    issuer = build.issuer("Microsoft Corporation", common_name="Microsoft")
    listing = build.listing(build.security(issuer), "MSFT")

    def exact(name: str) -> list[uuid.UUID]:
        return repo.listing_ids_by_name(name, prefix=False, market=None, as_of=AS_OF, limit=10)

    assert exact("microsoft corporation") == [listing]
    assert exact("MICROSOFT") == [listing]
    assert exact("Microsoft Corp") == []


def test_name_prefix_matches_the_start_only(build: Builder, repo: PgInstrumentRepository) -> None:
    _, _, apple = build.stock("Apple Inc", "AAPL")
    build.stock("Pineapple Holdings", "PINE")
    found = repo.listing_ids_by_name("app", prefix=True, market=None, as_of=AS_OF, limit=10)
    assert found == [apple]


@pytest.mark.parametrize("wildcard", ["%", "_", "a%", "\\"])
def test_like_wildcards_in_the_query_are_literal(
    build: Builder, repo: PgInstrumentRepository, wildcard: str
) -> None:
    build.stock("Acme Corp", "ACME")
    build.stock("Beta Corp", "BETA")
    found = repo.listing_ids_by_name(wildcard, prefix=True, market=None, as_of=AS_OF, limit=10)
    assert found == []


def test_name_lookup_honours_limit_market_and_validity(
    build: Builder, repo: PgInstrumentRepository
) -> None:
    for i in range(5):
        build.stock(f"Common {i}", f"CM{i}")
    build.stock("Common UK", "CMUK", mic="XLON", currency="GBP")
    build.stock("Common Old", "CMOLD", mic="XNYS", valid_to=date(2020, 1, 1))

    def prefix(market: str | None, limit: int) -> list[uuid.UUID]:
        return repo.listing_ids_by_name(
            "Common", prefix=True, market=market, as_of=AS_OF, limit=limit
        )

    assert len(prefix(None, 3)) == 3
    assert len(prefix("US", 50)) == 5
    assert len(prefix("GB", 50)) == 1


# --- records -----------------------------------------------------------------------------


def test_records_project_names_venue_currency_and_current_identifiers(
    build: Builder, repo: PgInstrumentRepository
) -> None:
    issuer, security, listing = build.stock("Microsoft Corporation", "MSFT")
    build.identifier("security", security, "isin", "US5949181045")
    build.identifier("listing", listing, "figi", "BBG000BPH459")
    (record,) = repo.records([listing], as_of=AS_OF)
    assert record.issuer_id == issuer
    assert record.security_id == security
    assert record.listing_id == listing
    assert (record.issuer_name, record.ticker, record.venue_mic, record.currency) == (
        "Microsoft Corporation",
        "MSFT",
        "XNAS",
        "USD",
    )
    assert record.isin == "US5949181045"
    assert record.figi == "BBG000BPH459"


def test_records_use_null_for_missing_or_expired_identifiers(
    build: Builder, repo: PgInstrumentRepository
) -> None:
    _, security, listing = build.stock("Acme", "ACME")
    build.identifier("security", security, "isin", "US0000000099", valid_to=LONG_AGO)
    (record,) = repo.records([listing], as_of=AS_OF)
    assert record.isin is None
    assert record.figi is None


def test_records_of_nothing_is_empty(repo: PgInstrumentRepository) -> None:
    assert repo.records([], as_of=AS_OF) == []


# --- end to end --------------------------------------------------------------------------


def test_ambiguous_ticker_across_venues_requires_selection_end_to_end(
    build: Builder, repo: PgInstrumentRepository
) -> None:
    build.stock("Alpha Beta Corp", "ABC", mic="XNAS")
    build.stock("A B C Holdings", "ABC", mic="XNYS")
    result = resolve_instrument(repo, "abc", "us", as_of=AS_OF)
    assert result.requires_user_selection is True
    assert [m.record.venue_mic for m in result.matches] == ["XNAS", "XNYS"]


def test_isin_resolves_to_a_single_listing_end_to_end(
    build: Builder, repo: PgInstrumentRepository
) -> None:
    _, security, listing = build.stock("Microsoft Corporation", "MSFT")
    build.identifier("security", security, "isin", "US5949181045")
    result = resolve_instrument(repo, "us5949181045", None, as_of=AS_OF)
    assert [m.record.listing_id for m in result.matches] == [listing]
    assert result.requires_user_selection is False
