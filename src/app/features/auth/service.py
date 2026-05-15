"""Business logic for authentication."""

from __future__ import annotations

from src.app.features.auth.models import AuthSession, AuthUser
from src.app.features.auth.types import AuthRepositoryProtocol


class AuthService:
    def __init__(self, repo: AuthRepositoryProtocol) -> None:
        self._repo = repo

    def create_guest_session(self, *, display_name: str | None = None) -> tuple[AuthUser, AuthSession]:
        return self._repo.create_guest_session(display_name=display_name)
