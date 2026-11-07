"""P1-05: static guarantees for docker-compose.dev.yml."""

from pathlib import Path
from typing import Any

import yaml

COMPOSE = Path(__file__).resolve().parents[2] / "deploy" / "compose" / "docker-compose.dev.yml"


def load() -> dict[str, Any]:
    data = yaml.safe_load(COMPOSE.read_text())
    assert isinstance(data, dict)
    return data


def test_exactly_the_phase1_services() -> None:
    assert set(load()["services"]) == {"postgres", "redis", "api"}


def test_all_published_ports_bind_localhost_only() -> None:
    for name, svc in load()["services"].items():
        for port in svc.get("ports", []):
            assert str(port).startswith("127.0.0.1:"), f"{name} publishes {port}"


def test_every_service_has_a_healthcheck() -> None:
    for name, svc in load()["services"].items():
        assert "healthcheck" in svc, name


def test_images_use_pinned_major_versions() -> None:
    services = load()["services"]
    assert services["postgres"]["image"].startswith("postgres:16")
    assert services["redis"]["image"].startswith("redis:8")


def test_api_waits_for_healthy_dependencies() -> None:
    depends = load()["services"]["api"]["depends_on"]
    assert depends["postgres"]["condition"] == "service_healthy"
    assert depends["redis"]["condition"] == "service_healthy"


def test_no_literal_password_in_compose_file() -> None:
    text = COMPOSE.read_text()
    assert "change-me" not in text
    assert "${GEI_POSTGRES_PASSWORD:?" in text
