from __future__ import annotations

import os
from collections.abc import Generator
from functools import lru_cache

from fastapi import Depends, Header, HTTPException, Request, WebSocket
from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy.orm import Session, sessionmaker

from src.app.core.settings import get_settings
from src.app.features.auth.models import AuthSession, AuthUser
from src.app.features.auth.types import AuthRepositoryProtocol, AuthRepositoryProvider
from src.app.repositories.thread_repository import ThreadRepository
from src.app.repositories.thread_types import ThreadRepositoryProtocol
from src.app.services.daytona_manager import DaytonaSessionManager
from src.app.db.session import session_dependency
from src.app.services.database import get_sqlalchemy_session_factory
from src.app.services.file_store import FileStore
from src.app.services.rate_limiter import RateLimitRule, RateLimiter
from src.app.services.routing_file_store import RoutingFileStore
from src.app.services.storage_paths import StoragePathsService


def build_file_store_for_workspace(workspace_root: str | os.PathLike[str] | None = None) -> FileStore:
    storage = StoragePathsService()
    storage.ensure_project_metadata(workspace_root)
    return FileStore(root=storage.files_dir(workspace_root))


@lru_cache(maxsize=1)
def get_file_store() -> FileStore | RoutingFileStore:
    storage = StoragePathsService()
    return RoutingFileStore(storage=storage)


@lru_cache(maxsize=1)
def get_auth_repository() -> AuthRepositoryProtocol:
    settings = get_settings()
    provider = AuthRepositoryProvider(settings=settings)
    return provider.create()


@lru_cache(maxsize=1)
def get_thread_store() -> ThreadRepositoryProtocol:
    settings = get_settings()
    storage = StoragePathsService(settings)
    return ThreadRepository(session_factory=get_database_session_factory(), storage=storage)


@lru_cache(maxsize=1)
def get_database_session_factory() -> sessionmaker[Session]:
    return get_sqlalchemy_session_factory(get_settings())


def get_database_session() -> Generator[Session, None, None]:
    yield from session_dependency(get_database_session_factory())


@lru_cache(maxsize=1)
def get_rate_limiter() -> RateLimiter:
    return RateLimiter()





def get_checkpointer(request: Request) -> BaseCheckpointSaver:
    """Return the shared PostgreSQL-backed checkpoint saver stored on app.state."""
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
    request: Request,
    authorization: str | None = Header(default=None),
    repo: AuthRepositoryProtocol = Depends(get_auth_repository),
) -> AuthSession:
    token = _read_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    session = repo.get_session(token)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return session


def get_current_user(
    request: Request,
    session: AuthSession = Depends(get_current_auth_session),
    repo: AuthRepositoryProtocol = Depends(get_auth_repository),
) -> AuthUser:
    user = repo.get_user(session.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    request.state.user_id = user.id
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
