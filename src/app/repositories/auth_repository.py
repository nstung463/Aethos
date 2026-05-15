"""PostgreSQL auth repository backed by SQLAlchemy ORM sessions."""

from __future__ import annotations

import hashlib
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from src.app.db.models.auth import AuthIdentityModel, AuthSessionModel, UserModel
from src.app.db.models.connections import OAuthStateModel
from src.app.features.auth.models import DEFAULT_PERMISSION_DEFAULTS, AuthSession, AuthUser


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now() -> int:
    return int(time.time())


def _dt_from_epoch(value: int) -> datetime:
    return datetime.fromtimestamp(value, tz=timezone.utc)


def _epoch_from_dt(value: datetime | None) -> int | None:
    if value is None:
        return None
    return int(value.timestamp())


@dataclass(frozen=True)
class AuthRepository:
    session_factory: sessionmaker[Session]
    session_ttl_seconds: int = 30 * 24 * 60 * 60
    session_refresh_interval_seconds: int = 5 * 60

    def _normalize_permission_defaults(self, defaults: Any) -> dict[str, Any]:
        if not isinstance(defaults, dict):
            defaults = {}
        return {
            "mode": defaults.get("mode") if isinstance(defaults.get("mode"), str) else None,
            "working_directories": [item for item in (defaults.get("working_directories") or []) if isinstance(item, str)],
            "rules": [item for item in (defaults.get("rules") or []) if isinstance(item, dict)],
        }

    def _user_to_payload(self, user: UserModel | None) -> AuthUser | None:
        if user is None:
            return None
        return AuthUser(id=user.id, display_name=user.display_name, created_at=_epoch_from_dt(user.created_at) or _now())

    def _session_to_payload(self, token: str, session: AuthSessionModel) -> AuthSession:
        return AuthSession(
            token=token,
            user_id=session.user_id,
            created_at=_epoch_from_dt(session.created_at) or _now(),
            expires_at=_epoch_from_dt(session.expires_at) or _now(),
            last_used_at=_epoch_from_dt(session.last_used_at) or _now(),
        )

    def _should_refresh_session(self, last_used_at: int, expires_at: int, now: int) -> bool:
        if self.session_refresh_interval_seconds <= 0:
            return True
        if now - last_used_at >= self.session_refresh_interval_seconds:
            return True
        return expires_at - now <= self.session_refresh_interval_seconds

    def create_guest_session(self, *, display_name: str | None = None) -> tuple[AuthUser, AuthSession]:
        now = _now()
        user_model = UserModel(
            id=f"user_{uuid.uuid4().hex}",
            display_name=(display_name or "Guest").strip() or "Guest",
            created_at=_dt_from_epoch(now),
            permission_defaults=dict(DEFAULT_PERMISSION_DEFAULTS),
        )
        token = secrets.token_urlsafe(32)
        session_model = AuthSessionModel(
            id=f"sess_{uuid.uuid4().hex}",
            user_id=user_model.id,
            session_token_hash=_hash_token(token),
            created_at=_dt_from_epoch(now),
            expires_at=_dt_from_epoch(now + self.session_ttl_seconds),
            last_used_at=_dt_from_epoch(now),
            revoked_at=None,
        )
        with self.session_factory.begin() as session:
            session.add(user_model)
            session.add(session_model)
        return self._user_to_payload(user_model) or AuthUser(user_model.id, user_model.display_name, now), self._session_to_payload(token, session_model)

    def create_session_for_user(self, *, user_id: str) -> AuthSession:
        now = _now()
        token = secrets.token_urlsafe(32)
        session_model = AuthSessionModel(
            id=f"sess_{uuid.uuid4().hex}",
            user_id=user_id,
            session_token_hash=_hash_token(token),
            created_at=_dt_from_epoch(now),
            expires_at=_dt_from_epoch(now + self.session_ttl_seconds),
            last_used_at=_dt_from_epoch(now),
            revoked_at=None,
        )
        with self.session_factory.begin() as session:
            session.add(session_model)
        return self._session_to_payload(token, session_model)

    def revoke_session(self, token: str) -> bool:
        token_hash = _hash_token(token)
        now = _dt_from_epoch(_now())
        with self.session_factory.begin() as session:
            record = session.scalar(select(AuthSessionModel).where(AuthSessionModel.session_token_hash == token_hash))
            if record is None or record.revoked_at is not None:
                return False
            record.revoked_at = now
            return True

    def find_identity(self, *, provider: str, provider_subject: str) -> AuthUser | None:
        with self.session_factory() as session:
            identity = session.scalar(
                select(AuthIdentityModel).where(
                    AuthIdentityModel.provider == provider,
                    AuthIdentityModel.provider_subject == provider_subject,
                )
            )
            if identity is None:
                return None
            return self._user_to_payload(identity.user)

    def link_identity(self, *, user_id: str, provider: str, provider_subject: str, email: str | None, profile: dict[str, Any]) -> AuthUser:
        with self.session_factory.begin() as session:
            existing = session.scalar(
                select(AuthIdentityModel).where(
                    AuthIdentityModel.provider == provider,
                    AuthIdentityModel.provider_subject == provider_subject,
                )
            )
            if existing is None:
                existing = AuthIdentityModel(
                    id=f"ident_{uuid.uuid4().hex}",
                    user_id=user_id,
                    provider=provider,
                    provider_subject=provider_subject,
                    email=email,
                    profile=profile or {},
                )
                session.add(existing)
            else:
                existing.user_id = user_id
                existing.email = email
                existing.profile = profile or {}
            user = session.get(UserModel, user_id)
            if user is None:
                raise ValueError("Linked identity to missing user")
            session.flush()
            return self._user_to_payload(user) or AuthUser(user.id, user.display_name, _now())

    def create_user_with_identity(self, *, provider: str, provider_subject: str, email: str | None, display_name: str, profile: dict[str, Any]) -> AuthUser:
        now = _now()
        user = UserModel(
            id=f"user_{uuid.uuid4().hex}",
            display_name=display_name.strip() or "User",
            created_at=_dt_from_epoch(now),
            permission_defaults=dict(DEFAULT_PERMISSION_DEFAULTS),
        )
        with self.session_factory.begin() as session:
            session.add(user)
        return self.link_identity(
            user_id=user.id,
            provider=provider,
            provider_subject=provider_subject,
            email=email,
            profile=profile,
        )

    def create_oauth_state(self, *, provider: str, payload: dict[str, Any], ttl_seconds: int = 900) -> str:
        state = secrets.token_urlsafe(32)
        with self.session_factory.begin() as session:
            session.add(
                OAuthStateModel(
                    state=state,
                    provider=provider,
                    payload_json=payload or {},
                    expires_at=_dt_from_epoch(_now() + ttl_seconds),
                )
            )
        return state

    def consume_oauth_state(self, *, provider: str, state: str) -> dict[str, Any] | None:
        now = _now()
        with self.session_factory.begin() as session:
            record = session.get(OAuthStateModel, state)
            if record is None or record.provider != provider:
                return None
            payload = dict(record.payload_json or {}) if isinstance(record.payload_json, dict) else None
            expires_at = _epoch_from_dt(record.expires_at) or 0
            session.delete(record)
        if expires_at < now:
            return None
        return payload

    def get_session(self, token: str) -> AuthSession | None:
        token_hash = _hash_token(token)
        now = _now()
        with self.session_factory.begin() as session:
            record = session.scalar(select(AuthSessionModel).where(AuthSessionModel.session_token_hash == token_hash))
            if record is None or record.revoked_at is not None:
                return None
            payload = self._session_to_payload(token, record)
            if payload.expires_at and now > payload.expires_at:
                record.revoked_at = _dt_from_epoch(now)
                return None
            if not self._should_refresh_session(payload.last_used_at, payload.expires_at, now):
                return payload
            record.last_used_at = _dt_from_epoch(now)
            record.expires_at = _dt_from_epoch(now + self.session_ttl_seconds)
            return self._session_to_payload(token, record)

    def get_user(self, user_id: str) -> AuthUser | None:
        with self.session_factory() as session:
            return self._user_to_payload(session.get(UserModel, user_id))

    def get_permission_defaults(self, user_id: str) -> dict[str, Any]:
        with self.session_factory() as session:
            user = session.get(UserModel, user_id)
            if user is None:
                return dict(DEFAULT_PERMISSION_DEFAULTS)
            return self._normalize_permission_defaults(user.permission_defaults)

    def update_permission_defaults(self, *, user_id: str, defaults: dict[str, Any]) -> dict[str, Any] | None:
        normalized = self._normalize_permission_defaults(defaults)
        with self.session_factory.begin() as session:
            user = session.get(UserModel, user_id)
            if user is None:
                return None
            user.permission_defaults = normalized
            return normalized


__all__ = ["AuthRepository"]
