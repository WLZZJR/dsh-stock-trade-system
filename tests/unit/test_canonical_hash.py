"""P1-18 / D10: canonical_hash — fixed vectors, normalisation rules and rejected inputs.

The expected digests were computed independently with `sha256sum` over the literal canonical
JSON text, not with the implementation, so they pin the byte-level format across platforms.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from data_engine.canonical_hash import canonical_hash, canonical_json

TZ_PLUS_8 = timezone(timedelta(hours=8))

VECTORS = [
    (
        {"b": 1, "a": [True, None]},
        '{"a":[true,null],"b":1}',
        "51705a2c9eb3e7e410a58f696a770c3ac3885a0cf43eb7fc88f5e47c11d4d30d",
    ),
    (
        {"name": "é世界"},
        '{"name":"é世界"}',
        "b557472a2f47d9d2e1f2b607eec26ab25b108203685a1039880408b8c44d1415",
    ),
    (
        {"qty": Decimal("1E+2"), "price": Decimal("123.4500")},
        '{"price":"123.45","qty":"100"}',
        "2bfb7cae6a6fc63b66986c64707e76786eeb292c31930949c9481685602aeae3",
    ),
    (
        {
            "day": date(2026, 1, 2),
            "at": datetime(2026, 1, 2, 3, 4, 5, tzinfo=TZ_PLUS_8),
            "at_us": datetime(2026, 1, 1, 19, 4, 5, 500000, tzinfo=UTC),
        },
        '{"at":"2026-01-01T19:04:05Z","at_us":"2026-01-01T19:04:05.500000Z","day":"2026-01-02"}',
        "391c205641d6caab895b203ba376ac3676119ddb0eb045584a6e60787a154651",
    ),
    (
        {"b": -5, "a": {"y": [{"z": 0, "k": "v"}], "x": 1}},
        '{"a":{"x":1,"y":[{"k":"v","z":0}]},"b":-5}',
        "aa1d8cd9e19adaacd14e03c12e5d714349a97f36ecada1a96a2fcd8cbd526d4c",
    ),
    ({}, "{}", "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"),
    ([], "[]", "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"),
    ("x", '"x"', "ba2df4903a2c14e86dc3bcca58911b44ac1d2514b7227bf6eb08cfb978f55a1b"),
]


@pytest.mark.parametrize(("value", "text", "digest"), VECTORS)
def test_fixed_vectors(value: object, text: str, digest: str) -> None:
    assert canonical_json(value) == text.encode("utf-8")
    assert canonical_hash(value) == digest
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == digest  # vector self-check


def test_key_order_does_not_matter() -> None:
    assert canonical_hash({"a": 1, "b": 2}) == canonical_hash({"b": 2, "a": 1})


def test_list_order_matters() -> None:
    assert canonical_hash([1, 2]) != canonical_hash([2, 1])


def test_equal_decimals_hash_equally_whatever_their_scale() -> None:
    assert canonical_hash(Decimal("1.10")) == canonical_hash(Decimal("1.1"))
    assert canonical_hash(Decimal("0")) == canonical_hash(Decimal("-0.000"))
    assert canonical_json(Decimal("1E-7")) == b'"0.0000001"'
    assert canonical_json(Decimal("-12.50")) == b'"-12.5"'


def test_instants_are_normalised_to_utc() -> None:
    same_instant = (
        datetime(2026, 3, 1, 12, 0, tzinfo=UTC),
        datetime(2026, 3, 1, 20, 0, tzinfo=TZ_PLUS_8),
    )
    assert canonical_hash(same_instant[0]) == canonical_hash(same_instant[1])
    assert canonical_json(same_instant[1]) == b'"2026-03-01T12:00:00Z"'


def test_uuid_is_lowercase_hyphenated_text() -> None:
    value = UUID("12345678-1234-5678-1234-567812345678")
    assert canonical_json(value) == b'"12345678-1234-5678-1234-567812345678"'


def test_tuples_serialise_like_lists() -> None:
    assert canonical_hash((1, 2)) == canonical_hash([1, 2])


def test_output_is_64_lowercase_hex_chars() -> None:
    digest = canonical_hash({"k": "v"})
    assert len(digest) == 64
    assert digest == digest.lower()
    int(digest, 16)


@pytest.mark.parametrize("bad", [1.5, float("nan"), float("inf"), {"price": 0.1}, [1.0]])
def test_floats_are_rejected_anywhere(bad: object) -> None:
    with pytest.raises(TypeError, match="float"):
        canonical_hash(bad)


@pytest.mark.parametrize("bad", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_non_finite_decimals_are_rejected(bad: Decimal) -> None:
    with pytest.raises(ValueError, match="finite"):
        canonical_hash(bad)


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValueError, match="timezone"):
        canonical_hash(datetime(2026, 1, 1, 12, 0))


def test_non_string_keys_are_rejected() -> None:
    with pytest.raises(TypeError, match="key"):
        canonical_hash({1: "a"})


def test_unsupported_types_are_rejected() -> None:
    for bad in (object(), {1, 2}, b"bytes"):
        with pytest.raises(TypeError, match="unsupported"):
            canonical_hash(bad)


def test_bool_is_not_treated_as_int() -> None:
    assert canonical_json(True) == b"true"
    assert canonical_json(1) == b"1"
