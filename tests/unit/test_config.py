from pathlib import Path

import pytest

from application.config import ConfigError, load_settings

REQUIRED_ENV = {
    "GEI_DATABASE_URL": "postgresql://gei:s3cret-pw@localhost:5432/gei",
    "GEI_REDIS_URL": "redis://localhost:6379/0",
}


def write_yaml(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "default.yaml"
    path.write_text(text)
    return path


def test_loads_required_env_and_yaml_defaults(tmp_path: Path) -> None:
    cfg = write_yaml(tmp_path, "env: dev\nlog_level: INFO\n")
    settings = load_settings(yaml_path=cfg, environ=REQUIRED_ENV)
    assert settings.env == "dev"
    assert settings.log_level == "INFO"
    assert settings.database_url.get_secret_value().endswith("/gei")


def test_env_overrides_yaml(tmp_path: Path) -> None:
    cfg = write_yaml(tmp_path, "log_level: INFO\n")
    settings = load_settings(yaml_path=cfg, environ={**REQUIRED_ENV, "GEI_LOG_LEVEL": "DEBUG"})
    assert settings.log_level == "DEBUG"


def test_missing_required_env_fails_naming_each_variable(tmp_path: Path) -> None:
    cfg = write_yaml(tmp_path, "env: dev\n")
    with pytest.raises(ConfigError) as exc:
        load_settings(yaml_path=cfg, environ={})
    message = str(exc.value)
    assert "GEI_DATABASE_URL" in message
    assert "GEI_REDIS_URL" in message


def test_secret_in_yaml_is_rejected(tmp_path: Path) -> None:
    cfg = write_yaml(tmp_path, "database_url: postgresql://gei:pw@localhost/gei\n")
    with pytest.raises(ConfigError) as exc:
        load_settings(yaml_path=cfg, environ=REQUIRED_ENV)
    assert "database_url" in str(exc.value)
    assert "pw@" not in str(exc.value)


def test_unknown_yaml_key_is_rejected(tmp_path: Path) -> None:
    cfg = write_yaml(tmp_path, "typo_key: 1\n")
    with pytest.raises(ConfigError, match="typo_key"):
        load_settings(yaml_path=cfg, environ=REQUIRED_ENV)


def test_invalid_value_is_rejected(tmp_path: Path) -> None:
    cfg = write_yaml(tmp_path, "env: staging\n")
    with pytest.raises(ConfigError, match="env"):
        load_settings(yaml_path=cfg, environ=REQUIRED_ENV)


def test_secrets_are_masked_in_repr_and_error(tmp_path: Path) -> None:
    cfg = write_yaml(tmp_path, "")
    settings = load_settings(yaml_path=cfg, environ=REQUIRED_ENV)
    assert "s3cret-pw" not in repr(settings)
    assert "s3cret-pw" not in str(settings)


def test_missing_yaml_file_is_a_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_settings(yaml_path=tmp_path / "nope.yaml", environ=REQUIRED_ENV)


def test_repository_default_yaml_is_valid_and_secret_free() -> None:
    settings = load_settings(environ=REQUIRED_ENV)
    assert settings.env == "dev"
