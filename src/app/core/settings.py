"""Application settings and environment access."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_name: str = "Ethos API"
    app_version: str = "1.0.0"
    app_description: str = "OpenAI-compatible API for Ethos LangGraph agent"
    cors_allow_origins: list[str] | None = None
    cors_allow_methods: list[str] | None = None
    cors_allow_headers: list[str] | None = None
    # File-based storage layout. Defaults live under ~/.ethos; env overrides preserve legacy deployments.
    users_dir: Path = Path.home() / ".ethos" / "users"
    checkpoints_dir: Path = Path.home() / ".ethos" / "projects"
    security_state_dir: Path = Path.home() / ".ethos" / "security"
    ethos_config_dir: Path = Path.home() / ".ethos"
    ethos_managed_settings_dir: Path = Path("/etc/ethos")
    session_ttl_seconds: int = 30 * 24 * 60 * 60  # 30 days sliding expiry
    allow_custom_provider_endpoints: bool = False
    auth_guest_session_limit: int = 10
    auth_guest_session_window_seconds: int = 60
    chat_requests_limit: int = 20
    chat_requests_window_seconds: int = 60
    thread_creations_limit: int = 20
    thread_creations_window_seconds: int = 3600
    file_write_limit: int = 20
    file_write_window_seconds: int = 60
    terminal_create_limit: int = 5
    terminal_create_window_seconds: int = 60
    terminal_connect_limit: int = 10
    terminal_connect_window_seconds: int = 60
    managed_file_max_bytes: int = 10 * 1024 * 1024
    managed_file_total_bytes_per_user: int = 100 * 1024 * 1024


def _csv_env(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        return default
    return value if value > 0 else default


def _default_managed_settings_dir() -> Path:
    system = os.name
    if system == "nt":
        return Path(r"C:\Program Files\Ethos")
    if sys.platform == "darwin":
        return Path("/Library/Application Support/Ethos")
    return Path("/etc/ethos")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _workspace = Path(os.getenv("ETHOS_WORKSPACE_DIR", str(Path.cwd() / "workspace")))
    _config_home = Path(os.getenv("ETHOS_CONFIG_HOME", str(Path.home() / ".ethos")))
    return Settings(
        cors_allow_origins=_csv_env(
            "ETHOS_CORS_ALLOW_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173",
        ),
        cors_allow_methods=_csv_env("ETHOS_CORS_ALLOW_METHODS", "GET,POST,PUT,PATCH,DELETE,OPTIONS"),
        cors_allow_headers=_csv_env("ETHOS_CORS_ALLOW_HEADERS", "Authorization,Content-Type,Accept"),
        users_dir=Path(os.getenv("ETHOS_USERS_DIR", str(_config_home / "users"))),
        checkpoints_dir=Path(os.getenv("ETHOS_CHECKPOINTS_DIR", str(_config_home / "projects"))),
        security_state_dir=Path(os.getenv("ETHOS_SECURITY_STATE_DIR", str(_config_home / "security"))),
        ethos_config_dir=_config_home,
        ethos_managed_settings_dir=Path(
            os.getenv("ETHOS_MANAGED_SETTINGS_DIR", str(_default_managed_settings_dir()))
        ),
        session_ttl_seconds=_int_env("ETHOS_SESSION_TTL_SECONDS", 30 * 24 * 60 * 60),
        allow_custom_provider_endpoints=_bool_env("ETHOS_ALLOW_CUSTOM_PROVIDER_ENDPOINTS", False),
        auth_guest_session_limit=_int_env("ETHOS_AUTH_GUEST_SESSION_LIMIT", 10),
        auth_guest_session_window_seconds=_int_env("ETHOS_AUTH_GUEST_SESSION_WINDOW_SECONDS", 60),
        chat_requests_limit=_int_env("ETHOS_CHAT_REQUESTS_LIMIT", 20),
        chat_requests_window_seconds=_int_env("ETHOS_CHAT_REQUESTS_WINDOW_SECONDS", 60),
        thread_creations_limit=_int_env("ETHOS_THREAD_CREATIONS_LIMIT", 20),
        thread_creations_window_seconds=_int_env("ETHOS_THREAD_CREATIONS_WINDOW_SECONDS", 3600),
        file_write_limit=_int_env("ETHOS_FILE_WRITE_LIMIT", 20),
        file_write_window_seconds=_int_env("ETHOS_FILE_WRITE_WINDOW_SECONDS", 60),
        terminal_create_limit=_int_env("ETHOS_TERMINAL_CREATE_LIMIT", 5),
        terminal_create_window_seconds=_int_env("ETHOS_TERMINAL_CREATE_WINDOW_SECONDS", 60),
        terminal_connect_limit=_int_env("ETHOS_TERMINAL_CONNECT_LIMIT", 10),
        terminal_connect_window_seconds=_int_env("ETHOS_TERMINAL_CONNECT_WINDOW_SECONDS", 60),
        managed_file_max_bytes=_int_env("ETHOS_MANAGED_FILE_MAX_BYTES", 10 * 1024 * 1024),
        managed_file_total_bytes_per_user=_int_env("ETHOS_MANAGED_FILE_TOTAL_BYTES_PER_USER", 100 * 1024 * 1024),
    )
