"""Source registry lookups: every fact row must carry a registered ``source_id`` (P1-17)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg


def get_source_id(
    conn: psycopg.Connection[Any], provider_name: str, source_name: str | None = None
) -> UUID:
    """Return the id of ``source_name`` (default: same as the provider) for a provider.

    Raises ``LookupError`` if it is not registered, e.g. because the seeds were not applied.
    """
    wanted = source_name or provider_name
    row = conn.execute(
        "SELECT d.id FROM data_sources d JOIN providers p ON p.id = d.provider_id "
        "WHERE p.name = %s AND d.source_name = %s ORDER BY d.created_at, d.id LIMIT 1",
        (provider_name, wanted),
    ).fetchone()
    if row is None:
        raise LookupError(
            f"data source {wanted!r} of provider {provider_name!r} is not registered; apply seeds"
        )
    source_id = row[0]
    if not isinstance(source_id, UUID):
        raise TypeError(f"data_sources.id returned {type(source_id).__name__}, expected UUID")
    return source_id
