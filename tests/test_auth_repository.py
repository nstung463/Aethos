from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

from src.app.core.settings import get_settings
from src.app.api.dependencies import get_auth_repository
from src.app.features.auth.repository import AuthRepository, _hash_token
from src.app.repositories.auth_repository import AuthRepository as ORMAuthRepository
from src.app.repositories.auth_repository import _hash_token as runtime_hash_token


def test_auth_repository_requires_postgres_in_runtime(tmp_path: Path, monkeypatch) -> None:
    config_home = tmp_path / "home-aethos"
    monkeypatch.setenv("AETHOS_CONFIG_HOME", str(config_home))
    monkeypatch.delenv("AETHOS_USERS_DIR", raising=False)
    monkeypatch.delenv("AETHOS_SECURITY_STATE_DIR", raising=False)
    monkeypatch.delenv("AETHOS_DATABASE_ENABLED", raising=False)
    monkeypatch.delenv("AETHOS_DATABASE_URL", raising=False)
    get_settings.cache_clear()
    get_auth_repository.cache_clear()

    with pytest.raises(ValueError, match="Auth now requires PostgreSQL"):
        get_auth_repository()


def test_auth_repository_returns_postgres_impl_when_configured(tmp_path: Path, monkeypatch) -> None:
    config_home = tmp_path / "home-aethos"
    monkeypatch.setenv("AETHOS_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("AETHOS_DATABASE_ENABLED", "true")
    monkeypatch.setenv("AETHOS_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/aethos")
    get_settings.cache_clear()
    get_auth_repository.cache_clear()

    repo = get_auth_repository()

    assert isinstance(repo, ORMAuthRepository)


def test_auth_repository_compat_module_reexports_orm_repository() -> None:
    assert AuthRepository is ORMAuthRepository


def test_auth_repository_compat_hash_token_matches_runtime_repository() -> None:
    token = "compat-token"

    assert _hash_token(token) == runtime_hash_token(token)


def test_auth_repository_refresh_decision_rules() -> None:
    repo = ORMAuthRepository(
        session_factory=sessionmaker(),
        session_refresh_interval_seconds=300,
    )
    now = 1_000

    assert repo._should_refresh_session(last_used_at=now - 10, expires_at=now + 3_600, now=now) is False
    assert repo._should_refresh_session(last_used_at=now - 301, expires_at=now + 3_600, now=now) is True
    assert repo._should_refresh_session(last_used_at=now - 10, expires_at=now + 200, now=now) is True
