"""P1-13: migration 0004 — providers, data_sources, provider_entitlements, provider_coverage."""

from __future__ import annotations

import psycopg
import pytest

pytestmark = pytest.mark.integration

Conn = psycopg.Connection[tuple[object, ...]]


def _scalar(db: Conn, query: str, params: tuple[object, ...] = ()) -> object:
    row = db.execute(query, params).fetchone()
    assert row is not None
    return row[0]


def _provider(db: Conn, name: str = "acme_data") -> object:
    return _scalar(
        db,
        "INSERT INTO providers (name, provider_type) VALUES (%s, 'market_data') RETURNING id",
        (name,),
    )


def _workspace(db: Conn) -> object:
    return _scalar(db, "INSERT INTO workspaces (name) VALUES ('ws') RETURNING id")


def test_entitlement_defaults_to_no_persistence_llm_or_redistribution(db: Conn) -> None:
    """ADR-0014: every permission switch defaults to false (minimum authorisation)."""
    provider, ws = _provider(db), _workspace(db)
    row = db.execute(
        "INSERT INTO provider_entitlements (provider_id, workspace_id, license_type, allowed_use) "
        "VALUES (%s, %s, 'unreviewed', 'none') "
        "RETURNING persistence_allowed, llm_transmission_allowed, redistribution_allowed",
        (provider, ws),
    ).fetchone()
    assert row == (False, False, False)


def test_one_entitlement_per_provider_and_workspace(db: Conn) -> None:
    provider, ws = _provider(db), _workspace(db)
    insert = (
        "INSERT INTO provider_entitlements (provider_id, workspace_id, license_type, allowed_use) "
        "VALUES (%s, %s, 'personal', 'research')"
    )
    db.execute(insert, (provider, ws))
    with pytest.raises(psycopg.errors.UniqueViolation), db.transaction():
        db.execute(insert, (provider, ws))


def test_provider_defaults_and_unique_name(db: Conn) -> None:
    _provider(db)
    assert _scalar(db, "SELECT status FROM providers WHERE name = 'acme_data'") == "active"
    with pytest.raises(psycopg.errors.UniqueViolation), db.transaction():
        _provider(db)


def test_data_source_requires_name_and_type_and_known_provider(db: Conn) -> None:
    provider = _provider(db)
    db.execute(
        "INSERT INTO data_sources (provider_id, source_name, source_type) "
        "VALUES (%s, 'daily bars', 'api')",
        (provider,),
    )
    with pytest.raises(psycopg.errors.NotNullViolation), db.transaction():
        db.execute(
            "INSERT INTO data_sources (provider_id, source_name) VALUES (%s, 'x')", (provider,)
        )
    with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
        db.execute(
            "INSERT INTO data_sources (provider_id, source_name, source_type) "
            "VALUES (gen_random_uuid(), 'x', 'api')"
        )


def test_data_source_provider_is_optional(db: Conn) -> None:
    """Hand-entered data may have a source without a vendor (provider_id is nullable)."""
    db.execute("INSERT INTO data_sources (source_name, source_type) VALUES ('notes', 'manual')")
    assert _scalar(db, "SELECT count(*) FROM data_sources WHERE provider_id IS NULL") == 1


def test_provider_with_sources_cannot_be_deleted(db: Conn) -> None:
    provider = _provider(db)
    db.execute(
        "INSERT INTO data_sources (provider_id, source_name, source_type) VALUES (%s, 's', 'api')",
        (provider,),
    )
    with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
        db.execute("DELETE FROM providers WHERE id = %s", (provider,))


def test_workspace_with_entitlements_cannot_be_deleted(db: Conn) -> None:
    provider, ws = _provider(db), _workspace(db)
    db.execute(
        "INSERT INTO provider_entitlements (provider_id, workspace_id, license_type, allowed_use) "
        "VALUES (%s, %s, 'personal', 'research')",
        (provider, ws),
    )
    with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
        db.execute("DELETE FROM workspaces WHERE id = %s", (ws,))


def test_coverage_status_checked_and_key_unique(db: Conn) -> None:
    provider = _provider(db)
    insert = (
        "INSERT INTO provider_coverage (provider_id, market_code, dataset, coverage_status) "
        "VALUES (%s, 'US', 'daily_bars', %s)"
    )
    db.execute(insert, (provider, "supported"))
    with pytest.raises(psycopg.errors.UniqueViolation), db.transaction():
        db.execute(insert, (provider, "partial"))
    with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
        db.execute(
            "INSERT INTO provider_coverage (provider_id, market_code, dataset, coverage_status) "
            "VALUES (%s, 'US', 'fundamentals', 'maybe')",
            (provider,),
        )
