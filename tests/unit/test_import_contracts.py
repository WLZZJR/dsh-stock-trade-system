"""D7: packages/domain must stay free of framework and vendor imports."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LINT_IMPORTS = Path(sys.executable).parent / "lint-imports"
ROOT_PACKAGES = {
    "packages": ("domain", "application", "data_engine"),
    "apps": ("api",),
}


def _lint_imports(cwd: Path, pythonpath: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [str(LINT_IMPORTS), "--config", ".importlinter"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": pythonpath},
    )


def test_repository_satisfies_import_contracts() -> None:
    result = _lint_imports(REPO_ROOT, f"{REPO_ROOT / 'packages'}:{REPO_ROOT / 'apps'}")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Contracts: 1 kept, 0 broken" in result.stdout


@pytest.mark.parametrize(
    "forbidden", ["fastapi", "starlette", "sqlalchemy", "celery", "redis", "psycopg"]
)
def test_domain_importing_forbidden_package_is_rejected(tmp_path: Path, forbidden: str) -> None:
    for base, names in ROOT_PACKAGES.items():
        for name in names:
            pkg = tmp_path / base / name
            pkg.mkdir(parents=True)
            (pkg / "__init__.py").write_text("")
    (tmp_path / "packages" / "domain" / "bad.py").write_text(f"import {forbidden}\n")
    (tmp_path / ".importlinter").write_text((REPO_ROOT / ".importlinter").read_text())

    result = _lint_imports(tmp_path, f"{tmp_path / 'packages'}:{tmp_path / 'apps'}")

    assert result.returncode != 0, result.stdout + result.stderr
    assert "domain.bad" in result.stdout
    assert forbidden in result.stdout
