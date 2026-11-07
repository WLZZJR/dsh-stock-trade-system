"""P1-15: migration 0006 — raw_payloads (dedup + retention CHECK) and ingest_log."""

from __future__ import annotations

import psycopg
import pytest

pytestmark = pytest.mark.integration

Conn = psycopg.Connection[tuple[object, ...]]
HASH_A = "a" * 64
HASH_B = "b" * 64


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


def _payload(db: Conn, provider: object, digest: str = HASH_A) -> object:
    return _scalar(
        db,
        "INSERT INTO raw_payloads (provider_id, payload_json, payload_hash) "
        "VALUES (%s, '{\"k\": 1}'::jsonb, %s) RETURNING id",
        (provider, digest),
    )


def test_hash_only_requires_null_payload(db: Conn) -> None:
    provider = _provider(db)
    with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
        db.execute(
            "INSERT INTO raw_payloads (provider_id, payload_json, payload_hash, retention) "
            "VALUES (%s, '{}'::jsonb, %s, 'hash_only')",
            (provider, HASH_A),
        )
    db.execute(
        "INSERT INTO raw_payloads (provider_id, payload_hash, retention) "
        "VALUES (%s, %s, 'hash_only')",
        (provider, HASH_A),
    )
    assert _scalar(db, "SELECT payload_json IS NULL FROM raw_payloads") is True


def test_stored_requires_payload(db: Conn) -> None:
    provider = _provider(db)
    with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
        db.execute(
            "INSERT INTO raw_payloads (provider_id, payload_hash, retention) "
            "VALUES (%s, %s, 'stored')",
            (provider, HASH_A),
        )
    with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
        db.execute(
            "INSERT INTO raw_payloads (provider_id, payload_hash) VALUES (%s, %s)",
            (provider, HASH_A),  # retention defaults to 'stored'
        )
    assert _scalar(db, "SELECT count(*) FROM raw_payloads") == 0


def test_retention_value_is_checked(db: Conn) -> None:
    provider = _provider(db)
    with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
        db.execute(
            "INSERT INTO raw_payloads (provider_id, payload_json, payload_hash, retention) "
            "VALUES (%s, '{}'::jsonb, %s, 'forever')",
            (provider, HASH_A),
        )


def test_raw_payload_dedup_unique(db: Conn) -> None:
    provider, other = _provider(db), _provider(db, "other_data")
    _payload(db, provider, HASH_A)
    with pytest.raises(psycopg.errors.UniqueViolation), db.transaction():
        _payload(db, provider, HASH_A)
    _payload(db, provider, HASH_B)  # different content, same provider: fine
    _payload(db, other, HASH_A)  # same content, different provider: fine
    assert _scalar(db, "SELECT count(*) FROM raw_payloads") == 3


def test_payload_hash_is_exactly_64_chars(db: Conn) -> None:
    provider = _provider(db)
    with pytest.raises(psycopg.errors.StringDataRightTruncation), db.transaction():
        _payload(db, provider, "c" * 65)


def test_ingest_log_failed_request_has_no_payload(db: Conn) -> None:
    provider = _provider(db)
    row = db.execute(
        "INSERT INTO ingest_log "
        "(provider_id, endpoint, request_hash, requested_at, http_status, "
        "error_code, error_message) "
        "VALUES (%s, '/v1/bars', %s, now(), 503, 'upstream_unavailable', 'try later') "
        "RETURNING payload_id, retry_count, response_meta_json",
        (provider, HASH_A),
    ).fetchone()
    assert row == (None, 0, {})


def test_ingest_log_keeps_every_attempt_including_duplicates(db: Conn) -> None:
    provider = _provider(db)
    payload = _payload(db, provider)
    for _ in range(2):  # same request, same content: two events, one payload
        db.execute(
            "INSERT INTO ingest_log "
            "(provider_id, endpoint, request_hash, requested_at, http_status, payload_id) "
            "VALUES (%s, '/v1/bars', %s, now(), 200, %s)",
            (provider, HASH_A, payload),
        )
    assert _scalar(db, "SELECT count(*) FROM ingest_log") == 2
    assert _scalar(db, "SELECT count(*) FROM raw_payloads") == 1


def test_ingest_log_payload_fk_and_restrict(db: Conn) -> None:
    provider = _provider(db)
    with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
        db.execute(
            "INSERT INTO ingest_log "
            "(provider_id, endpoint, request_hash, requested_at, payload_id) "
            "VALUES (%s, '/v1/bars', %s, now(), gen_random_uuid())",
            (provider, HASH_A),
        )
    payload = _payload(db, provider)
    db.execute(
        "INSERT INTO ingest_log (provider_id, endpoint, request_hash, requested_at, payload_id) "
        "VALUES (%s, '/v1/bars', %s, now(), %s)",
        (provider, HASH_A, payload),
    )
    with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
        db.execute("DELETE FROM raw_payloads WHERE id = %s", (payload,))


def test_ingest_log_requires_provider_endpoint_hash_and_request_time(db: Conn) -> None:
    provider = _provider(db)
    with pytest.raises(psycopg.errors.NotNullViolation), db.transaction():
        db.execute(
            "INSERT INTO ingest_log (provider_id, endpoint, request_hash) VALUES (%s, '/x', %s)",
            (provider, HASH_A),
        )


def test_ingest_log_time_index_exists(db: Conn) -> None:
    rows = db.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'ingest_log'").fetchall()
    assert "idx_ingest_log_provider_time" in {r[0] for r in rows}
