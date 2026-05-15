"""PostgreSQL connection repository backed by SQLAlchemy ORM sessions."""

from __future__ import annotations

import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.app.db.models.connections import (
    ConnectionAuditModel,
    ConnectionModel,
    ConnectionSecretModel,
    OAuthStateModel,
)

ProviderName = str
ConnectionStatus = str


def _now() -> int:
    return int(time.time())


def _dt_from_epoch(value: int) -> datetime:
    return datetime.fromtimestamp(value, tz=timezone.utc)


def _epoch_from_dt(value: datetime | None) -> int | None:
    if value is None:
        return None
    return int(value.timestamp())


class ConnectionRepositoryError(RuntimeError):
    """Base error raised by the PostgreSQL-backed connections repository."""


class ConnectionRepositorySchemaUnavailableError(ConnectionRepositoryError):
    """Raised when the PostgreSQL schema for native connections is unavailable."""


class OAuthStateInvalidError(ConnectionRepositoryError):
    """Raised when an OAuth state does not exist or belongs to another provider."""


class OAuthStateExpiredError(ConnectionRepositoryError):
    """Raised when an OAuth state exists but is no longer valid."""


def _raise_missing_postgres_schema(detail: str) -> None:
    raise ConnectionRepositorySchemaUnavailableError(
        "Native connections database schema is unavailable: "
        f"{detail}. Run database migrations before enabling PostgreSQL-backed connections."
    )


@dataclass(frozen=True)
class ConnectionRecord:
    id: str
    provider: ProviderName
    owner_user_id: str
    project_key: str
    account_label: str
    status: str
    capabilities: list[str]
    scopes: list[str]
    auth_type: str
    tools_enabled: bool
    created_at: int
    updated_at: int
    last_refresh_at: int | None
    last_error: str | None


def _connection_to_record(model: ConnectionModel) -> ConnectionRecord:
    return ConnectionRecord(
        id=model.id,
        provider=model.provider,
        owner_user_id=model.owner_user_id,
        project_key=model.project_key,
        account_label=model.account_label,
        status=model.status,
        capabilities=[item for item in model.capabilities_json if isinstance(item, str)],
        scopes=[item for item in model.scopes_json if isinstance(item, str)],
        auth_type=model.auth_type,
        tools_enabled=bool(model.tools_enabled),
        created_at=_epoch_from_dt(model.created_at) or _now(),
        updated_at=_epoch_from_dt(model.updated_at) or _now(),
        last_refresh_at=_epoch_from_dt(model.last_refresh_at),
        last_error=model.last_error,
    )


@dataclass(frozen=True)
class ConnectionRepository:
    session_factory: sessionmaker[Session]

    def __post_init__(self) -> None:
        self._ensure_schema()

    @property
    def engine(self) -> Engine:
        bind = self.session_factory.kw.get("bind")
        if isinstance(bind, Engine):
            return bind
        raise RuntimeError("ConnectionRepository session factory is not bound to an Engine.")

    def _ensure_schema(self) -> None:
        try:
            with self.session_factory() as session:
                inspector = inspect(session.bind)
                tables = set(inspector.get_table_names())
        except Exception as exc:
            _raise_missing_postgres_schema(str(exc))
        required_tables = {"connections", "connection_secrets", "connection_audit", "oauth_states"}
        missing = sorted(required_tables - tables)
        if missing:
            _raise_missing_postgres_schema(f"missing tables: {', '.join(missing)}")

    def list_connections(self, *, owner_user_id: str, project_key: str) -> list[ConnectionRecord]:
        with self.session_factory() as session:
            rows = session.scalars(
                select(ConnectionModel)
                .where(
                    ConnectionModel.owner_user_id == owner_user_id,
                    ConnectionModel.project_key == project_key,
                )
                .order_by(ConnectionModel.updated_at.desc(), ConnectionModel.created_at.desc())
            ).all()
        return [_connection_to_record(row) for row in rows]

    def get_connection(self, *, connection_id: str, owner_user_id: str | None = None) -> ConnectionRecord | None:
        with self.session_factory() as session:
            query = select(ConnectionModel).where(ConnectionModel.id == connection_id)
            if owner_user_id is not None:
                query = query.where(ConnectionModel.owner_user_id == owner_user_id)
            row = session.scalar(query)
        return _connection_to_record(row) if row is not None else None

    def get_default_connection(
        self,
        *,
        provider: ProviderName,
        owner_user_id: str,
        project_key: str,
    ) -> ConnectionRecord | None:
        with self.session_factory() as session:
            row = session.scalar(
                select(ConnectionModel)
                .where(
                    ConnectionModel.provider == provider,
                    ConnectionModel.owner_user_id == owner_user_id,
                    ConnectionModel.project_key == project_key,
                    ConnectionModel.status == "active",
                    ConnectionModel.tools_enabled.is_(True),
                )
                .order_by(ConnectionModel.updated_at.desc(), ConnectionModel.created_at.desc())
                .limit(1)
            )
        return _connection_to_record(row) if row is not None else None

    def find_connection_by_account(
        self,
        *,
        provider: ProviderName,
        owner_user_id: str,
        project_key: str,
        account_label: str,
    ) -> ConnectionRecord | None:
        with self.session_factory() as session:
            row = session.scalar(
                select(ConnectionModel)
                .where(
                    ConnectionModel.provider == provider,
                    ConnectionModel.owner_user_id == owner_user_id,
                    ConnectionModel.project_key == project_key,
                    ConnectionModel.account_label == account_label,
                )
                .order_by(ConnectionModel.updated_at.desc(), ConnectionModel.created_at.desc())
                .limit(1)
            )
        return _connection_to_record(row) if row is not None else None

    def save_connection(
        self,
        *,
        connection_id: str | None,
        provider: ProviderName,
        owner_user_id: str,
        project_key: str,
        account_label: str,
        status: ConnectionStatus,
        capabilities: list[str],
        scopes: list[str],
        auth_type: str = "oauth2",
        tools_enabled: bool = True,
        last_refresh_at: int | None = None,
        last_error: str | None = None,
    ) -> ConnectionRecord:
        now = _now()
        with self.session_factory.begin() as session:
            existing: ConnectionModel | None = None
            if connection_id is None:
                existing = session.scalar(
                    select(ConnectionModel).where(
                        ConnectionModel.provider == provider,
                        ConnectionModel.owner_user_id == owner_user_id,
                        ConnectionModel.project_key == project_key,
                        ConnectionModel.account_label == account_label,
                    )
                )
            model = session.get(ConnectionModel, connection_id) if connection_id else existing
            if model is None:
                model = ConnectionModel(
                    id=connection_id or (existing.id if existing is not None else f"conn_{uuid.uuid4().hex}"),
                    created_at=_dt_from_epoch(now),
                )
                session.add(model)
            model.provider = provider
            model.owner_user_id = owner_user_id
            model.project_key = project_key
            model.account_label = account_label
            model.status = status
            model.capabilities_json = capabilities
            model.scopes_json = scopes
            model.auth_type = auth_type
            model.tools_enabled = tools_enabled
            model.updated_at = _dt_from_epoch(now)
            model.last_refresh_at = _dt_from_epoch(last_refresh_at) if last_refresh_at is not None else None
            model.last_error = last_error
            session.flush()
            session.refresh(model)
            return _connection_to_record(model)

    def set_tools_enabled(self, *, connection_id: str, owner_user_id: str, enabled: bool) -> ConnectionRecord | None:
        with self.session_factory.begin() as session:
            model = session.get(ConnectionModel, connection_id)
            if model is None or model.owner_user_id != owner_user_id:
                return None
            model.tools_enabled = enabled
            model.updated_at = _dt_from_epoch(_now())
            session.flush()
            session.refresh(model)
            return _connection_to_record(model)

    def save_secret(self, *, connection_id: str, ciphertext: str, key_version: str = "v1") -> None:
        with self.session_factory.begin() as session:
            model = session.get(ConnectionSecretModel, connection_id)
            if model is None:
                model = ConnectionSecretModel(connection_id=connection_id)
                session.add(model)
            model.ciphertext = ciphertext
            model.key_version = key_version
            model.updated_at = _dt_from_epoch(_now())

    def load_secret(self, *, connection_id: str) -> str | None:
        with self.session_factory() as session:
            model = session.get(ConnectionSecretModel, connection_id)
            return model.ciphertext if model is not None else None

    def delete_connection(self, *, connection_id: str, owner_user_id: str) -> bool:
        with self.session_factory.begin() as session:
            model = session.get(ConnectionModel, connection_id)
            if model is None or model.owner_user_id != owner_user_id:
                return False
            session.delete(model)
            return True

    def create_oauth_state(
        self,
        *,
        provider: ProviderName,
        user_id: str,
        project_key: str,
        workspace_root: str,
        redirect_to: str | None,
        ttl_seconds: int = 900,
    ) -> str:
        state = secrets.token_urlsafe(32)
        with self.session_factory.begin() as session:
            session.add(
                OAuthStateModel(
                    state=state,
                    provider=provider,
                    payload_json={
                        "user_id": user_id,
                        "project_key": project_key,
                        "workspace_root": workspace_root,
                        "redirect_to": redirect_to,
                    },
                    expires_at=_dt_from_epoch(_now() + ttl_seconds),
                )
            )
        return state

    def consume_oauth_state(self, *, state: str, provider: ProviderName) -> dict[str, Any]:
        now = _now()
        with self.session_factory.begin() as session:
            record = session.get(OAuthStateModel, state)
            if record is None or record.provider != provider:
                raise OAuthStateInvalidError("OAuth state is invalid or already used.")
            payload = dict(record.payload_json or {}) if isinstance(record.payload_json, dict) else {}
            expires_at = _epoch_from_dt(record.expires_at) or 0
            session.delete(record)
        if expires_at < now:
            raise OAuthStateExpiredError("OAuth state has expired.")
        return payload

    def append_audit(
        self,
        *,
        connection_id: str,
        user_id: str,
        tool_name: str,
        action_kind: str,
        status: str,
        request_summary: str,
        error: str | None = None,
    ) -> None:
        with self.session_factory.begin() as session:
            session.add(
                ConnectionAuditModel(
                    id=f"audit_{uuid.uuid4().hex}",
                    connection_id=connection_id,
                    user_id=user_id,
                    tool_name=tool_name,
                    action_kind=action_kind,
                    status=status,
                    request_summary=request_summary,
                    created_at=_dt_from_epoch(_now()),
                    error=error,
                )
            )


__all__ = [
    "ConnectionRecord",
    "ConnectionRepository",
    "ConnectionRepositoryError",
    "ConnectionRepositorySchemaUnavailableError",
    "OAuthStateExpiredError",
    "OAuthStateInvalidError",
]
