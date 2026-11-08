"""P1-20: the problem catalog covers every error category named in API_CONTRACT 25.4."""

from __future__ import annotations

import pytest

from application import problems
from application.problems import ProblemError, ProblemSpec, problem_type

# API_CONTRACT 25.4 categories: parameter, instrument ambiguity, missing data, authorization,
# provider rate limit, task conflict, model not applicable, internal error.
CONTRACT_CATEGORIES = {
    "parameter": problems.VALIDATION_ERROR,
    "ambiguous_instrument": problems.AMBIGUOUS_INSTRUMENT,
    "data_missing": problems.MISSING_REQUIRED_FIELD,
    "unauthenticated": problems.UNAUTHENTICATED,
    "forbidden": problems.FORBIDDEN,
    "rate_limited": problems.RATE_LIMITED,
    "task_conflict": problems.TASK_CONFLICT,
    "model_not_applicable": problems.MODEL_NOT_APPLICABLE,
    "internal": problems.INTERNAL_ERROR,
}


def test_every_contract_category_has_a_distinct_code() -> None:
    codes = [spec.code for spec in CONTRACT_CATEGORIES.values()]
    assert len(set(codes)) == len(codes)


def test_catalog_entries_are_well_formed() -> None:
    for spec in problems.CATALOG:
        assert isinstance(spec, ProblemSpec)
        assert spec.code == spec.code.upper()
        assert 400 <= spec.status <= 599
        assert spec.title


def test_catalog_codes_are_unique() -> None:
    codes = [spec.code for spec in problems.CATALOG]
    assert len(set(codes)) == len(codes)


def test_problem_type_is_a_stable_uri_derived_from_the_code() -> None:
    assert problem_type(problems.MISSING_REQUIRED_FIELD) == (
        "https://example.invalid/problems/missing-required-field"
    )


def test_problem_error_carries_spec_detail_and_extensions() -> None:
    err = ProblemError(
        problems.MISSING_REQUIRED_FIELD,
        "Required financial facts are unavailable.",
        missing_fields=["net_debt"],
    )
    assert err.spec is problems.MISSING_REQUIRED_FIELD
    assert err.detail == "Required financial facts are unavailable."
    assert err.extensions == {"missing_fields": ["net_debt"]}


@pytest.mark.parametrize("reserved", ["type", "title", "status", "code", "detail", "trace_id"])
def test_extensions_cannot_overwrite_standard_members(reserved: str) -> None:
    with pytest.raises(ValueError, match=reserved):
        ProblemError(problems.INTERNAL_ERROR, "x", **{reserved: "spoofed"})


def test_problem_error_can_carry_response_headers() -> None:
    err = ProblemError(problems.RATE_LIMITED, "slow down", retry_after=30)
    assert err.headers == {}
    err.headers["Retry-After"] = "30"
    assert err.headers == {"Retry-After": "30"}
    assert err.extensions == {"retry_after": 30}
