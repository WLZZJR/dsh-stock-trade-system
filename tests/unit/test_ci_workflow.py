"""P1-06 / D8: static guarantees for .github/workflows/ci.yml."""

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / ".github" / "workflows" / "ci.yml"
COMPOSE = ROOT / "deploy" / "compose" / "docker-compose.dev.yml"


def load() -> dict[str, Any]:
    data = yaml.safe_load(CI.read_text())
    assert isinstance(data, dict)
    return data


def test_triggers_are_pull_request_and_push_to_main() -> None:
    on = load()[True]  # PyYAML parses the bare key `on` as boolean True
    assert "pull_request" in on
    assert on["push"]["branches"] == ["main"]


def test_expected_jobs_exist() -> None:
    assert {"checks", "integration", "audit", "secret-scan"} <= set(load()["jobs"])


def test_permissions_are_read_only() -> None:
    assert load()["permissions"] == {"contents": "read"}


def test_every_action_is_pinned_to_a_commit_sha() -> None:
    uses = re.findall(r"^\s*-?\s*uses:\s*(\S+)", CI.read_text(), flags=re.MULTILINE)
    assert uses, "workflow should use at least actions/checkout"
    for ref in uses:
        assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", ref), f"not SHA-pinned: {ref}"


def test_run_steps_only_call_make_or_setup_commands() -> None:
    allowed = re.compile(r"^(make [\w-]+|uv sync --frozen)$")
    for job_name, job in load()["jobs"].items():
        for step in job["steps"]:
            run = step.get("run")
            if run is not None:
                assert allowed.match(run.strip()), f"{job_name}: unexpected command {run!r}"


def test_integration_postgres_image_matches_compose() -> None:
    compose_image = yaml.safe_load(COMPOSE.read_text())["services"]["postgres"]["image"]
    ci_image = load()["jobs"]["integration"]["services"]["postgres"]["image"]
    assert ci_image == compose_image


def test_secret_scan_checks_full_history() -> None:
    steps = load()["jobs"]["secret-scan"]["steps"]
    checkout = next(s for s in steps if str(s.get("uses", "")).startswith("actions/checkout@"))
    assert checkout["with"]["fetch-depth"] == 0


def test_checkout_does_not_persist_credentials() -> None:
    for job in load()["jobs"].values():
        for step in job["steps"]:
            if str(step.get("uses", "")).startswith("actions/checkout@"):
                assert step["with"]["persist-credentials"] is False
