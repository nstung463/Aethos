"""Native OAuth-backed connections for integrations such as Google and Slack."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException

from src.app.core.settings import Settings, get_settings
from src.app.services.storage_paths import StoragePathsService

ProviderName = Literal["google", "google-gmail", "google-drive", "google-calendar", "google-sheets", "slack"]
AuthorizableProviderName = Literal["google-gmail", "google-drive", "google-calendar", "google-sheets", "slack"]
ConnectionStatus = Literal["active", "error", "revoked"]
SUPPORTED_CONNECTION_PROVIDERS: tuple[AuthorizableProviderName, ...] = (
    "google-gmail",
    "google-drive",
    "google-calendar",
    "google-sheets",
    "slack",
)

_GOOGLE_IDENTITY_SCOPES = [
    "openid",
    "email",
    "profile",
]
GOOGLE_CONNECTOR_SCOPES: dict[str, list[str]] = {
    "google-gmail": [
        *_GOOGLE_IDENTITY_SCOPES,
        "https://www.googleapis.com/auth/gmail.modify",
    ],
    "google-drive": [
        *_GOOGLE_IDENTITY_SCOPES,
        "https://www.googleapis.com/auth/drive.readonly",
    ],
    "google-calendar": [
        *_GOOGLE_IDENTITY_SCOPES,
        "https://www.googleapis.com/auth/calendar",
    ],
    "google-sheets": [
        *_GOOGLE_IDENTITY_SCOPES,
        "https://www.googleapis.com/auth/spreadsheets",
    ],
}
GOOGLE_SCOPES = [
    *_GOOGLE_IDENTITY_SCOPES,
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/spreadsheets",
]
GOOGLE_CONNECTOR_CAPABILITIES: dict[str, list[str]] = {
    "google-gmail": ["gmail"],
    "google-drive": ["drive"],
    "google-calendar": ["calendar"],
    "google-sheets": ["sheets"],
    "google": ["gmail", "drive", "calendar", "sheets"],
}
SLACK_SCOPES = [
    "channels:read",
    "groups:read",
    "chat:write",
    "search:read",
]
WRITE_TOOL_NAMES = {
    "gmail_send_message",
    "calendar_create_event",
    "sheets_append_values",
    "slack_post_message",
}


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


@dataclass(frozen=True)
class AuthorizationStart:
    provider: ProviderName
    authorization_url: str
    state: str


def _now() -> int:
    return int(time.time())


def _ensure_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _json_list(text: str | None) -> list[str]:
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    return [item for item in data if isinstance(item, str)] if isinstance(data, list) else []


def _is_google_provider(provider: str) -> bool:
    return provider == "google" or provider in GOOGLE_CONNECTOR_SCOPES


def _google_scopes_for_provider(provider: str) -> list[str]:
    return GOOGLE_CONNECTOR_SCOPES.get(provider, GOOGLE_SCOPES)


def _google_capabilities_for_provider(provider: str) -> list[str]:
    return GOOGLE_CONNECTOR_CAPABILITIES.get(provider, GOOGLE_CONNECTOR_CAPABILITIES["google"])


def _connection_from_row(row: sqlite3.Row) -> ConnectionRecord:
    return ConnectionRecord(
        id=str(row["id"]),
        provider=str(row["provider"]),
        owner_user_id=str(row["owner_user_id"]),
        project_key=str(row["project_key"]),
        account_label=str(row["account_label"]),
        status=str(row["status"]),
        capabilities=_json_list(row["capabilities_json"]),
        scopes=_json_list(row["scopes_json"]),
        auth_type=str(row["auth_type"]),
        tools_enabled=bool(row["tools_enabled"]) if "tools_enabled" in row.keys() else True,
        created_at=int(row["created_at"]),
        updated_at=int(row["updated_at"]),
        last_refresh_at=int(row["last_refresh_at"]) if row["last_refresh_at"] is not None else None,
        last_error=str(row["last_error"]) if row["last_error"] else None,
    )


class SecretVault:
    """Versioned local secret envelope for access and refresh tokens."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def _key(self) -> bytes:
        raw = self._settings.ethos_secrets_key
        if not raw:
            raise HTTPException(status_code=503, detail="ETHOS_SECRETS_KEY is required for native connections.")
        return hashlib.sha256(raw.encode("utf-8")).digest()

    @staticmethod
    def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
        stream = bytearray()
        counter = 0
        while len(stream) < length:
            counter_bytes = counter.to_bytes(8, "big")
            stream.extend(hashlib.blake2b(nonce + counter_bytes, key=key, digest_size=32).digest())
            counter += 1
        return bytes(stream[:length])

    def encrypt(self, payload: dict[str, Any]) -> str:
        key = self._key()
        nonce = secrets.token_bytes(16)
        plaintext = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        keystream = self._keystream(key, nonce, len(plaintext))
        ciphertext = bytes(a ^ b for a, b in zip(plaintext, keystream, strict=False))
        mac = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
        envelope = {
            "version": 1,
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            "mac": base64.b64encode(mac).decode("ascii"),
        }
        return json.dumps(envelope, separators=(",", ":"))

    def decrypt(self, envelope_text: str) -> dict[str, Any]:
        key = self._key()
        try:
            envelope = json.loads(envelope_text)
            nonce = base64.b64decode(str(envelope["nonce"]))
            ciphertext = base64.b64decode(str(envelope["ciphertext"]))
            received_mac = base64.b64decode(str(envelope["mac"]))
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Stored connection secret is invalid.") from exc
        expected_mac = hmac.new(key, nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(received_mac, expected_mac):
            raise HTTPException(status_code=500, detail="Stored connection secret failed integrity check.")
        keystream = self._keystream(key, nonce, len(ciphertext))
        plaintext = bytes(a ^ b for a, b in zip(ciphertext, keystream, strict=False))
        try:
            data = json.loads(plaintext.decode("utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Stored connection secret is unreadable.") from exc
        return _ensure_dict(data)


class ConnectionRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS connections (
                    id TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    owner_user_id TEXT NOT NULL,
                    project_key TEXT NOT NULL,
                    account_label TEXT NOT NULL,
                    status TEXT NOT NULL,
                    capabilities_json TEXT NOT NULL,
                    scopes_json TEXT NOT NULL,
                    auth_type TEXT NOT NULL,
                    tools_enabled INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    last_refresh_at INTEGER,
                    last_error TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_connections_owner_project
                    ON connections(owner_user_id, project_key, provider);

                CREATE TABLE IF NOT EXISTS connection_secrets (
                    connection_id TEXT PRIMARY KEY,
                    ciphertext TEXT NOT NULL,
                    key_version TEXT NOT NULL,
                    updated_at INTEGER NOT NULL,
                    FOREIGN KEY(connection_id) REFERENCES connections(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS connection_audit (
                    id TEXT PRIMARY KEY,
                    connection_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    action_kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    request_summary TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    error TEXT,
                    FOREIGN KEY(connection_id) REFERENCES connections(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS oauth_states (
                    state TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    project_key TEXT NOT NULL,
                    workspace_root TEXT NOT NULL,
                    redirect_to TEXT,
                    expires_at INTEGER NOT NULL
                );
                """
            )
            columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(connections)").fetchall()}
            if "tools_enabled" not in columns:
                conn.execute("ALTER TABLE connections ADD COLUMN tools_enabled INTEGER NOT NULL DEFAULT 1")

    def list_connections(self, *, owner_user_id: str, project_key: str) -> list[ConnectionRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM connections
                WHERE owner_user_id = ? AND project_key = ?
                ORDER BY updated_at DESC, created_at DESC
                """,
                (owner_user_id, project_key),
            ).fetchall()
        return [_connection_from_row(row) for row in rows]

    def get_connection(self, *, connection_id: str, owner_user_id: str | None = None) -> ConnectionRecord | None:
        sql = "SELECT * FROM connections WHERE id = ?"
        params: list[Any] = [connection_id]
        if owner_user_id is not None:
            sql += " AND owner_user_id = ?"
            params.append(owner_user_id)
        with self._connect() as conn:
            row = conn.execute(sql, tuple(params)).fetchone()
        return _connection_from_row(row) if row else None

    def get_default_connection(
        self,
        *,
        provider: ProviderName,
        owner_user_id: str,
        project_key: str,
    ) -> ConnectionRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM connections
                WHERE provider = ? AND owner_user_id = ? AND project_key = ? AND status = 'active' AND tools_enabled = 1
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 1
                """,
                (provider, owner_user_id, project_key),
            ).fetchone()
        return _connection_from_row(row) if row else None

    def find_connection_by_account(
        self,
        *,
        provider: ProviderName,
        owner_user_id: str,
        project_key: str,
        account_label: str,
    ) -> ConnectionRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM connections
                WHERE provider = ? AND owner_user_id = ? AND project_key = ? AND account_label = ?
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 1
                """,
                (provider, owner_user_id, project_key, account_label),
            ).fetchone()
        return _connection_from_row(row) if row else None

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
        created_at = now
        existing = None
        if connection_id is None:
            existing = self.find_connection_by_account(
                provider=provider,
                owner_user_id=owner_user_id,
                project_key=project_key,
                account_label=account_label,
            )
        resolved_id = connection_id or (existing.id if existing is not None else f"conn_{uuid.uuid4().hex}")
        if connection_id:
            prior = self.get_connection(connection_id=connection_id)
            if prior is not None:
                created_at = prior.created_at
        elif existing is not None:
            created_at = existing.created_at
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO connections (
                    id, provider, owner_user_id, project_key, account_label, status,
                    capabilities_json, scopes_json, auth_type, tools_enabled, created_at, updated_at,
                    last_refresh_at, last_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    provider = excluded.provider,
                    owner_user_id = excluded.owner_user_id,
                    project_key = excluded.project_key,
                    account_label = excluded.account_label,
                    status = excluded.status,
                    capabilities_json = excluded.capabilities_json,
                    scopes_json = excluded.scopes_json,
                    auth_type = excluded.auth_type,
                    tools_enabled = excluded.tools_enabled,
                    updated_at = excluded.updated_at,
                    last_refresh_at = excluded.last_refresh_at,
                    last_error = excluded.last_error
                """,
                (
                    resolved_id,
                    provider,
                    owner_user_id,
                    project_key,
                    account_label,
                    status,
                    json.dumps(capabilities),
                    json.dumps(scopes),
                    auth_type,
                    1 if tools_enabled else 0,
                    created_at,
                    now,
                    last_refresh_at,
                    last_error,
                ),
            )
        record = self.get_connection(connection_id=resolved_id)
        if record is None:
            raise HTTPException(status_code=500, detail="Failed to persist connection.")
        return record

    def set_tools_enabled(self, *, connection_id: str, owner_user_id: str, enabled: bool) -> ConnectionRecord | None:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE connections
                SET tools_enabled = ?, updated_at = ?
                WHERE id = ? AND owner_user_id = ?
                """,
                (1 if enabled else 0, _now(), connection_id, owner_user_id),
            )
        if cursor.rowcount == 0:
            return None
        return self.get_connection(connection_id=connection_id, owner_user_id=owner_user_id)

    def save_secret(self, *, connection_id: str, ciphertext: str, key_version: str = "v1") -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO connection_secrets (connection_id, ciphertext, key_version, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(connection_id) DO UPDATE SET
                    ciphertext = excluded.ciphertext,
                    key_version = excluded.key_version,
                    updated_at = excluded.updated_at
                """,
                (connection_id, ciphertext, key_version, _now()),
            )

    def load_secret(self, *, connection_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT ciphertext FROM connection_secrets WHERE connection_id = ?",
                (connection_id,),
            ).fetchone()
        return str(row["ciphertext"]) if row else None

    def delete_connection(self, *, connection_id: str, owner_user_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM connections WHERE id = ? AND owner_user_id = ?",
                (connection_id, owner_user_id),
            )
        return cursor.rowcount > 0

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
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO oauth_states (state, provider, user_id, project_key, workspace_root, redirect_to, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (state, provider, user_id, project_key, workspace_root, redirect_to, _now() + ttl_seconds),
            )
        return state

    def consume_oauth_state(self, *, state: str, provider: ProviderName) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM oauth_states WHERE state = ? AND provider = ?",
                (state, provider),
            ).fetchone()
            conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
        if row is None:
            raise HTTPException(status_code=400, detail="OAuth state is invalid or already used.")
        if int(row["expires_at"]) < _now():
            raise HTTPException(status_code=400, detail="OAuth state has expired.")
        return {
            "provider": str(row["provider"]),
            "user_id": str(row["user_id"]),
            "project_key": str(row["project_key"]),
            "workspace_root": str(row["workspace_root"]),
            "redirect_to": str(row["redirect_to"]) if row["redirect_to"] else None,
        }

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
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO connection_audit (
                    id, connection_id, user_id, tool_name, action_kind, status, request_summary, created_at, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"audit_{uuid.uuid4().hex}",
                    connection_id,
                    user_id,
                    tool_name,
                    action_kind,
                    status,
                    request_summary,
                    _now(),
                    error,
                ),
            )


class ConnectionService:
    def __init__(
        self,
        *,
        workspace_root: str | Path,
        settings: Settings | None = None,
        storage: StoragePathsService | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._storage = storage or StoragePathsService(self._settings)
        self._workspace_root = Path(workspace_root).expanduser().resolve()
        self._project_key = self._storage.project_key(self._workspace_root)
        self._repo = ConnectionRepository(self._storage.integrations_db_path(self._workspace_root))
        self._vault = SecretVault(self._settings)

    @classmethod
    def for_oauth_state(cls, *, state: str, provider: ProviderName, settings: Settings | None = None) -> "ConnectionService":
        active_settings = settings or get_settings()
        storage = StoragePathsService(active_settings)
        for db_path in storage.projects_dir().glob("*/integrations/integrations.db"):
            conn: sqlite3.Connection | None = None
            try:
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT workspace_root FROM oauth_states WHERE state = ? AND provider = ?",
                    (state, provider),
                ).fetchone()
            except sqlite3.Error:
                row = None
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass
            if row and row["workspace_root"]:
                return cls(workspace_root=str(row["workspace_root"]), settings=active_settings, storage=storage)
        raise HTTPException(status_code=400, detail="OAuth state is invalid or unavailable.")

    @property
    def project_key(self) -> str:
        return self._project_key

    def list_connections(self, *, owner_user_id: str) -> list[ConnectionRecord]:
        return self._repo.list_connections(owner_user_id=owner_user_id, project_key=self._project_key)

    def get_connection(self, *, connection_id: str, owner_user_id: str) -> ConnectionRecord:
        record = self._repo.get_connection(connection_id=connection_id, owner_user_id=owner_user_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Connection not found.")
        return record

    def get_connection_scopes(self, *, connection_id: str, owner_user_id: str) -> list[str]:
        return self.get_connection(connection_id=connection_id, owner_user_id=owner_user_id).scopes

    def begin_authorization(
        self,
        *,
        provider: AuthorizableProviderName,
        owner_user_id: str,
        redirect_to: str | None = None,
    ) -> AuthorizationStart:
        public_base_url = (self._settings.ethos_public_base_url or "").rstrip("/")
        if not public_base_url:
            raise HTTPException(status_code=503, detail="ETHOS_PUBLIC_BASE_URL is required for OAuth.")
        state = self._repo.create_oauth_state(
            provider=provider,
            user_id=owner_user_id,
            project_key=self._project_key,
            workspace_root=str(self._workspace_root),
            redirect_to=redirect_to,
        )
        if _is_google_provider(provider):
            if not self._settings.google_client_id or not self._settings.google_client_secret:
                raise HTTPException(status_code=503, detail="Google OAuth credentials are not configured.")
            redirect_uri = self._callback_redirect_uri(provider)
            query = urlencode(
                {
                    "client_id": self._settings.google_client_id,
                    "redirect_uri": redirect_uri,
                    "response_type": "code",
                    "access_type": "offline",
                    "prompt": "consent",
                    "include_granted_scopes": "true",
                    "scope": " ".join(_google_scopes_for_provider(provider)),
                    "state": state,
                }
            )
            url = f"https://accounts.google.com/o/oauth2/v2/auth?{query}"
        elif provider == "slack":
            if not self._settings.slack_client_id or not self._settings.slack_client_secret:
                raise HTTPException(status_code=503, detail="Slack OAuth credentials are not configured.")
            redirect_uri = f"{public_base_url}/v1/extensions/connections/slack/callback"
            query = urlencode(
                {
                    "client_id": self._settings.slack_client_id,
                    "redirect_uri": redirect_uri,
                    "scope": ",".join(SLACK_SCOPES),
                    "state": state,
                }
            )
            url = f"https://slack.com/oauth/v2/authorize?{query}"
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
        return AuthorizationStart(provider=provider, authorization_url=url, state=state)

    def handle_callback(self, *, provider: ProviderName, code: str, state: str) -> dict[str, Any]:
        oauth_state = self._repo.consume_oauth_state(state=state, provider=provider)
        if _is_google_provider(provider):
            result = self._handle_google_callback(
                provider=provider,
                code=code,
                owner_user_id=oauth_state["user_id"],
            )
        elif provider == "slack":
            result = self._handle_slack_callback(code=code, owner_user_id=oauth_state["user_id"])
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")
        result["redirect_to"] = oauth_state.get("redirect_to")
        return result

    def refresh_access_token(self, *, connection_id: str, owner_user_id: str | None = None) -> dict[str, Any]:
        record = self._repo.get_connection(connection_id=connection_id, owner_user_id=owner_user_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Connection not found.")
        secrets_data = self._load_secret_payload(record.id)
        if _is_google_provider(record.provider):
            refreshed = self._refresh_google_token(secrets_data)
        else:
            refreshed = self._refresh_slack_token(secrets_data)
        merged = dict(secrets_data)
        merged.update(refreshed)
        self._repo.save_secret(connection_id=record.id, ciphertext=self._vault.encrypt(merged))
        self._repo.save_connection(
            connection_id=record.id,
            provider=record.provider,
            owner_user_id=record.owner_user_id,
            project_key=record.project_key,
            account_label=record.account_label,
            status="active",
            capabilities=record.capabilities,
            scopes=record.scopes,
            auth_type=record.auth_type,
            tools_enabled=record.tools_enabled,
            last_refresh_at=_now(),
            last_error=None,
        )
        return merged

    def revoke_connection(self, *, connection_id: str, owner_user_id: str) -> bool:
        return self._repo.delete_connection(connection_id=connection_id, owner_user_id=owner_user_id)

    def set_tools_enabled(self, *, connection_id: str, owner_user_id: str, enabled: bool) -> ConnectionRecord:
        record = self._repo.set_tools_enabled(
            connection_id=connection_id,
            owner_user_id=owner_user_id,
            enabled=enabled,
        )
        if record is None:
            raise HTTPException(status_code=404, detail="Connection not found.")
        return record

    def test_connection(self, *, connection_id: str, owner_user_id: str) -> dict[str, Any]:
        record = self.get_connection(connection_id=connection_id, owner_user_id=owner_user_id)
        if _is_google_provider(record.provider):
            payload = self._google_request(record=record, method="GET", path="oauth2/v2/userinfo")
            return {"ok": True, "provider": record.provider, "label": payload.get("email") or record.account_label}
        payload = self._slack_request(record=record, method="POST", path="auth.test", json_body={})
        if payload.get("ok") is not True:
            raise HTTPException(status_code=502, detail=str(payload.get("error", "Slack auth test failed.")))
        return {"ok": True, "provider": record.provider, "label": payload.get("team") or record.account_label}

    def perform_tool(
        self,
        *,
        provider: ProviderName,
        tool_name: str,
        owner_user_id: str,
        connection_id: str | None,
        payload: dict[str, Any],
    ) -> str:
        record = (
            self.get_connection(connection_id=connection_id, owner_user_id=owner_user_id)
            if connection_id
            else self._repo.get_default_connection(provider=provider, owner_user_id=owner_user_id, project_key=self._project_key)
        )
        if record is None:
            raise HTTPException(status_code=404, detail=f"No active {provider} connection is available.")
        if connection_id and record.provider != provider:
            raise HTTPException(
                status_code=400,
                detail=f"Connection {connection_id} belongs to provider {record.provider}, not {provider}.",
            )
        if not record.tools_enabled:
            raise HTTPException(status_code=403, detail=f"Tools are disabled for connection {record.id}.")
        try:
            response = self._dispatch_tool(record=record, tool_name=tool_name, payload=payload)
            self._repo.append_audit(
                connection_id=record.id,
                user_id=owner_user_id,
                tool_name=tool_name,
                action_kind="write" if tool_name in WRITE_TOOL_NAMES else "read",
                status="ok",
                request_summary=json.dumps(payload, ensure_ascii=False),
            )
            return json.dumps(response, indent=2, ensure_ascii=False)
        except HTTPException as exc:
            self._repo.append_audit(
                connection_id=record.id,
                user_id=owner_user_id,
                tool_name=tool_name,
                action_kind="write" if tool_name in WRITE_TOOL_NAMES else "read",
                status="error",
                request_summary=json.dumps(payload, ensure_ascii=False),
                error=str(exc.detail),
            )
            raise

    def _load_secret_payload(self, connection_id: str) -> dict[str, Any]:
        ciphertext = self._repo.load_secret(connection_id=connection_id)
        if not ciphertext:
            raise HTTPException(status_code=500, detail="Connection secret is missing.")
        return self._vault.decrypt(ciphertext)

    def _callback_redirect_uri(self, provider: ProviderName) -> str:
        public_base_url = (self._settings.ethos_public_base_url or "").rstrip("/")
        return f"{public_base_url}/v1/extensions/connections/{provider}/callback"

    def _exchange_google_code(self, *, provider: ProviderName, code: str) -> dict[str, Any]:
        response = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": self._settings.google_client_id,
                "client_secret": self._settings.google_client_secret,
                "redirect_uri": self._callback_redirect_uri(provider),
                "grant_type": "authorization_code",
            },
            timeout=20,
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Google token exchange failed ({response.status_code}).")
        return _ensure_dict(response.json())

    def _exchange_slack_code(self, code: str) -> dict[str, Any]:
        response = httpx.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "code": code,
                "client_id": self._settings.slack_client_id,
                "client_secret": self._settings.slack_client_secret,
                "redirect_uri": self._callback_redirect_uri("slack"),
            },
            timeout=20,
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Slack token exchange failed ({response.status_code}).")
        payload = _ensure_dict(response.json())
        if payload.get("ok") is not True:
            raise HTTPException(status_code=502, detail=f"Slack token exchange failed: {payload.get('error', 'unknown')}")
        return payload

    def _handle_google_callback(self, *, provider: ProviderName, code: str, owner_user_id: str) -> dict[str, Any]:
        token_payload = self._exchange_google_code(provider=provider, code=code)
        access_token = str(token_payload.get("access_token", "")).strip()
        if not access_token:
            raise HTTPException(status_code=502, detail="Google OAuth response did not include an access token.")
        userinfo_response = httpx.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=20,
        )
        if userinfo_response.status_code >= 400:
            raise HTTPException(status_code=502, detail="Failed to fetch Google account profile.")
        userinfo = _ensure_dict(userinfo_response.json())
        scopes = str(token_payload.get("scope", "")).split()
        account_label = str(userinfo.get("email") or userinfo.get("name") or "Google account")
        record = self._repo.save_connection(
            connection_id=None,
            provider=provider,
            owner_user_id=owner_user_id,
            project_key=self._project_key,
            account_label=account_label,
            status="active",
            capabilities=_google_capabilities_for_provider(provider),
            scopes=scopes or _google_scopes_for_provider(provider),
            last_refresh_at=_now(),
            last_error=None,
        )
        secret_payload = {
            "access_token": access_token,
            "refresh_token": token_payload.get("refresh_token"),
            "token_type": token_payload.get("token_type", "Bearer"),
            "expiry": _now() + int(token_payload.get("expires_in", 3600)),
        }
        self._repo.save_secret(connection_id=record.id, ciphertext=self._vault.encrypt(secret_payload))
        return {"connection_id": record.id, "account_label": record.account_label, "provider": provider}

    def _handle_slack_callback(self, *, code: str, owner_user_id: str) -> dict[str, Any]:
        token_payload = self._exchange_slack_code(code)
        access_token = str(token_payload.get("access_token", "")).strip()
        if not access_token:
            raise HTTPException(status_code=502, detail="Slack OAuth response did not include an access token.")
        team = _ensure_dict(token_payload.get("team"))
        authed_user = _ensure_dict(token_payload.get("authed_user"))
        account_label = str(team.get("name") or authed_user.get("id") or "Slack workspace")
        scopes = str(token_payload.get("scope", "")).split(",")
        record = self._repo.save_connection(
            connection_id=None,
            provider="slack",
            owner_user_id=owner_user_id,
            project_key=self._project_key,
            account_label=account_label,
            status="active",
            capabilities=["channels", "search", "chat"],
            scopes=[scope for scope in scopes if scope],
            last_refresh_at=_now(),
            last_error=None,
        )
        secret_payload = {
            "access_token": access_token,
            "refresh_token": token_payload.get("refresh_token") or authed_user.get("refresh_token"),
            "token_type": token_payload.get("token_type", "Bearer"),
            "expiry": _now() + int(token_payload.get("expires_in", 3600)),
        }
        self._repo.save_secret(connection_id=record.id, ciphertext=self._vault.encrypt(secret_payload))
        return {"connection_id": record.id, "account_label": record.account_label, "provider": "slack"}

    def _refresh_google_token(self, secret_payload: dict[str, Any]) -> dict[str, Any]:
        refresh_token = str(secret_payload.get("refresh_token", "")).strip()
        if not refresh_token:
            raise HTTPException(status_code=400, detail="This Google connection does not have a refresh token.")
        response = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "refresh_token": refresh_token,
                "client_id": self._settings.google_client_id,
                "client_secret": self._settings.google_client_secret,
                "grant_type": "refresh_token",
            },
            timeout=20,
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Google token refresh failed ({response.status_code}).")
        payload = _ensure_dict(response.json())
        return {
            "access_token": payload.get("access_token"),
            "token_type": payload.get("token_type", secret_payload.get("token_type", "Bearer")),
            "expiry": _now() + int(payload.get("expires_in", 3600)),
            "refresh_token": secret_payload.get("refresh_token"),
        }

    def _refresh_slack_token(self, secret_payload: dict[str, Any]) -> dict[str, Any]:
        refresh_token = str(secret_payload.get("refresh_token", "")).strip()
        if not refresh_token:
            return secret_payload
        response = httpx.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self._settings.slack_client_id,
                "client_secret": self._settings.slack_client_secret,
            },
            timeout=20,
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Slack token refresh failed ({response.status_code}).")
        payload = _ensure_dict(response.json())
        if payload.get("ok") is not True:
            raise HTTPException(status_code=502, detail=f"Slack token refresh failed: {payload.get('error', 'unknown')}")
        return {
            "access_token": payload.get("access_token"),
            "token_type": payload.get("token_type", secret_payload.get("token_type", "Bearer")),
            "expiry": _now() + int(payload.get("expires_in", 3600)),
            "refresh_token": payload.get("refresh_token", refresh_token),
        }

    def _active_access_token(self, record: ConnectionRecord) -> str:
        payload = self._load_secret_payload(record.id)
        expiry = int(payload.get("expiry") or 0)
        if expiry and expiry <= (_now() + 60):
            payload = self.refresh_access_token(connection_id=record.id, owner_user_id=record.owner_user_id)
        access_token = str(payload.get("access_token", "")).strip()
        if not access_token:
            raise HTTPException(status_code=500, detail="Connection access token is missing.")
        return access_token

    def _google_request(
        self,
        *,
        record: ConnectionRecord,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = self._active_access_token(record)
        response = httpx.request(
            method=method,
            url=f"https://www.googleapis.com/{path.lstrip('/')}",
            params=params,
            json=json_body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Google API request failed ({response.status_code}).")
        if not response.content:
            return {"ok": True}
        if "application/json" in response.headers.get("content-type", ""):
            return _ensure_dict(response.json())
        return {"content": response.text}

    def _google_binary_request(
        self,
        *,
        record: ConnectionRecord,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = self._active_access_token(record)
        response = httpx.get(
            f"https://www.googleapis.com/{path.lstrip('/')}",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Google file read failed ({response.status_code}).")
        return {
            "content_type": response.headers.get("content-type"),
            "size": len(response.content),
            "content_base64": base64.b64encode(response.content).decode("ascii"),
        }

    def _slack_request(
        self,
        *,
        record: ConnectionRecord,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = self._active_access_token(record)
        response = httpx.request(
            method=method,
            url=f"https://slack.com/api/{path.lstrip('/')}",
            json=json_body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Slack API request failed ({response.status_code}).")
        payload = _ensure_dict(response.json())
        if payload.get("ok") is False:
            raise HTTPException(status_code=502, detail=f"Slack API error: {payload.get('error', 'unknown')}")
        return payload

    def _dispatch_tool(self, *, record: ConnectionRecord, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "gmail_search_messages":
            return self._google_request(
                record=record,
                method="GET",
                path="gmail/v1/users/me/messages",
                params={"q": payload.get("query", ""), "maxResults": int(payload.get("limit", 10))},
            )
        if tool_name == "gmail_get_message":
            message_id = str(payload.get("message_id", "")).strip()
            if not message_id:
                raise HTTPException(status_code=400, detail="message_id is required.")
            return self._google_request(
                record=record,
                method="GET",
                path=f"gmail/v1/users/me/messages/{message_id}",
                params={"format": "full"},
            )
        if tool_name == "gmail_send_message":
            to = str(payload.get("to", "")).strip()
            subject = str(payload.get("subject", "")).strip()
            body = str(payload.get("body", "")).strip()
            if not to or not subject or not body:
                raise HTTPException(status_code=400, detail="to, subject, and body are required.")
            raw = base64.urlsafe_b64encode(
                f"To: {to}\r\nSubject: {subject}\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n{body}".encode("utf-8")
            ).decode("ascii")
            return self._google_request(
                record=record,
                method="POST",
                path="gmail/v1/users/me/messages/send",
                json_body={"raw": raw},
            )
        if tool_name == "drive_search_files":
            return self._google_request(
                record=record,
                method="GET",
                path="drive/v3/files",
                params={
                    "q": str(payload.get("query", "")).strip() or "trashed = false",
                    "pageSize": int(payload.get("limit", 10)),
                    "fields": "files(id,name,mimeType,modifiedTime,size,webViewLink)",
                },
            )
        if tool_name == "drive_read_file":
            file_id = str(payload.get("file_id", "")).strip()
            if not file_id:
                raise HTTPException(status_code=400, detail="file_id is required.")
            metadata = self._google_request(
                record=record,
                method="GET",
                path=f"drive/v3/files/{file_id}",
                params={"fields": "id,name,mimeType,size"},
            )
            mime_type = str(metadata.get("mimeType", ""))
            if mime_type.startswith("application/vnd.google-apps"):
                return self._google_binary_request(
                    record=record,
                    path=f"drive/v3/files/{file_id}/export",
                    params={"mimeType": "text/plain"},
                ) | {"metadata": metadata}
            return self._google_binary_request(
                record=record,
                path=f"drive/v3/files/{file_id}",
                params={"alt": "media"},
            ) | {"metadata": metadata}
        if tool_name == "calendar_list_events":
            calendar_id = str(payload.get("calendar_id", "primary")).strip() or "primary"
            params = {
                "maxResults": int(payload.get("limit", 10)),
                "singleEvents": True,
                "orderBy": "startTime",
            }
            if payload.get("time_min"):
                params["timeMin"] = str(payload["time_min"])
            if payload.get("time_max"):
                params["timeMax"] = str(payload["time_max"])
            return self._google_request(
                record=record,
                method="GET",
                path=f"calendar/v3/calendars/{calendar_id}/events",
                params=params,
            )
        if tool_name == "calendar_create_event":
            calendar_id = str(payload.get("calendar_id", "primary")).strip() or "primary"
            title = str(payload.get("title", "")).strip()
            start = str(payload.get("start", "")).strip()
            end = str(payload.get("end", "")).strip()
            if not title or not start or not end:
                raise HTTPException(status_code=400, detail="title, start, and end are required.")
            attendees = payload.get("attendees")
            attendees_payload = (
                [{"email": item} for item in attendees if isinstance(item, str) and item.strip()]
                if isinstance(attendees, list)
                else []
            )
            body = {
                "summary": title,
                "description": str(payload.get("description", "")).strip() or None,
                "start": {"dateTime": start},
                "end": {"dateTime": end},
            }
            if attendees_payload:
                body["attendees"] = attendees_payload
            return self._google_request(
                record=record,
                method="POST",
                path=f"calendar/v3/calendars/{calendar_id}/events",
                json_body=body,
            )
        if tool_name == "sheets_read_values":
            spreadsheet_id = str(payload.get("spreadsheet_id", "")).strip()
            range_name = str(payload.get("range", "")).strip()
            if not spreadsheet_id or not range_name:
                raise HTTPException(status_code=400, detail="spreadsheet_id and range are required.")
            return self._google_request(
                record=record,
                method="GET",
                path=f"sheets/v4/spreadsheets/{spreadsheet_id}/values/{range_name}",
            )
        if tool_name == "sheets_append_values":
            spreadsheet_id = str(payload.get("spreadsheet_id", "")).strip()
            range_name = str(payload.get("range", "")).strip()
            values = payload.get("values")
            if not spreadsheet_id or not range_name or not isinstance(values, list):
                raise HTTPException(status_code=400, detail="spreadsheet_id, range, and values are required.")
            return self._google_request(
                record=record,
                method="POST",
                path=f"sheets/v4/spreadsheets/{spreadsheet_id}/values/{range_name}:append",
                params={"valueInputOption": "USER_ENTERED"},
                json_body={"values": values},
            )
        if tool_name == "slack_list_channels":
            payload = self._slack_request(record=record, method="POST", path="conversations.list", json_body={"limit": int(payload.get("limit", 20))})
            return {"channels": payload.get("channels", [])}
        if tool_name == "slack_search_messages":
            query = str(payload.get("query", "")).strip()
            if not query:
                raise HTTPException(status_code=400, detail="query is required.")
            return self._slack_request(record=record, method="POST", path="search.messages", json_body={"query": query, "count": int(payload.get("limit", 10))})
        if tool_name == "slack_post_message":
            channel = str(payload.get("channel", "")).strip()
            text = str(payload.get("text", "")).strip()
            if not channel or not text:
                raise HTTPException(status_code=400, detail="channel and text are required.")
            return self._slack_request(record=record, method="POST", path="chat.postMessage", json_body={"channel": channel, "text": text})
        raise HTTPException(status_code=400, detail=f"Unsupported integration tool: {tool_name}")


__all__ = [
    "AuthorizableProviderName",
    "AuthorizationStart",
    "ConnectionRecord",
    "ConnectionRepository",
    "ConnectionService",
    "GOOGLE_CONNECTOR_CAPABILITIES",
    "GOOGLE_CONNECTOR_SCOPES",
    "GOOGLE_SCOPES",
    "ProviderName",
    "SLACK_SCOPES",
    "SecretVault",
    "SUPPORTED_CONNECTION_PROVIDERS",
    "WRITE_TOOL_NAMES",
]
