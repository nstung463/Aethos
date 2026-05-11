"""Shared pytest fixtures for aethos tool tests."""
from __future__ import annotations

import os
import time
import tempfile
from pathlib import Path

import pytest

from src.app.core.settings import get_settings
from src.app.dependencies import get_auth_repository, get_file_store, get_rate_limiter, get_thread_store
from src.app.modules.chat.service import get_chat_service

_TEST_TEMP_ROOT = (
    Path(__file__).resolve().parent.parent
    / "tmp"
    / f"pytest-{os.getpid()}-{int(time.time() * 1000)}"
).resolve()
_TEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
os.environ["TMP"] = str(_TEST_TEMP_ROOT)
os.environ["TEMP"] = str(_TEST_TEMP_ROOT)
tempfile.tempdir = str(_TEST_TEMP_ROOT)


@pytest.fixture(autouse=True)
def isolate_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AETHOS_SECURITY_STATE_DIR", str(tmp_path / "security"))
    monkeypatch.setenv("AETHOS_USERS_DIR", str(tmp_path / "users"))
    monkeypatch.setenv("AETHOS_CHECKPOINTS_DB", str(tmp_path / "checkpoints.db"))
    monkeypatch.setenv("AETHOS_MANAGED_FILES_DIR", str(tmp_path / "managed_files"))
    monkeypatch.setenv("AETHOS_CONFIG_HOME", str(tmp_path / "home-aethos"))
    monkeypatch.setenv("AETHOS_MANAGED_SETTINGS_DIR", str(tmp_path / "managed-settings"))
    get_settings.cache_clear()
    get_auth_repository.cache_clear()
    get_thread_store.cache_clear()
    get_file_store.cache_clear()
    get_rate_limiter.cache_clear()
    get_chat_service.cache_clear()


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    """Return a fresh temporary workspace root for each test."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws
