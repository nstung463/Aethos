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
    app_name: str = "Aethos API"
    app_version: str = "1.0.0"
    app_description: str = "OpenAI-compatible API for Aethos LangGraph agent"
    cors_allow_origins: list[str] | None = None
    cors_allow_methods: list[str] | None = None
    cors_allow_headers: list[str] | None = None
    # File-based storage layout. Defaults live under ~/.aethos.
    users_dir: Path = Path.home() / ".aethos" / "users"
    checkpoints_dir: Path = Path.home() / ".aethos" / "projects"
    security_state_dir: Path = Path.home() / ".aethos" / "security"
    aethos_config_dir: Path = Path.home() / ".aethos"
    aethos_managed_settings_dir: Path = Path("/etc/aethos")
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
    managed_file_max_bytes: int = 10 * 1024 * 1024
    managed_file_total_bytes_per_user: int = 100 * 1024 * 1024
    aethos_public_base_url: str | None = None
    aethos_secrets_key: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
    slack_client_id: str | None = None
    slack_client_secret: str | None = None
    microsoft_client_id: str | None = None
    microsoft_client_secret: str | None = None
    microsoft_tenant_id: str | None = None


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
        return Path(r"C:\Program Files\Aethos")
    if sys.platform == "darwin":
        return Path("/Library/Application Support/Aethos")
    return Path("/etc/aethos")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _workspace = Path(os.getenv("AETHOS_WORKSPACE_DIR", str(Path.cwd() / "workspace")))
    _config_home = Path(os.getenv("AETHOS_CONFIG_HOME", str(Path.home() / ".aethos")))
    return Settings(
        cors_allow_origins=_csv_env(
            "AETHOS_CORS_ALLOW_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173",
        ),
        cors_allow_methods=_csv_env("AETHOS_CORS_ALLOW_METHODS", "GET,POST,PUT,PATCH,DELETE,OPTIONS"),
        cors_allow_headers=_csv_env("AETHOS_CORS_ALLOW_HEADERS", "Authorization,Content-Type,Accept"),
        users_dir=Path(os.getenv("AETHOS_USERS_DIR", str(_config_home / "users"))),
        checkpoints_dir=Path(os.getenv("AETHOS_CHECKPOINTS_DIR", str(_config_home / "projects"))),
        security_state_dir=Path(os.getenv("AETHOS_SECURITY_STATE_DIR", str(_config_home / "security"))),
        aethos_config_dir=_config_home,
        aethos_managed_settings_dir=Path(
            os.getenv("AETHOS_MANAGED_SETTINGS_DIR", str(_default_managed_settings_dir()))
        ),
        session_ttl_seconds=_int_env("AETHOS_SESSION_TTL_SECONDS", 30 * 24 * 60 * 60),
        allow_custom_provider_endpoints=_bool_env("AETHOS_ALLOW_CUSTOM_PROVIDER_ENDPOINTS", False),
        auth_guest_session_limit=_int_env("AETHOS_AUTH_GUEST_SESSION_LIMIT", 10),
        auth_guest_session_window_seconds=_int_env("AETHOS_AUTH_GUEST_SESSION_WINDOW_SECONDS", 60),
        chat_requests_limit=_int_env("AETHOS_CHAT_REQUESTS_LIMIT", 20),
        chat_requests_window_seconds=_int_env("AETHOS_CHAT_REQUESTS_WINDOW_SECONDS", 60),
        thread_creations_limit=_int_env("AETHOS_THREAD_CREATIONS_LIMIT", 20),
        thread_creations_window_seconds=_int_env("AETHOS_THREAD_CREATIONS_WINDOW_SECONDS", 3600),
        file_write_limit=_int_env("AETHOS_FILE_WRITE_LIMIT", 20),
        file_write_window_seconds=_int_env("AETHOS_FILE_WRITE_WINDOW_SECONDS", 60),
        managed_file_max_bytes=_int_env("AETHOS_MANAGED_FILE_MAX_BYTES", 10 * 1024 * 1024),
        managed_file_total_bytes_per_user=_int_env("AETHOS_MANAGED_FILE_TOTAL_BYTES_PER_USER", 100 * 1024 * 1024),
        aethos_public_base_url=os.getenv("AETHOS_PUBLIC_BASE_URL"),
        aethos_secrets_key=os.getenv("AETHOS_SECRETS_KEY"),
        google_client_id=os.getenv("GOOGLE_CLIENT_ID"),
        google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        slack_client_id=os.getenv("SLACK_CLIENT_ID"),
        slack_client_secret=os.getenv("SLACK_CLIENT_SECRET"),
        microsoft_client_id=os.getenv("MICROSOFT_CLIENT_ID"),
        microsoft_client_secret=os.getenv("MICROSOFT_CLIENT_SECRET"),
        microsoft_tenant_id=os.getenv("MICROSOFT_TENANT_ID"),
    )
