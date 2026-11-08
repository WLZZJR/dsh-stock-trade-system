"""P1-21: domain rules for instrument queries and match confidence (pure, no I/O)."""

from __future__ import annotations

import pytest

from domain.instruments import Confidence, looks_like_identifier, normalize_market, normalize_query


def test_confidence_ranks_high_above_medium_above_low() -> None:
    assert Confidence.HIGH.rank < Confidence.MEDIUM.rank < Confidence.LOW.rank
    assert Confidence.HIGH.value == "high"


def test_stronger_picks_the_better_confidence() -> None:
    assert Confidence.stronger(Confidence.LOW, Confidence.HIGH) is Confidence.HIGH
    assert Confidence.stronger(Confidence.MEDIUM, Confidence.MEDIUM) is Confidence.MEDIUM


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  msft ", "msft"),
        ("Microsoft   Corporation", "Microsoft Corporation"),
        ("\tAAPL\n", "AAPL"),
    ],
)
def test_normalize_query_trims_and_collapses_whitespace(raw: str, expected: str) -> None:
    assert normalize_query(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "\n\t"])
def test_normalize_query_rejects_blank(raw: str) -> None:
    with pytest.raises(ValueError, match="blank"):
        normalize_query(raw)


@pytest.mark.parametrize(
    "value",
    ["US5949181045", "BBG000BPH459", "us5949181045", "BBG001S5S399"],
)
def test_twelve_character_alphanumerics_look_like_identifiers(value: str) -> None:
    assert looks_like_identifier(value)


@pytest.mark.parametrize(
    "value", ["MSFT", "Microsoft Corp", "US594918104", "US59491810455", "US-5949181045", ""]
)
def test_other_strings_do_not_look_like_identifiers(value: str) -> None:
    assert not looks_like_identifier(value)


@pytest.mark.parametrize(("raw", "expected"), [("us", "US"), (" Us ", "US"), ("GB", "GB")])
def test_normalize_market_uppercases_two_letter_codes(raw: str, expected: str) -> None:
    assert normalize_market(raw) == expected


@pytest.mark.parametrize("raw", ["USA", "U", "1S", "", "U S"])
def test_normalize_market_rejects_anything_but_two_letters(raw: str) -> None:
    with pytest.raises(ValueError, match="market"):
        normalize_market(raw)


@pytest.mark.parametrize("raw", ["ab\x00c", "ab\x07c", "ab\x1bc", "\x7fab"])
def test_normalize_query_rejects_control_characters(raw: str) -> None:
    with pytest.raises(ValueError, match="control"):
        normalize_query(raw)
