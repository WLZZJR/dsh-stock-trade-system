"""Configuration loading: environment variables > ``configs/default.yaml``.

Secrets (database / Redis URLs, which may embed passwords) come from the
environment only and must never appear in YAML. Error messages never echo
input values, so a bad secret cannot leak through a startup failure.
"""

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

ENV_PREFIX = "GEI_"
DEFAULT_YAML_PATH = Path(__file__).resolve().parents[2] / "configs" / "default.yaml"


class ConfigError(Exception):
    """Raised when configuration is missing, malformed, or unsafe."""


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    # non-secret: may live in YAML, overridable by env
    env: Literal["dev", "test", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # secret: environment only
    database_url: SecretStr = Field(min_length=1)
    redis_url: SecretStr = Field(min_length=1)


SECRET_FIELDS = frozenset({"database_url", "redis_url"})


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ConfigError(f"config file not found: {path}") from None
    data = yaml.safe_load(raw)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"config file must be a mapping: {path}")
    leaked = sorted(SECRET_FIELDS & data.keys())
    if leaked:
        names = ", ".join(f"{k} (use {ENV_PREFIX}{k.upper()})" for k in leaked)
        raise ConfigError(f"secrets must not be set in YAML: {names}")
    return data


def _read_env(environ: Mapping[str, str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for name in Settings.model_fields:
        value = environ.get(f"{ENV_PREFIX}{name.upper()}")
        if value:  # empty string counts as unset
            values[name] = value
    return values


def load_settings(
    yaml_path: Path | None = None, environ: Mapping[str, str] | None = None
) -> Settings:
    merged = {
        **_read_yaml(yaml_path or DEFAULT_YAML_PATH),
        **_read_env(os.environ if environ is None else environ),
    }
    try:
        return Settings.model_validate(merged)
    except ValidationError as exc:
        problems = []
        for err in exc.errors(include_input=False):
            field = ".".join(str(p) for p in err["loc"])
            if err["type"] == "missing":
                problems.append(
                    f"missing required environment variable {ENV_PREFIX}{field.upper()}"
                )
            else:
                problems.append(f"invalid {field}: {err['msg']}")
        raise ConfigError("invalid configuration: " + "; ".join(problems)) from None


def main() -> int:
    """``python -m application.config``: validate configuration, print no secrets."""
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"config error: {exc}")
        return 1
    print(f"config ok (env={settings.env}, log_level={settings.log_level})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
