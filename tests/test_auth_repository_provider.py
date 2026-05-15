from __future__ import annotations

from pathlib import Path

import pytest

from src.app.core.settings import get_settings
from src.app.api.dependencies import get_auth_repository
from src.app.features.auth.types import AuthRepositoryProtocol, AuthRepositoryProvider
from src.app.repositories.auth_repository import AuthRepository
from src.app.services.database import _build_sqlalchemy_engine


def test_auth_repository_provider_requires_postgres_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AETHOS_CONFIG_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("AETHOS_DATABASE_ENABLED", raising=False)
    monkeypatch.delenv("AETHOS_DATABASE_URL", raising=False)
    get_settings.cache_clear()

    settings = get_settings()
    with pytest.raises(ValueError, match="Auth now requires PostgreSQL"):
        AuthRepositoryProvider(settings=settings).create()


def test_get_auth_repository_returns_protocol_compatible_impl(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AETHOS_CONFIG_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AETHOS_DATABASE_ENABLED", "true")
    monkeypatch.setenv("AETHOS_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/aethos")
    get_settings.cache_clear()
    get_auth_repository.cache_clear()

    repo = get_auth_repository()

    assert isinstance(repo, AuthRepositoryProtocol)
    assert isinstance(repo, AuthRepository)


def test_auth_repository_provider_returns_orm_impl(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AETHOS_CONFIG_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AETHOS_DATABASE_ENABLED", "true")
    monkeypatch.setenv("AETHOS_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/aethos")
    get_settings.cache_clear()
    _build_sqlalchemy_engine.cache_clear()

    settings = get_settings()
    repo = AuthRepositoryProvider(settings=settings).create()

    assert isinstance(repo, AuthRepository)

