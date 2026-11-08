"""P1-21 / P1-22: instrument endpoints end to end over real PostgreSQL 16."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date

import psycopg
import pytest
from fastapi.testclient import TestClient
from masterdata import Builder

from api.deps import get_connection, require_session
from api.main import create_app
from domain.auth import Identity

pytestmark = pytest.mark.integration

Conn = psycopg.Connection[tuple[object, ...]]
IDENTITY = Identity(
    session_id=uuid.uuid4(),
    user_id=uuid.uuid4(),
    email="owner@example.com",
    workspace_id=uuid.uuid4(),
    role="owner",
)


@pytest.fixture
def build(db: Conn) -> Builder:
    return Builder(db)


@pytest.fixture
def client(db: Conn, build: Builder) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[require_session] = lambda: IDENTITY
    app.dependency_overrides[get_connection] = lambda: db  # same transaction as the test data
    yield TestClient(app, raise_server_exceptions=False)


def test_resolve_by_ticker_and_isin_returns_the_full_contract_shape(
    build: Builder, client: TestClient
) -> None:
    issuer, security, listing = build.stock("Microsoft Corporation", "MSFT")
    build.identifier("security", security, "isin", "US5949181045")
    build.identifier("listing", listing, "figi", "BBG000BPH459")
    expected = {
        "issuer_id": str(issuer),
        "security_id": str(security),
        "listing_id": str(listing),
        "issuer_name": "Microsoft Corporation",
        "ticker": "MSFT",
        "venue_mic": "XNAS",
        "currency": "USD",
        "identifiers": {"isin": "US5949181045", "figi": "BBG000BPH459"},
        "match_confidence": "high",
    }
    for query in ("MSFT", "msft", "US5949181045", "BBG000BPH459", "Microsoft Corporation"):
        body = client.get("/api/v1/instruments/resolve", params={"query": query}).json()
        assert body["matches"] == [expected], query
        assert body["requires_user_selection"] is False


def test_same_ticker_on_two_venues_requires_selection(build: Builder, client: TestClient) -> None:
    build.stock("Alpha Beta Corp", "ABC", mic="XNAS")
    build.stock("A B C Holdings", "ABC", mic="XNYS")
    body = client.get("/api/v1/instruments/resolve", params={"query": "ABC", "market": "US"}).json()
    assert body["requires_user_selection"] is True
    assert [m["venue_mic"] for m in body["matches"]] == ["XNAS", "XNYS"]


def test_reused_ticker_resolves_only_to_the_current_security(
    build: Builder, client: TestClient
) -> None:
    build.stock("Old Co", "ABC", valid_to=date(2020, 1, 1))
    _, _, current = build.stock("New Co", "ABC", valid_from=date(2020, 1, 1))
    body = client.get("/api/v1/instruments/resolve", params={"query": "ABC"}).json()
    assert [m["listing_id"] for m in body["matches"]] == [str(current)]
    assert body["requires_user_selection"] is False


def test_detail_works_for_a_delisted_listing_that_resolve_hides(
    build: Builder, client: TestClient
) -> None:
    _, _, gone = build.stock("Gone Co", "GONE", status="delisted")
    resolve = client.get("/api/v1/instruments/resolve", params={"query": "GONE"}).json()
    assert resolve["matches"] == []
    detail = client.get(f"/api/v1/instruments/{gone}")
    assert detail.status_code == 200
    assert detail.json()["ticker"] == "GONE"


def test_detail_of_unknown_listing_is_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/instruments/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


@pytest.mark.parametrize(
    "payload",
    ["' OR '1'='1", "'; DROP TABLE listings; --", "%", "_", "\\", "a%' --", "\x00ab"],
)
def test_hostile_query_strings_match_nothing_and_change_nothing(
    build: Builder, client: TestClient, db: Conn, payload: str
) -> None:
    build.stock("Acme Corp", "ACME")
    response = client.get("/api/v1/instruments/resolve", params={"query": payload})
    assert response.status_code in (200, 422)
    if response.status_code == 200:
        assert response.json()["matches"] == []
    row = db.execute("SELECT count(*) FROM listings WHERE ticker = 'ACME'").fetchone()
    assert row == (1,)
