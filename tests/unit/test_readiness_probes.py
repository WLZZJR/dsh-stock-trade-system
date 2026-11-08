"""P1-25: probe building blocks that need no running service."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from data_engine import readiness_probes
from data_engine.readiness_probes import (
    PROBE_TIMEOUT_SECONDS,
    expected_migration_head,
    redis_probe,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def write_revision(directory: Path, revision: str, down: str | None) -> None:
    versions = directory / "versions"  # Alembic reads revisions from <script dir>/versions
    versions.mkdir(exist_ok=True)
    (versions / f"{revision}_x.py").write_text(
        f'revision = "{revision}"\ndown_revision = {down!r}\nbranch_labels = None\n'
        "depends_on = None\n\ndef upgrade() -> None:\n    pass\n\ndef downgrade() -> None:\n"
        "    pass\n"
    )


def test_expected_head_is_the_tip_of_the_revision_chain(tmp_path: Path) -> None:
    write_revision(tmp_path, "0001", None)
    write_revision(tmp_path, "0002", "0001")
    write_revision(tmp_path, "0003", "0002")
    assert expected_migration_head(tmp_path) == "0003"


def test_two_heads_are_an_error_not_a_guess(tmp_path: Path) -> None:
    write_revision(tmp_path, "0001", None)
    write_revision(tmp_path, "0002a", "0001")
    write_revision(tmp_path, "0002b", "0001")
    with pytest.raises(RuntimeError, match="found 2 heads"):
        expected_migration_head(tmp_path)


def test_the_repository_migrations_resolve_to_a_single_head() -> None:
    versions = sorted(p.stem for p in (REPO_ROOT / "database/migrations/versions").glob("0*.py"))
    assert expected_migration_head().startswith(versions[-1].split("_")[0])


class FakeRedis:
    instances: list[FakeRedis] = []  # noqa: RUF012

    def __init__(self, *, ping_result: object = True, error: Exception | None = None) -> None:
        self.ping_result = ping_result
        self.error = error
        self.closed = False
        FakeRedis.instances.append(self)

    def ping(self) -> object:
        if self.error:
            raise self.error
        return self.ping_result

    def close(self) -> None:
        self.closed = True


def install(monkeypatch: pytest.MonkeyPatch, **fake_args: Any) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    FakeRedis.instances = []

    def from_url(url: str, **kwargs: Any) -> FakeRedis:
        seen["url"] = url
        seen.update(kwargs)
        return FakeRedis(**fake_args)

    monkeypatch.setattr(readiness_probes.redis.Redis, "from_url", staticmethod(from_url))
    return seen


def test_redis_probe_pings_with_short_timeouts_and_closes_the_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = install(monkeypatch)
    assert redis_probe("redis://example/0") is True
    assert seen["url"] == "redis://example/0"
    assert seen["socket_connect_timeout"] == PROBE_TIMEOUT_SECONDS
    assert seen["socket_timeout"] == PROBE_TIMEOUT_SECONDS
    assert FakeRedis.instances[0].closed is True


def test_redis_probe_propagates_errors_and_still_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install(monkeypatch, error=ConnectionError("down"))
    with pytest.raises(ConnectionError):  # the aggregator turns this into a failed check
        redis_probe("redis://example/0")
    assert FakeRedis.instances[0].closed is True


def test_redis_probe_is_false_for_an_unexpected_ping_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, ping_result=False)
    assert redis_probe("redis://example/0") is False


def test_timeouts_are_short_enough_for_a_probe() -> None:
    assert 0 < PROBE_TIMEOUT_SECONDS <= 5
