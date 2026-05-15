from __future__ import annotations

import pytest

from src.app.core.settings import get_settings
from src.app.services.database import (
    _build_sqlalchemy_engine,
    get_database_config,
    get_sqlalchemy_engine,
    run_database_migrations,
)


def test_database_config_defaults_disabled(monkeypatch) -> None:
    monkeypatch.delenv("AETHOS_DATABASE_ENABLED", raising=False)
    monkeypatch.delenv("AETHOS_DATABASE_URL", raising=False)
    monkeypatch.delenv("AETHOS_DATABASE_AUTO_MIGRATE", raising=False)
    get_settings.cache_clear()

    config = get_database_config()

    assert config.enabled is False
    assert config.url is None
    assert config.auto_migrate is False
    assert config.is_configured is False


def test_database_config_reads_environment(monkeypatch) -> None:
    monkeypatch.setenv("AETHOS_DATABASE_ENABLED", "true")
    monkeypatch.setenv("AETHOS_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/aethos")
    monkeypatch.setenv("AETHOS_DATABASE_AUTO_MIGRATE", "true")
    get_settings.cache_clear()

    config = get_database_config()

    assert config.enabled is True
    assert config.url == "postgresql+psycopg://postgres:postgres@localhost:5432/aethos"
    assert config.auto_migrate is True
    assert config.is_configured is True


def test_sqlalchemy_engine_requires_database_url(monkeypatch) -> None:
    monkeypatch.delenv("AETHOS_DATABASE_URL", raising=False)
    get_settings.cache_clear()
    _build_sqlalchemy_engine.cache_clear()

    with pytest.raises(ValueError, match="AETHOS_DATABASE_URL"):
        get_sqlalchemy_engine()


def test_run_database_migrations_skips_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("AETHOS_DATABASE_ENABLED", "false")
    monkeypatch.setenv("AETHOS_DATABASE_AUTO_MIGRATE", "true")
    monkeypatch.setenv("AETHOS_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/aethos")
    get_settings.cache_clear()

    run_database_migrations()

