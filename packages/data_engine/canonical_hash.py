"""Canonical JSON and SHA-256 hashing for data snapshots (plan D10, ADR-0010).

Snapshot manifests and record hashes must come out byte-identical on every platform and Python
version, so the format is pinned here instead of being left to ``json.dumps`` defaults:

* objects: string keys only, sorted by code point, recursively;
* separators ``,`` and ``:`` (no whitespace), non-ASCII kept as UTF-8 (no ``\\u`` escapes);
* ``Decimal`` -> plain-notation string without exponent or trailing zeros (``Decimal("1.10")``
  and ``Decimal("1.1")`` hash equally; zero, including ``-0``, is ``"0"``);
* ``datetime`` -> timezone-aware only, converted to UTC, ``YYYY-MM-DDTHH:MM:SS[.ffffff]Z``;
* ``date`` -> ``YYYY-MM-DD``; ``UUID`` -> lowercase hyphenated text;
* ``float`` is rejected everywhere (binary floats are not reproducible financial values);
* ``tuple`` is treated as a list; any other type is rejected.

Date and time text is built by hand, not with ``strftime``, because ``%Y`` is not zero-padded on
every platform.

Known property: a ``Decimal``, ``datetime`` or ``UUID`` is serialised as a JSON string, so it
hashes the same as a ``str`` holding that exact text. Callers that need to tell them apart must
include a type or field name in the hashed structure.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

_MAX_DECIMAL_EXPONENT = 10_000  # refuse values whose plain notation would be absurdly long


def canonical_json(value: object) -> bytes:
    """Return the canonical UTF-8 JSON encoding of ``value``."""
    text = json.dumps(
        _normalise(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return text.encode("utf-8")


def canonical_hash(value: object) -> str:
    """Return the SHA-256 of the canonical encoding as 64 lowercase hex characters."""
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _normalise(value: object) -> Any:
    # bool must be tested before int (bool is an int subclass) and datetime before date.
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        raise TypeError("float values are not allowed in canonical hashing; use Decimal or str")
    if isinstance(value, Decimal):
        return _decimal_text(value)
    if isinstance(value, datetime):
        return _datetime_text(value)
    if isinstance(value, date):
        return f"{value.year:04d}-{value.month:02d}-{value.day:02d}"
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"object key must be str, got {type(key).__name__}")
            result[key] = _normalise(item)
        return result
    if isinstance(value, list | tuple):
        return [_normalise(item) for item in value]
    raise TypeError(f"unsupported type for canonical hashing: {type(value).__name__}")


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("Decimal must be finite (no NaN or Infinity)")
    sign, digits, exponent = value.as_tuple()
    if not isinstance(exponent, int):  # unreachable for finite values; narrows the type
        raise ValueError("Decimal must be finite (no NaN or Infinity)")
    coefficient = int("".join(map(str, digits)))
    if coefficient == 0:
        return "0"
    while coefficient % 10 == 0:
        coefficient //= 10
        exponent += 1
    if abs(exponent) > _MAX_DECIMAL_EXPONENT:
        raise ValueError("Decimal exponent is out of the supported range")
    text = str(coefficient)
    if exponent >= 0:
        text += "0" * exponent
    else:
        point = len(text) + exponent
        text = f"{text[:point]}.{text[point:]}" if point > 0 else "0." + "0" * -point + text
    return f"-{text}" if sign else text


def _datetime_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware (naive datetimes are ambiguous)")
    utc = value.astimezone(UTC)
    text = (
        f"{utc.year:04d}-{utc.month:02d}-{utc.day:02d}"
        f"T{utc.hour:02d}:{utc.minute:02d}:{utc.second:02d}"
    )
    if utc.microsecond:
        text += f".{utc.microsecond:06d}"
    return text + "Z"
