"""P1-21 / P1-22: instrument endpoints follow API_CONTRACT 25.1 and the problem+json contract."""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import date

import psycopg
import pytest
from fastapi.testclient import TestClient

from api.deps import get_instrument_repository, get_today, require_session
from api.main import create_app
from domain.auth import Identity
from domain.instruments import InstrumentRecord

TODAY = date(2026, 11, 8)
IDENTITY = Identity(
    session_id=uuid.uuid4(),
    user_id=uuid.uuid4(),
    email="owner@example.com",
    workspace_id=uuid.uuid4(),
    role="owner",
)
MSFT = InstrumentRecord(
    issuer_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
    security_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
    listing_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
    issuer_name="Microsoft Corporation",
    ticker="MSFT",
    venue_mic="XNAS",
    currency="USD",
    isin="US5949181045",
    figi=None,
)
ABC_NASDAQ = InstrumentRecord(
    issuer_id=uuid.uuid4(),
    security_id=uuid.uuid4(),
    listing_id=uuid.UUID("44444444-4444-4444-4444-444444444444"),
    issuer_name="Alpha Beta Corp",
    ticker="ABC",
    venue_mic="XNAS",
    currency="USD",
    isin=None,
    figi="BBG000000001",
)
ABC_NYSE = InstrumentRecord(
    issuer_id=uuid.uuid4(),
    security_id=uuid.uuid4(),
    listing_id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
    issuer_name="A B C Holdings",
    ticker="ABC",
    venue_mic="XNYS",
    currency="USD",
    isin=None,
    figi=None,
)


@dataclass
class StaticRepo:
    rows: list[InstrumentRecord] = field(default_factory=lambda: [MSFT, ABC_NASDAQ, ABC_NYSE])
    markets: list[str | None] = field(default_factory=list)

    def listing_ids_by_ticker(
        self, ticker: str, *, market: str | None, as_of: date
    ) -> list[uuid.UUID]:
        self.markets.append(market)
        return [r.listing_id for r in self.rows if r.ticker == ticker]

    def listing_ids_by_identifier(
        self, value: str, *, market: str | None, as_of: date
    ) -> list[uuid.UUID]:
        return [r.listing_id for r in self.rows if value in (r.isin, r.figi)]

    def listing_ids_by_name(
        self, name: str, *, prefix: bool, market: str | None, as_of: date, limit: int
    ) -> list[uuid.UUID]:
        return []

    def records(self, listing_ids: Sequence[uuid.UUID], *, as_of: date) -> list[InstrumentRecord]:
        return [r for r in self.rows if r.listing_id in set(listing_ids)]


@pytest.fixture
def repo() -> StaticRepo:
    return StaticRepo()


@pytest.fixture
def client(repo: StaticRepo) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[require_session] = lambda: IDENTITY
    app.dependency_overrides[get_instrument_repository] = lambda: repo
    app.dependency_overrides[get_today] = lambda: TODAY
    yield TestClient(app, raise_server_exceptions=False)


# --- resolve -----------------------------------------------------------------------------


def test_resolve_unique_ticker_matches_the_contract_example_shape(client: TestClient) -> None:
    response = client.get("/api/v1/instruments/resolve", params={"query": "MSFT", "market": "US"})
    assert response.status_code == 200
    body = response.json()
    assert body["requires_user_selection"] is False
    assert body["truncated"] is False
    assert body["matches"] == [
        {
            "issuer_id": str(MSFT.issuer_id),
            "security_id": str(MSFT.security_id),
            "listing_id": str(MSFT.listing_id),
            "issuer_name": "Microsoft Corporation",
            "ticker": "MSFT",
            "venue_mic": "XNAS",
            "currency": "USD",
            "identifiers": {"isin": "US5949181045", "figi": None},
            "match_confidence": "high",
        }
    ]


def test_ambiguous_ticker_requires_selection_and_lists_every_candidate(client: TestClient) -> None:
    response = client.get("/api/v1/instruments/resolve", params={"query": "ABC"})
    body = response.json()
    assert response.status_code == 200
    assert body["requires_user_selection"] is True
    assert [m["venue_mic"] for m in body["matches"]] == ["XNAS", "XNYS"]


def test_resolve_by_isin(client: TestClient) -> None:
    body = client.get("/api/v1/instruments/resolve", params={"query": "us5949181045"}).json()
    assert [m["ticker"] for m in body["matches"]] == ["MSFT"]


def test_unknown_query_is_200_with_no_matches(client: TestClient) -> None:
    response = client.get("/api/v1/instruments/resolve", params={"query": "ZZZZ"})
    assert response.status_code == 200
    assert response.json() == {"matches": [], "requires_user_selection": False, "truncated": False}


def test_market_is_normalised_and_passed_through(client: TestClient, repo: StaticRepo) -> None:
    client.get("/api/v1/instruments/resolve", params={"query": "MSFT", "market": "us"})
    assert repo.markets == ["US"]


def test_missing_market_searches_everywhere(client: TestClient, repo: StaticRepo) -> None:
    client.get("/api/v1/instruments/resolve", params={"query": "MSFT"})
    assert repo.markets == [None]


@pytest.mark.parametrize(
    "params",
    [
        {},  # query is required
        {"query": ""},
        {"query": "   "},
        {"query": "x" * 101},
        {"query": "MSFT", "market": "USA"},
        {"query": "MSFT", "market": "1S"},
    ],
)
def test_bad_resolve_parameters_are_422_problems(
    client: TestClient, params: dict[str, str]
) -> None:
    response = client.get("/api/v1/instruments/resolve", params=params)
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["trace_id"] == response.headers["x-trace-id"]
    assert body["errors"]


# --- detail ------------------------------------------------------------------------------


def test_instrument_detail_returns_the_listing(client: TestClient) -> None:
    response = client.get(f"/api/v1/instruments/{MSFT.listing_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["listing_id"] == str(MSFT.listing_id)
    assert body["ticker"] == "MSFT"
    assert body["identifiers"] == {"isin": "US5949181045", "figi": None}
    assert "match_confidence" not in body


def test_unknown_listing_is_a_404_problem(client: TestClient) -> None:
    response = client.get(f"/api/v1/instruments/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "NOT_FOUND"


def test_malformed_listing_id_is_a_422_problem(client: TestClient) -> None:
    response = client.get("/api/v1/instruments/not-a-uuid")
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_resolve_is_not_shadowed_by_the_listing_id_route(client: TestClient) -> None:
    assert client.get("/api/v1/instruments/resolve", params={"query": "MSFT"}).status_code == 200


# --- database failure --------------------------------------------------------------------


def test_database_outage_is_503_without_leaking_the_driver_message() -> None:
    class BrokenRepo(StaticRepo):
        def listing_ids_by_ticker(
            self, ticker: str, *, market: str | None, as_of: date
        ) -> list[uuid.UUID]:
            raise psycopg.OperationalError("connection to server at 10.0.0.5 password=hunter2")

    app = create_app()
    app.dependency_overrides[require_session] = lambda: IDENTITY
    app.dependency_overrides[get_instrument_repository] = BrokenRepo
    app.dependency_overrides[get_today] = lambda: TODAY
    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/v1/instruments/resolve", params={"query": "MSFT"}
    )
    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"
    assert "10.0.0.5" not in response.text
    assert "hunter2" not in response.text


def test_unreachable_database_is_503_with_a_bounded_connect_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from application.config import Settings

    seen: dict[str, object] = {}

    def refuse(conninfo: str, **kwargs: object) -> None:
        seen.update(kwargs)
        raise psycopg.OperationalError("could not connect to 10.0.0.5 password=topsecretpw")

    monkeypatch.setattr("api.deps.psycopg.connect", refuse)
    app = create_app()
    app.dependency_overrides[require_session] = lambda: IDENTITY
    app.state.settings = Settings(
        database_url="postgresql://gei:topsecretpw@db.internal/gei",  # type: ignore[arg-type]
        redis_url="redis://redis.internal/0",  # type: ignore[arg-type]
    )
    app.dependency_overrides[get_today] = lambda: TODAY
    response = TestClient(app, raise_server_exceptions=False).get(
        "/api/v1/instruments/resolve", params={"query": "MSFT"}
    )
    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"
    assert "topsecretpw" not in response.text
    assert "10.0.0.5" not in response.text
    timeout = seen.get("connect_timeout")
    assert isinstance(timeout, int) and 0 < timeout <= 10  # never hang a request on a dead host
