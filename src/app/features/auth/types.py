"""Auth repository interfaces and provider wiring for the ORM-backed runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from src.app.core.settings import Settings
from src.app.features.auth.models import AuthSession, AuthUser
from src.app.repositories.auth_repository import AuthRepository as ORMAuthRepository
from src.app.services.database import get_database_config, get_sqlalchemy_session_factory
from src.app.services.storage_paths import StoragePathsService


OAuthStatePayload = dict[str, Any]


@runtime_checkable
class AuthRepositoryProtocol(Protocol):
    """Persistence contract for auth users, sessions, and permission defaults."""

    def create_guest_session(
        self, *, display_name: str | None = None
    ) -> tuple[AuthUser, AuthSession]:
        ...

    def get_session(self, token: str) -> AuthSession | None:
        ...

    def get_user(self, user_id: str) -> AuthUser | None:
        ...

    def create_session_for_user(self, *, user_id: str) -> AuthSession:
        ...

    def revoke_session(self, token: str) -> bool:
        ...

    def find_identity(self, *, provider: str, provider_subject: str) -> AuthUser | None:
        ...

    def link_identity(
        self,
        *,
        user_id: str,
        provider: str,
        provider_subject: str,
        email: str | None,
        profile: dict[str, Any],
    ) -> AuthUser:
        ...

    def create_user_with_identity(
        self,
        *,
        provider: str,
        provider_subject: str,
        email: str | None,
        display_name: str,
        profile: dict[str, Any],
    ) -> AuthUser:
        ...

    def create_oauth_state(self, *, provider: str, payload: OAuthStatePayload, ttl_seconds: int = 900) -> str:
        ...

    def consume_oauth_state(self, *, provider: str, state: str) -> OAuthStatePayload | None:
        ...

    def get_permission_defaults(self, user_id: str) -> dict[str, Any]:
        ...

    def update_permission_defaults(
        self, *, user_id: str, defaults: dict[str, Any]
    ) -> dict[str, Any] | None:
        ...


@dataclass(frozen=True)
class AuthRepositoryProvider:
    """Factory for the canonical ORM-backed auth repository."""

    settings: Settings
    storage: StoragePathsService | None = None

    def create(self) -> AuthRepositoryProtocol:
        database = get_database_config(self.settings)
        if not database.enabled or not database.is_configured:
            raise ValueError(
                "Auth now requires PostgreSQL. Set AETHOS_DATABASE_ENABLED=true and AETHOS_DATABASE_URL."
            )
        return ORMAuthRepository(
            session_factory=get_sqlalchemy_session_factory(self.settings),
            session_ttl_seconds=self.settings.session_ttl_seconds,
        )
