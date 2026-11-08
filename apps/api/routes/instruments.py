"""GET /instruments/resolve and GET /instruments/{listing_id} (API_CONTRACT 25, 25.1)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from api.deps import get_instrument_repository, get_today
from api.problem_http import problem_responses
from application import problems
from application.instrument_resolution import (
    InstrumentRepository,
    get_instrument,
    resolve_instrument,
)
from application.problems import ProblemError
from domain.instruments import InstrumentMatch, InstrumentRecord

router = APIRouter(prefix="/instruments", tags=["instruments"])


class Identifiers(BaseModel):
    isin: str | None
    figi: str | None


class InstrumentOut(BaseModel):
    issuer_id: uuid.UUID
    security_id: uuid.UUID
    listing_id: uuid.UUID
    issuer_name: str
    ticker: str
    venue_mic: str
    currency: str
    identifiers: Identifiers


class InstrumentMatchOut(InstrumentOut):
    match_confidence: Literal["high", "medium", "low"]


class ResolveResponse(BaseModel):
    matches: list[InstrumentMatchOut]
    requires_user_selection: bool
    truncated: bool


def _instrument(record: InstrumentRecord) -> dict[str, object]:
    return {
        "issuer_id": record.issuer_id,
        "security_id": record.security_id,
        "listing_id": record.listing_id,
        "issuer_name": record.issuer_name,
        "ticker": record.ticker,
        "venue_mic": record.venue_mic,
        "currency": record.currency,
        "identifiers": Identifiers(isin=record.isin, figi=record.figi),
    }


def _match(match: InstrumentMatch) -> InstrumentMatchOut:
    return InstrumentMatchOut(**_instrument(match.record), match_confidence=match.confidence.value)  # type: ignore[arg-type]


@router.get("/resolve", response_model=ResolveResponse, responses=problem_responses(422, 503))
def resolve(
    repo: Annotated[InstrumentRepository, Depends(get_instrument_repository)],
    today: Annotated[date, Depends(get_today)],
    query: Annotated[str, Query(min_length=1, max_length=100)],
    market: Annotated[str | None, Query(pattern=r"^[A-Za-z]{2}$")] = None,
) -> ResolveResponse:
    try:
        result = resolve_instrument(repo, query, market, as_of=today)
    except ValueError:  # blank (only spaces) or containing control characters
        raise ProblemError(
            problems.VALIDATION_ERROR,
            "Request parameters failed validation.",
            errors=[{"loc": ["query", "query"], "type": "invalid_query"}],
        ) from None
    return ResolveResponse(
        matches=[_match(m) for m in result.matches],
        requires_user_selection=result.requires_user_selection,
        truncated=result.truncated,
    )


@router.get(
    "/{listing_id}", response_model=InstrumentOut, responses=problem_responses(404, 422, 503)
)
def instrument_detail(
    listing_id: uuid.UUID,
    repo: Annotated[InstrumentRepository, Depends(get_instrument_repository)],
    today: Annotated[date, Depends(get_today)],
) -> InstrumentOut:
    record = get_instrument(repo, listing_id, as_of=today)
    if record is None:
        raise ProblemError(problems.NOT_FOUND, "No listing exists with this id.")
    return InstrumentOut(**_instrument(record))  # type: ignore[arg-type]
