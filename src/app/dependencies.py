from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, Header, HTTPException, Request, WebSocket
from langgraph.checkpoint.base import BaseCheckpointSaver

from src.app.core.settings import get_settings
from src.app.modules.auth.repository import AuthRepository, AuthSession, AuthUser
from src.app.services.daytona_manager import DaytonaSessionManager
from src.app.services.file_store import FileStore
from src.app.services.rate_limiter import RateLimitRule, RateLimiter
from src.app.services.thread_store import ThreadStore


@lru_cache(maxsize=1)
def get_file_store() -> FileStore:
    root = Path(os.getenv("ETHOS_MANAGED_FILES_DIR", Path.cwd() / "workspace" / "managed_files"))
    return FileStore(root=root)


@lru_cache(maxsize=1)
def get_auth_repository() -> AuthRepository:
    settings = get_settings()
    return AuthRepository(
        root=settings.users_dir,
        session_ttl_seconds=settings.session_ttl_seconds,
        legacy_root=settings.security_state_dir,
    )


@lru_cache(maxsize=1)
def get_thread_store() -> ThreadStore:
    settings = get_settings()
    return ThreadStore(
        root=settings.users_dir,
        legacy_root=settings.security_state_dir,
    )


@lru_cache(maxsize=1)
def get_rate_limiter() -> RateLimiter:
    return RateLimiter()


def get_open_terminal_base_url() -> str:
    return os.getenv("OPEN_TERMINAL_URL", "http://localhost:8000").rstrip("/")


def get_open_terminal_api_key() -> str:
    return os.getenv("OPEN_TERMINAL_API_KEY", "")


def get_terminal_name() -> str:
    return os.getenv("ETHOS_TERMINAL_NAME", "Ethos Sandbox")


def get_checkpointer(request: Request) -> BaseCheckpointSaver:
    """Return the shared MemorySaver stored on app.state."""
    return request.app.state.checkpointer


def get_daytona_session_manager(request: Request) -> DaytonaSessionManager:
    return request.app.state.daytona_manager


def _read_bearer_token(value: str | None) -> str | None:
    if not value:
        return None
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def get_current_auth_session(
    authorization: str | None = Header(default=None),
    repo: AuthRepository = Depends(get_auth_repository),
) -> AuthSession:
    token = _read_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    session = repo.get_session(token)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return session


def get_current_user(
    session: AuthSession = Depends(get_current_auth_session),
    repo: AuthRepository = Depends(get_auth_repository),
) -> AuthUser:
    user = repo.get_user(session.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def require_websocket_user(websocket: WebSocket) -> AuthUser:
    repo = get_auth_repository()
    token = _read_bearer_token(websocket.headers.get("authorization"))
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    session = repo.get_session(token)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    user = repo.get_user(session.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def _rate_limit_key_from_request(request: Request, *, user: AuthUser | None = None) -> str:
    if user is not None:
        return f"user:{user.id}"
    client_host = request.client.host if request.client else "unknown"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_host = forwarded.split(",")[0].strip() or client_host
    return f"ip:{client_host}"


def enforce_rate_limit(
    *,
    request: Request,
    rule: RateLimitRule,
    limiter: RateLimiter | None = None,
    user: AuthUser | None = None,
) -> None:
    active_limiter = limiter or get_rate_limiter()
    allowed, retry_after = active_limiter.hit(rule=rule, key=_rate_limit_key_from_request(request, user=user))
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded for {rule.scope}. Retry in {retry_after}s.",
            headers={"Retry-After": str(retry_after)},
        )
