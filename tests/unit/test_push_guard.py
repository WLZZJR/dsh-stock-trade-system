"""D8 fallback: without server-side branch protection, a local pre-push guard
refuses direct pushes to main. It is a convenience guard, not a security boundary."""

import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / "scripts" / "guard_main_push.sh"


def run_guard(remote_branch: str | None) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "PRE_COMMIT_REMOTE_BRANCH"}
    if remote_branch is not None:
        env["PRE_COMMIT_REMOTE_BRANCH"] = remote_branch
    return subprocess.run(  # noqa: S603
        ["bash", str(GUARD)],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_push_to_main_is_refused() -> None:
    result = run_guard("refs/heads/main")
    assert result.returncode != 0
    assert "direct push to main is refused" in result.stdout + result.stderr


def test_push_to_feature_branch_is_allowed() -> None:
    assert run_guard("refs/heads/feat/p1-06-ci").returncode == 0


def test_branch_names_containing_main_are_allowed() -> None:
    assert run_guard("refs/heads/maintenance").returncode == 0
    assert run_guard("refs/heads/feat/main-menu").returncode == 0


def test_guard_without_context_does_not_block() -> None:
    assert run_guard(None).returncode == 0


def test_pre_push_hooks_are_configured() -> None:
    config = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text())
    hooks = {h["id"]: h for repo in config["repos"] for h in repo["hooks"]}
    assert hooks["guard-main-push"]["stages"] == ["pre-push"]
    assert hooks["make-ci"]["stages"] == ["pre-push"]
