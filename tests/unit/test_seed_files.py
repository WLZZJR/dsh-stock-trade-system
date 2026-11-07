"""P1-17: static guarantees for database/seeds/*.sql (no database needed)."""

from __future__ import annotations

import re
from pathlib import Path

SEEDS = Path(__file__).resolve().parents[2] / "database" / "seeds"
FILES = sorted(SEEDS.glob("*.sql"))
MUTATING = re.compile(r"\b(UPDATE|DELETE|TRUNCATE|DROP)\b", re.IGNORECASE)


def test_seed_files_exist_in_load_order() -> None:
    assert [f.name for f in FILES] == [
        "01_currencies.sql",
        "02_countries.sql",
        "03_venues_us.sql",
        "04_sources.sql",
    ]


def test_every_statement_is_idempotent() -> None:
    for path in FILES:
        text = path.read_text(encoding="utf-8")
        statements = [s for s in re.split(r";\s*\n", text) if "INSERT" in s.upper()]
        assert statements, f"{path.name} has no INSERT"
        for statement in statements:
            assert "ON CONFLICT" in statement or "WHERE NOT EXISTS" in statement, (
                f"{path.name}: statement is not safe to re-run:\n{statement[:200]}"
            )


def test_seeds_only_insert() -> None:
    for path in FILES:
        text = path.read_text(encoding="utf-8")
        body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("--"))
        assert not MUTATING.search(body), path.name


def test_seed_files_record_their_provenance() -> None:
    for name in ("01_currencies.sql", "02_countries.sql"):
        head = (SEEDS / name).read_text(encoding="utf-8")[:800]
        assert "Source:" in head
        assert "Retrieved:" in head
