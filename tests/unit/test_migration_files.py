"""P1-19: static guarantees for database/migrations/versions (no database needed)."""

from __future__ import annotations

import ast
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "database" / "migrations" / "versions"
FILES = sorted(VERSIONS.glob("[0-9][0-9][0-9][0-9]_*.py"))


def _script() -> ScriptDirectory:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "database" / "migrations"))
    return ScriptDirectory.from_config(cfg)


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"missing function {name}()")


def test_history_is_linear_with_one_head_and_contiguous_ids() -> None:
    script = _script()
    assert len(script.get_heads()) == 1
    ascending = [r.revision for r in reversed(list(script.walk_revisions()))]
    assert ascending == [f"{n:04d}" for n in range(1, len(ascending) + 1)]
    assert len(FILES) == len(ascending)


def test_file_names_match_revision_ids() -> None:
    script = _script()
    for path in FILES:
        revision = script.get_revision(path.name[:4])
        assert revision is not None
        assert Path(revision.path).name == path.name


def test_every_migration_has_a_real_downgrade() -> None:
    for path in FILES:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for name in ("upgrade", "downgrade"):
            segment = ast.get_source_segment(source, _function(tree, name)) or ""
            assert "op.execute(" in segment, f"{path.name}: {name}() does nothing"


def test_migrations_are_hand_written_sql_not_orm_metadata() -> None:
    """D6: constraints and triggers are raw SQL; nothing relies on SQLAlchemy autogenerate."""
    for path in FILES:
        source = path.read_text(encoding="utf-8")
        assert "sqlalchemy" not in source, path.name
        assert "autogenerate" not in source, path.name
