"""P1-16: migration 0007 — immutable data_snapshots and data_snapshot_items."""

from __future__ import annotations

import psycopg
import pytest

pytestmark = pytest.mark.integration

Conn = psycopg.Connection[tuple[object, ...]]
HASH = "d" * 64
RANGE_REF = '{"listing_id": "x", "interval": "1d"}'


def _scalar(db: Conn, query: str, params: tuple[object, ...] = ()) -> object:
    row = db.execute(query, params).fetchone()
    assert row is not None
    return row[0]


def _snapshot(db: Conn) -> object:
    ws = _scalar(db, "INSERT INTO workspaces (name) VALUES ('ws') RETURNING id")
    return _scalar(
        db,
        "INSERT INTO data_snapshots "
        "(workspace_id, snapshot_type, as_of, schema_version, selection_policy, manifest, "
        "content_hash) "
        "VALUES (%s, 'research_run', now(), 'v1', '{}'::jsonb, '{}'::jsonb, %s) RETURNING id",
        (ws, HASH),
    )


def _row_item(db: Conn, snapshot: object, record_type: str, record_id: object) -> None:
    db.execute(
        "INSERT INTO data_snapshot_items (snapshot_id, record_type, record_id, record_hash) "
        "VALUES (%s, %s, %s, %s)",
        (snapshot, record_type, record_id, HASH),
    )


def test_snapshot_immutable(db: Conn) -> None:
    snapshot = _snapshot(db)
    with pytest.raises(psycopg.errors.RestrictViolation, match="append-only"), db.transaction():
        db.execute("UPDATE data_snapshots SET schema_version = 'v2' WHERE id = %s", (snapshot,))
    with pytest.raises(psycopg.errors.RestrictViolation, match="append-only"), db.transaction():
        db.execute("DELETE FROM data_snapshots WHERE id = %s", (snapshot,))
    assert (
        _scalar(db, "SELECT schema_version FROM data_snapshots WHERE id = %s", (snapshot,)) == "v1"
    )


def test_snapshot_items_immutable(db: Conn) -> None:
    snapshot = _snapshot(db)
    _row_item(db, snapshot, "financial_fact", "11111111-1111-1111-1111-111111111111")
    with pytest.raises(psycopg.errors.RestrictViolation, match="append-only"), db.transaction():
        db.execute("UPDATE data_snapshot_items SET record_hash = %s", ("e" * 64,))
    with pytest.raises(psycopg.errors.RestrictViolation, match="append-only"), db.transaction():
        db.execute("DELETE FROM data_snapshot_items")
    assert _scalar(db, "SELECT record_hash FROM data_snapshot_items") == HASH


def test_snapshot_item_range_vs_record_ref_check(db: Conn) -> None:
    snapshot = _snapshot(db)
    insert = (
        "INSERT INTO data_snapshot_items "
        "(snapshot_id, record_type, record_id, range_ref_json, record_hash) "
        "VALUES (%s, %s, %s, %s::jsonb, %s)"
    )
    rid = "22222222-2222-2222-2222-222222222222"
    # a market_bar_range must carry range_ref_json and no record_id
    db.execute(insert, (snapshot, "market_bar_range", None, RANGE_REF, HASH))
    for bad in (
        (snapshot, "market_bar_range", None, None, HASH),  # range without range_ref_json
        (snapshot, "market_bar_range", rid, RANGE_REF, HASH),  # range with record_id
        (snapshot, "financial_fact", None, None, HASH),  # row ref without record_id
        (snapshot, "financial_fact", None, RANGE_REF, HASH),  # row ref with only a range
    ):
        with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
            db.execute(insert, bad)
    # a row reference needs record_id; the CHECK does not forbid an extra range_ref_json
    db.execute(insert, (snapshot, "financial_fact", rid, None, HASH))
    db.execute(insert, (snapshot, "filing", rid, RANGE_REF, HASH))
    assert _scalar(db, "SELECT count(*) FROM data_snapshot_items") == 3


def test_snapshot_item_duplicate_record_rejected(db: Conn) -> None:
    snapshot = _snapshot(db)
    rid = "33333333-3333-3333-3333-333333333333"
    _row_item(db, snapshot, "financial_fact", rid)
    with pytest.raises(psycopg.errors.UniqueViolation), db.transaction():
        _row_item(db, snapshot, "financial_fact", rid)
    _row_item(db, snapshot, "filing", rid)  # same id, different record type: fine
    other = _scalar(
        db,
        "INSERT INTO data_snapshots "
        "(workspace_id, snapshot_type, as_of, schema_version, selection_policy, manifest, "
        "content_hash) "
        "SELECT workspace_id, 'valuation', now(), 'v1', '{}'::jsonb, '{}'::jsonb, %s "
        "FROM data_snapshots WHERE id = %s RETURNING id",
        (HASH, snapshot),
    )
    _row_item(db, other, "financial_fact", rid)  # same record in another snapshot: fine


def test_multiple_range_items_are_allowed_in_one_snapshot(db: Conn) -> None:
    """The uniqueness index only covers row references (record_id IS NOT NULL)."""
    snapshot = _snapshot(db)
    for interval in ("1d", "1wk"):
        db.execute(
            "INSERT INTO data_snapshot_items "
            "(snapshot_id, record_type, range_ref_json, record_hash) "
            "VALUES (%s, 'market_bar_range', %s::jsonb, %s)",
            (snapshot, f'{{"interval": "{interval}"}}', HASH),
        )
    assert _scalar(db, "SELECT count(*) FROM data_snapshot_items") == 2


def test_snapshot_item_record_type_is_checked(db: Conn) -> None:
    snapshot = _snapshot(db)
    with pytest.raises(psycopg.errors.CheckViolation), db.transaction():
        _row_item(db, snapshot, "news_event", "44444444-4444-4444-4444-444444444444")


def test_snapshot_requires_workspace_and_item_requires_snapshot(db: Conn) -> None:
    with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
        db.execute(
            "INSERT INTO data_snapshots "
            "(workspace_id, snapshot_type, as_of, schema_version, selection_policy, manifest, "
            "content_hash) "
            "VALUES (gen_random_uuid(), 'research_run', now(), 'v1', '{}', '{}', %s)",
            (HASH,),
        )
    with pytest.raises(psycopg.errors.ForeignKeyViolation), db.transaction():
        _row_item(
            db,
            "00000000-0000-0000-0000-000000000000",
            "filing",
            "5" * 8 + "-5555-5555-5555-555555555555",
        )


def test_snapshot_content_hash_is_exactly_64_chars(db: Conn) -> None:
    ws = _scalar(db, "INSERT INTO workspaces (name) VALUES ('ws') RETURNING id")
    with pytest.raises(psycopg.errors.StringDataRightTruncation), db.transaction():
        db.execute(
            "INSERT INTO data_snapshots "
            "(workspace_id, snapshot_type, as_of, schema_version, selection_policy, manifest, "
            "content_hash) "
            "VALUES (%s, 'research_run', now(), 'v1', '{}', '{}', %s)",
            (ws, "f" * 65),
        )
