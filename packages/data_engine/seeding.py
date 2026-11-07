"""Apply the reference-data seeds in database/seeds/ (P1-17).

Every seed statement is idempotent (ON CONFLICT DO NOTHING / WHERE NOT EXISTS) and only inserts,
so running this repeatedly never duplicates or overwrites rows. Seeds are not migrations: the
schema works without them, and they can be re-applied at any time.

CLI: ``python -m data_engine.seeding`` reads GEI_DATABASE_URL (see ``make seed``).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import psycopg

SEEDS_DIR = Path(__file__).resolve().parents[2] / "database" / "seeds"


def seed_files() -> list[Path]:
    """Seed files in load order (the numeric filename prefix defines the order)."""
    return sorted(SEEDS_DIR.glob("*.sql"))


def apply_seeds(conn: psycopg.Connection[Any]) -> None:
    """Run every seed file on ``conn``. The caller owns the transaction."""
    for path in seed_files():
        # bytes keeps the multi-statement file as one simple-protocol query (no parameters).
        conn.execute(path.read_bytes())


def main() -> int:
    url = os.environ.get("GEI_DATABASE_URL")
    if not url:
        print("GEI_DATABASE_URL is not set; cannot apply seeds", file=sys.stderr)  # noqa: T201
        return 2
    with psycopg.connect(url) as conn, conn.transaction():
        apply_seeds(conn)
    print(f"applied {len(seed_files())} seed files")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
