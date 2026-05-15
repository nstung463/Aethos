"""Shared pytest fixtures for aethos tool tests."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from src.app.core.settings import get_settings
from src.app.api.dependencies import get_auth_repository, get_file_store, get_rate_limiter, get_thread_store
from src.app.features.chat.service import get_chat_service
from src.app.services.database import _build_sqlalchemy_engine
from src.app.services.runtime_state import shutdown_runtime_workers

_SYSTEM_TEMP_ROOT = Path(tempfile.gettempdir()).resolve() / "aethos-pytest"
_SYSTEM_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(_SYSTEM_TEMP_ROOT)


@pytest.fixture(scope="session", autouse=True)
def cleanup_runtime_workers() -> None:
    """Ensure runtime prewarm threads cannot leak across test session boundaries."""
    yield
    shutdown_runtime_workers(clear_cache=True)


@pytest.fixture(autouse=True)
def isolate_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TMP", str(_SYSTEM_TEMP_ROOT))
    monkeypatch.setenv("TEMP", str(_SYSTEM_TEMP_ROOT))
    monkeypatch.setenv("AETHOS_WORKSPACE_PREWARM_ENABLED", "0")
    monkeypatch.setenv("AETHOS_SECURITY_STATE_DIR", str(tmp_path / "security"))
    monkeypatch.setenv("AETHOS_USERS_DIR", str(tmp_path / "users"))
    monkeypatch.setenv("AETHOS_CHECKPOINTS_DIR", str(tmp_path / "checkpoints"))
    monkeypatch.setenv("AETHOS_MANAGED_FILES_DIR", str(tmp_path / "managed_files"))
    monkeypatch.setenv("AETHOS_CONFIG_HOME", str(tmp_path / "home-aethos"))
    monkeypatch.setenv("AETHOS_MANAGED_SETTINGS_DIR", str(tmp_path / "managed-settings"))
    get_settings.cache_clear()
    get_auth_repository.cache_clear()
    get_thread_store.cache_clear()
    get_file_store.cache_clear()
    get_rate_limiter.cache_clear()
    get_chat_service.cache_clear()
    _build_sqlalchemy_engine.cache_clear()


@pytest.fixture()
def disable_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AETHOS_DATABASE_ENABLED", raising=False)
    monkeypatch.delenv("AETHOS_DATABASE_URL", raising=False)
    monkeypatch.delenv("AETHOS_DATABASE_AUTO_MIGRATE", raising=False)
    get_settings.cache_clear()
    _build_sqlalchemy_engine.cache_clear()


@pytest.fixture()
def postgres_database(monkeypatch: pytest.MonkeyPatch) -> str:
    pytest.importorskip("psycopg")
    database_url = os.environ.get("AETHOS_TEST_DATABASE_URL", "").strip()
    if not database_url:
        pytest.skip("AETHOS_TEST_DATABASE_URL is not configured for PostgreSQL-backed app tests")

    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
    except OperationalError:
        pytest.skip("Configured PostgreSQL test database is not available")

    monkeypatch.setenv("AETHOS_DATABASE_ENABLED", "true")
    monkeypatch.setenv("AETHOS_DATABASE_URL", database_url)
    monkeypatch.setenv("AETHOS_DATABASE_AUTO_MIGRATE", "true")
    get_settings.cache_clear()
    _build_sqlalchemy_engine.cache_clear()
    return database_url


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    """Return a fresh temporary workspace root for each test."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws

