"""Native connections orchestration service."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import HTTPException

from src.app.core.settings import Settings, get_settings
from src.app.features.extensions.oauth_clients import (
    AuthorizationStart,
    GOOGLE_CONNECTOR_CAPABILITIES,
    GOOGLE_CONNECTOR_SCOPES,
    GOOGLE_SCOPES,
    MICROSOFT_CONNECTOR_SCOPES,
    OAuthProviderClient,
    ProviderName,
    SLACK_SCOPES,
    WRITE_TOOL_NAMES,
    build_authorization_start,
    ensure_dict,
    google_capabilities_for_provider,
    is_google_provider,
    is_microsoft_provider,
    microsoft_capabilities_for_provider,
    now_epoch,
)
from src.app.features.extensions.secret_vault import SecretVault
from src.app.repositories.connection_repository import (
    ConnectionRecord,
    ConnectionRepository,
    ConnectionRepositorySchemaUnavailableError,
    OAuthStateExpiredError,
    OAuthStateInvalidError,
)
from src.app.services.database import get_sqlalchemy_engine, get_sqlalchemy_session_factory
from src.app.services.storage_paths import StoragePathsService

AuthorizableProviderName = Literal[
    "google-gmail",
    "google-drive",
    "google-calendar",
    "google-sheets",
    "microsoft-outlook-mail",
    "microsoft-outlook-calendar",
    "slack",
]
ConnectionScope = Literal["project", "user"]
SUPPORTED_CONNECTION_PROVIDERS: tuple[AuthorizableProviderName, ...] = (
    "google-gmail",
    "google-drive",
    "google-calendar",
    "google-sheets",
    "microsoft-outlook-mail",
    "microsoft-outlook-calendar",
    "slack",
)


class ConnectionService:
    def __init__(
        self,
        *,
        workspace_root: str | Path,
        settings: Settings | None = None,
        storage: StoragePathsService | None = None,
        scope: ConnectionScope = "project",
    ) -> None:
        self._settings = settings or get_settings()
        self._storage = storage or StoragePathsService(self._settings)
        self._scope = scope
        resolved_workspace_root = Path(workspace_root).expanduser().resolve()
        self._requested_workspace_root = resolved_workspace_root
        if scope == "user":
            self._workspace_root = (self._storage.user_settings_dir() / "__user_scope__").resolve()
            self._project_key = "user"
        else:
            self._workspace_root = resolved_workspace_root
            self._project_key = self._storage.project_key(self._workspace_root)
        get_sqlalchemy_engine(self._settings)
        self._repo = ConnectionRepository(get_sqlalchemy_session_factory(self._settings))
        self._vault = SecretVault(self._settings)
        self._oauth = OAuthProviderClient(self._settings, self._active_access_token)
        self._oauth_state_payload: dict[str, Any] | None = None

    @classmethod
    def for_oauth_state(cls, *, state: str, provider: ProviderName, settings: Settings | None = None) -> "ConnectionService":
        active_settings = settings or get_settings()
        storage = StoragePathsService(active_settings)
        repo = ConnectionRepository(get_sqlalchemy_session_factory(active_settings))
        try:
            payload = repo.consume_oauth_state(state=state, provider=provider)
        except ConnectionRepositorySchemaUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except (OAuthStateInvalidError, OAuthStateExpiredError) as exc:
            raise HTTPException(status_code=400, detail="OAuth state is invalid or unavailable.") from exc
        if isinstance(payload, dict) and payload.get("workspace_root"):
            scope: ConnectionScope = "user" if str(payload.get("project_key")) == "user" else "project"
            service = cls(
                workspace_root=str(payload["workspace_root"]),
                settings=active_settings,
                storage=storage,
                scope=scope,
            )
            service._oauth_state_payload = payload
            return service
        raise HTTPException(status_code=400, detail="OAuth state is invalid or unavailable.")

    @property
    def project_key(self) -> str:
        return self._project_key

    @property
    def scope(self) -> ConnectionScope:
        return self._scope

    def _user_service(self) -> "ConnectionService":
        if self._scope == "user":
            return self
        return ConnectionService(
            workspace_root=self._requested_workspace_root,
            settings=self._settings,
            storage=self._storage,
            scope="user",
        )

    def list_connections(self, *, owner_user_id: str) -> list[ConnectionRecord]:
        return self._repo.list_connections(owner_user_id=owner_user_id, project_key=self._project_key)

    def list_effective_connections(self, *, owner_user_id: str) -> list[ConnectionRecord]:
        if self._scope == "user":
            return self.list_connections(owner_user_id=owner_user_id)
        project_connections = self.list_connections(owner_user_id=owner_user_id)
        user_connections = self._user_service().list_connections(owner_user_id=owner_user_id)
        project_providers = {item.provider for item in project_connections}
        return project_connections + [item for item in user_connections if item.provider not in project_providers]

    def get_connection(self, *, connection_id: str, owner_user_id: str) -> ConnectionRecord:
        record = self._repo.get_connection(connection_id=connection_id, owner_user_id=owner_user_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Connection not found.")
        return record

    def get_effective_connection(self, *, connection_id: str, owner_user_id: str) -> ConnectionRecord:
        record = self._repo.get_connection(connection_id=connection_id, owner_user_id=owner_user_id)
        if record is not None:
            return record
        if self._scope == "project":
            user_record = self._user_service()._repo.get_connection(connection_id=connection_id, owner_user_id=owner_user_id)
            if user_record is not None:
                return user_record
        raise HTTPException(status_code=404, detail="Connection not found.")

    def get_connection_scopes(self, *, connection_id: str, owner_user_id: str) -> list[str]:
        return self.get_effective_connection(connection_id=connection_id, owner_user_id=owner_user_id).scopes

    def begin_authorization(
        self,
        *,
        provider: AuthorizableProviderName,
        owner_user_id: str,
        redirect_to: str | None = None,
    ) -> AuthorizationStart:
        public_base_url = (self._settings.aethos_public_base_url or "").rstrip("/")
        if not public_base_url:
            raise HTTPException(status_code=503, detail="AETHOS_PUBLIC_BASE_URL is required for OAuth.")
        state = self._repo.create_oauth_state(
            provider=provider,
            user_id=owner_user_id,
            project_key=self._project_key,
            workspace_root=str(self._workspace_root),
            redirect_to=redirect_to,
        )
        return build_authorization_start(
            settings=self._settings,
            provider=provider,
            state=state,
            callback_redirect_uri=self._callback_redirect_uri(provider),
        )

    def handle_callback(self, *, provider: ProviderName, code: str, state: str) -> dict[str, Any]:
        oauth_state = self._oauth_state_payload
        if oauth_state is None:
            try:
                oauth_state = self._repo.consume_oauth_state(state=state, provider=provider)
            except ConnectionRepositorySchemaUnavailableError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except (OAuthStateInvalidError, OAuthStateExpiredError) as exc:
                raise HTTPException(status_code=400, detail="OAuth state is invalid or unavailable.") from exc
        self._oauth_state_payload = None
        if is_google_provider(provider):
            result = self._handle_google_callback(
                provider=provider,
                code=code,
                owner_user_id=oauth_state["user_id"],
            )
        elif is_microsoft_provider(provider):
            result = self._handle_microsoft_callback(
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
        if is_google_provider(record.provider):
            refreshed = self._oauth.refresh_google_token(secrets_data)
        elif is_microsoft_provider(record.provider):
            refreshed = self._oauth.refresh_microsoft_token(secrets_data)
        else:
            refreshed = self._oauth.refresh_slack_token(secrets_data)
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
            last_refresh_at=now_epoch(),
            last_error=None,
        )
        return merged

    def revoke_connection(self, *, connection_id: str, owner_user_id: str) -> bool:
        deleted = self._repo.delete_connection(connection_id=connection_id, owner_user_id=owner_user_id)
        if deleted or self._scope != "project":
            return deleted
        return self._user_service()._repo.delete_connection(connection_id=connection_id, owner_user_id=owner_user_id)

    def set_tools_enabled(self, *, connection_id: str, owner_user_id: str, enabled: bool) -> ConnectionRecord:
        record = self._repo.set_tools_enabled(connection_id=connection_id, owner_user_id=owner_user_id, enabled=enabled)
        if record is not None:
            return record
        if self._scope == "project":
            user_record = self._user_service()._repo.set_tools_enabled(
                connection_id=connection_id,
                owner_user_id=owner_user_id,
                enabled=enabled,
            )
            if user_record is not None:
                return user_record
        raise HTTPException(status_code=404, detail="Connection not found.")

    def get_default_connection(self, *, provider: ProviderName, owner_user_id: str) -> ConnectionRecord | None:
        record = self._repo.get_default_connection(provider=provider, owner_user_id=owner_user_id, project_key=self._project_key)
        if record is not None or self._scope != "project":
            return record
        return self._user_service()._repo.get_default_connection(
            provider=provider,
            owner_user_id=owner_user_id,
            project_key=self._user_service().project_key,
        )

    def test_connection(self, *, connection_id: str, owner_user_id: str) -> dict[str, Any]:
        record = self.get_effective_connection(connection_id=connection_id, owner_user_id=owner_user_id)
        service = self
        if self._scope == "project" and record.project_key == "user":
            service = self._user_service()

        if is_google_provider(record.provider):
            payload = service._google_request(record=record, method="GET", path="oauth2/v2/userinfo")
            return {"ok": True, "provider": record.provider, "label": payload.get("email") or record.account_label}
        if is_microsoft_provider(record.provider):
            payload = service._microsoft_request(record=record, method="GET", path="v1.0/me")
            label = payload.get("mail") or payload.get("userPrincipalName") or record.account_label
            return {"ok": True, "provider": record.provider, "label": label}
        payload = service._slack_request(record=record, method="POST", path="auth.test", json_body={})
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
        audit_repo = self._repo
        tool_service = self
        if connection_id:
            record = self._repo.get_connection(connection_id=connection_id, owner_user_id=owner_user_id)
            if record is None and self._scope == "project":
                user_service = self._user_service()
                record = user_service._repo.get_connection(connection_id=connection_id, owner_user_id=owner_user_id)
                if record is not None:
                    audit_repo = user_service._repo
                    tool_service = user_service
        else:
            record = self._repo.get_default_connection(provider=provider, owner_user_id=owner_user_id, project_key=self._project_key)
            if record is None and self._scope == "project":
                user_service = self._user_service()
                record = user_service._repo.get_default_connection(
                    provider=provider,
                    owner_user_id=owner_user_id,
                    project_key=user_service.project_key,
                )
                if record is not None:
                    audit_repo = user_service._repo
                    tool_service = user_service
        if record is None:
            raise HTTPException(status_code=404, detail=f"No active {provider} connection is available.")
        if self._scope == "project" and record.project_key == "user":
            user_service = self._user_service()
            tool_service = user_service
            audit_repo = user_service._repo
        if connection_id and record.provider != provider:
            raise HTTPException(status_code=400, detail=f"Connection {connection_id} belongs to provider {record.provider}, not {provider}.")
        if not record.tools_enabled:
            raise HTTPException(status_code=403, detail=f"Tools are disabled for connection {record.id}.")
        try:
            response = tool_service._dispatch_tool(record=record, tool_name=tool_name, payload=payload)
            audit_repo.append_audit(
                connection_id=record.id,
                user_id=owner_user_id,
                tool_name=tool_name,
                action_kind="write" if tool_name in WRITE_TOOL_NAMES else "read",
                status="ok",
                request_summary=json.dumps(payload, ensure_ascii=False),
            )
            return json.dumps(response, indent=2, ensure_ascii=False)
        except HTTPException as exc:
            audit_repo.append_audit(
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
        public_base_url = (self._settings.aethos_public_base_url or "").rstrip("/")
        return f"{public_base_url}/v1/extensions/connections/{provider}/callback"

    def _exchange_google_code(self, *, provider: ProviderName, code: str) -> dict[str, Any]:
        payload = self._oauth.exchange_google_code(
            provider=provider,
            code=code,
            callback_redirect_uri=self._callback_redirect_uri(provider),
        )
        if not payload.get("access_token"):
            raise HTTPException(status_code=502, detail="Google token exchange response is missing access_token.")
        return payload

    def _exchange_microsoft_code(self, *, provider: ProviderName, code: str) -> dict[str, Any]:
        payload = self._oauth.exchange_microsoft_code(
            provider=provider,
            code=code,
            callback_redirect_uri=self._callback_redirect_uri(provider),
        )
        if not payload.get("access_token"):
            raise HTTPException(status_code=502, detail="Microsoft token exchange response is missing access_token.")
        return payload

    def _exchange_slack_code(self, *, code: str) -> dict[str, Any]:
        payload = self._oauth.exchange_slack_code(code=code)
        access_token = payload.get("access_token")
        authed_user = payload.get("authed_user") if isinstance(payload.get("authed_user"), dict) else {}
        if not access_token and isinstance(authed_user, dict):
            access_token = authed_user.get("access_token")
        if not access_token:
            raise HTTPException(status_code=502, detail="Slack token exchange response is missing access_token.")
        return payload

    def _refresh_google_token(self, secrets_data: dict[str, Any]) -> dict[str, Any]:
        return self._oauth.refresh_google_token(secrets_data)

    def _refresh_microsoft_token(self, secrets_data: dict[str, Any]) -> dict[str, Any]:
        return self._oauth.refresh_microsoft_token(secrets_data)

    def _refresh_slack_token(self, secrets_data: dict[str, Any]) -> dict[str, Any]:
        return self._oauth.refresh_slack_token(secrets_data)

    def _active_access_token(self, record: ConnectionRecord) -> str:
        secrets_data = self._load_secret_payload(record.id)
        expiry = secrets_data.get("expiry")
        access_token = str(secrets_data.get("access_token", "")).strip()
        now = now_epoch()
        if access_token and (not isinstance(expiry, (int, float)) or now < int(expiry) - 30):
            return access_token
        refreshed = self.refresh_access_token(connection_id=record.id, owner_user_id=record.owner_user_id)
        token = str(refreshed.get("access_token", "")).strip()
        if not token:
            raise HTTPException(status_code=502, detail="Provider token refresh did not return an access token.")
        return token

    def _request_with_access_token(
        self,
        *,
        url: str,
        access_token: str,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        provider_label: str,
    ) -> dict[str, Any]:
        merged_headers = {"Authorization": f"Bearer {access_token}"}
        if headers:
            merged_headers.update(headers)
        response = httpx.request(
            method=method,
            url=url,
            params=params,
            json=json_body,
            headers=merged_headers,
            timeout=30,
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"{provider_label} API request failed ({response.status_code}).")
        if not response.content:
            return {"ok": True}
        if "application/json" in response.headers.get("content-type", ""):
            data = response.json()
            return data if isinstance(data, dict) else {"value": data}
        return {"content": response.text}

    def _handle_google_callback(self, *, provider: ProviderName, code: str, owner_user_id: str) -> dict[str, Any]:
        token = self._exchange_google_code(provider=provider, code=code)
        access_token = str(token.get("access_token", "")).strip()
        if not access_token:
            raise HTTPException(status_code=502, detail="Google token exchange failed to return access token.")
        userinfo = self._request_with_access_token(
            url="https://www.googleapis.com/oauth2/v2/userinfo",
            access_token=access_token,
            provider_label="Google",
        )
        email = str(userinfo.get("email", "")).strip() or "google-account"
        capabilities = google_capabilities_for_provider(provider)
        scopes = list(dict.fromkeys(token.get("scope", "").split())) if isinstance(token.get("scope"), str) else []
        if not scopes:
            scopes = GOOGLE_CONNECTOR_SCOPES.get(provider, GOOGLE_SCOPES)
        expiry = now_epoch() + int(token.get("expires_in", 3600)) if isinstance(token.get("expires_in"), int) else None
        record = self._repo.save_connection(
            connection_id=None,
            provider=provider,
            owner_user_id=owner_user_id,
            project_key=self._project_key,
            account_label=email,
            status="active",
            capabilities=capabilities,
            scopes=scopes,
            auth_type="oauth2",
            tools_enabled=True,
            last_refresh_at=now_epoch(),
            last_error=None,
        )
        self._repo.save_secret(
            connection_id=record.id,
            ciphertext=self._vault.encrypt(
                {
                    "access_token": access_token,
                    "refresh_token": token.get("refresh_token"),
                    "token_type": token.get("token_type") or "Bearer",
                    "expiry": expiry,
                    "scope": token.get("scope"),
                }
            ),
        )
        return {"connection_id": record.id, "account_label": record.account_label, "provider": record.provider}

    def _handle_microsoft_callback(self, *, provider: ProviderName, code: str, owner_user_id: str) -> dict[str, Any]:
        token = self._exchange_microsoft_code(provider=provider, code=code)
        access_token = str(token.get("access_token", "")).strip()
        if not access_token:
            raise HTTPException(status_code=502, detail="Microsoft token exchange failed to return access token.")
        me = self._request_with_access_token(
            url="https://graph.microsoft.com/v1.0/me",
            access_token=access_token,
            provider_label="Microsoft Graph",
        )
        label = str(me.get("mail") or me.get("userPrincipalName") or "microsoft-account")
        capabilities = microsoft_capabilities_for_provider(provider)
        scopes = list(dict.fromkeys(token.get("scope", "").split())) if isinstance(token.get("scope"), str) else MICROSOFT_CONNECTOR_SCOPES[provider]
        expiry = now_epoch() + int(token.get("expires_in", 3600)) if isinstance(token.get("expires_in"), int) else None
        record = self._repo.save_connection(
            connection_id=None,
            provider=provider,
            owner_user_id=owner_user_id,
            project_key=self._project_key,
            account_label=label,
            status="active",
            capabilities=capabilities,
            scopes=scopes,
            auth_type="oauth2",
            tools_enabled=True,
            last_refresh_at=now_epoch(),
            last_error=None,
        )
        self._repo.save_secret(
            connection_id=record.id,
            ciphertext=self._vault.encrypt(
                {
                    "access_token": access_token,
                    "refresh_token": token.get("refresh_token"),
                    "token_type": token.get("token_type") or "Bearer",
                    "expiry": expiry,
                    "scope": token.get("scope"),
                }
            ),
        )
        return {"connection_id": record.id, "account_label": record.account_label, "provider": record.provider}

    def _handle_slack_callback(self, *, code: str, owner_user_id: str) -> dict[str, Any]:
        token = self._exchange_slack_code(code=code)
        access_token = str(token.get("access_token") or "").strip()
        authed_user = token.get("authed_user") if isinstance(token.get("authed_user"), dict) else {}
        if not access_token and isinstance(authed_user, dict):
            access_token = str(authed_user.get("access_token") or "").strip()
        if not access_token:
            raise HTTPException(status_code=502, detail="Slack token exchange failed to return access token.")
        team = token.get("team") if isinstance(token.get("team"), dict) else {}
        team_name = str(team.get("name") if isinstance(team, dict) else "")
        user_id = str((authed_user or {}).get("id", "")).strip()
        label = team_name.strip() or user_id or "slack-workspace"
        scopes_raw = token.get("scope")
        scopes = [item.strip() for item in scopes_raw.split(",") if item.strip()] if isinstance(scopes_raw, str) else SLACK_SCOPES
        expiry = now_epoch() + int(token.get("expires_in", 3600)) if isinstance(token.get("expires_in"), int) else None
        refresh_token = token.get("refresh_token")
        if not refresh_token and isinstance(authed_user, dict):
            refresh_token = authed_user.get("refresh_token")
        record = self._repo.save_connection(
            connection_id=None,
            provider="slack",
            owner_user_id=owner_user_id,
            project_key=self._project_key,
            account_label=label,
            status="active",
            capabilities=["slack"],
            scopes=scopes,
            auth_type="oauth2",
            tools_enabled=True,
            last_refresh_at=now_epoch(),
            last_error=None,
        )
        self._repo.save_secret(
            connection_id=record.id,
            ciphertext=self._vault.encrypt(
                {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "token_type": token.get("token_type") or "Bearer",
                    "expiry": expiry,
                    "scope": scopes_raw,
                }
            ),
        )
        return {"connection_id": record.id, "account_label": record.account_label, "provider": record.provider}

    def _google_request(
        self,
        *,
        record: ConnectionRecord,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._oauth.google_request(record=record, method=method, path=path, params=params, json_body=json_body)

    def _google_binary_request(
        self,
        *,
        record: ConnectionRecord,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._oauth.google_binary_request(record=record, path=path, params=params)

    def _slack_request(
        self,
        *,
        record: ConnectionRecord,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._oauth.slack_request(record=record, method=method, path=path, json_body=json_body)

    def _microsoft_request(
        self,
        *,
        record: ConnectionRecord,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return self._oauth.microsoft_request(
            record=record,
            method=method,
            path=path,
            params=params,
            json_body=json_body,
            headers=headers,
        )

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
            return self._google_request(record=record, method="GET", path=f"gmail/v1/users/me/messages/{message_id}", params={"format": "full"})
        if tool_name == "gmail_send_message":
            to = str(payload.get("to", "")).strip()
            subject = str(payload.get("subject", "")).strip()
            body = str(payload.get("body", "")).strip()
            if not to or not subject or not body:
                raise HTTPException(status_code=400, detail="to, subject, and body are required.")
            raw = base64.urlsafe_b64encode(
                f"To: {to}\r\nSubject: {subject}\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n{body}".encode("utf-8")
            ).decode("ascii")
            return self._google_request(record=record, method="POST", path="gmail/v1/users/me/messages/send", json_body={"raw": raw})
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
            metadata = self._google_request(record=record, method="GET", path=f"drive/v3/files/{file_id}", params={"fields": "id,name,mimeType,size"})
            mime_type = str(metadata.get("mimeType", ""))
            if mime_type.startswith("application/vnd.google-apps"):
                return self._google_binary_request(record=record, path=f"drive/v3/files/{file_id}/export", params={"mimeType": "text/plain"}) | {"metadata": metadata}
            return self._google_binary_request(record=record, path=f"drive/v3/files/{file_id}", params={"alt": "media"}) | {"metadata": metadata}
        if tool_name == "calendar_list_events":
            calendar_id = str(payload.get("calendar_id", "primary")).strip() or "primary"
            params = {"maxResults": int(payload.get("limit", 10)), "singleEvents": True, "orderBy": "startTime"}
            if payload.get("time_min"):
                params["timeMin"] = str(payload["time_min"])
            if payload.get("time_max"):
                params["timeMax"] = str(payload["time_max"])
            return self._google_request(record=record, method="GET", path=f"calendar/v3/calendars/{calendar_id}/events", params=params)
        if tool_name == "calendar_create_event":
            calendar_id = str(payload.get("calendar_id", "primary")).strip() or "primary"
            title = str(payload.get("title", "")).strip()
            start = str(payload.get("start", "")).strip()
            end = str(payload.get("end", "")).strip()
            if not title or not start or not end:
                raise HTTPException(status_code=400, detail="title, start, and end are required.")
            attendees = payload.get("attendees")
            attendees_payload = [{"email": item} for item in attendees if isinstance(item, str) and item.strip()] if isinstance(attendees, list) else []
            body = {"summary": title, "description": str(payload.get("description", "")).strip() or None, "start": {"dateTime": start}, "end": {"dateTime": end}}
            if attendees_payload:
                body["attendees"] = attendees_payload
            return self._google_request(record=record, method="POST", path=f"calendar/v3/calendars/{calendar_id}/events", json_body=body)
        if tool_name == "outlook_search_messages":
            query = str(payload.get("query", "")).strip()
            limit = int(payload.get("limit", 10))
            params: dict[str, Any] = {"$top": max(1, min(limit, 50)), "$select": "id,subject,from,toRecipients,receivedDateTime,bodyPreview,webLink", "$orderby": "receivedDateTime DESC"}
            if query:
                search_query = query.replace('"', '\\"')
                params["$search"] = f'"{search_query}"'
            return self._microsoft_request(record=record, method="GET", path="v1.0/me/messages", params=params, headers={"ConsistencyLevel": "eventual"} if query else None)
        if tool_name == "outlook_get_message":
            message_id = str(payload.get("message_id", "")).strip()
            if not message_id:
                raise HTTPException(status_code=400, detail="message_id is required.")
            return self._microsoft_request(record=record, method="GET", path=f"v1.0/me/messages/{message_id}")
        if tool_name == "outlook_send_message":
            to = str(payload.get("to", "")).strip()
            subject = str(payload.get("subject", "")).strip()
            body = str(payload.get("body", "")).strip()
            if not to or not subject or not body:
                raise HTTPException(status_code=400, detail="to, subject, and body are required.")
            return self._microsoft_request(
                record=record,
                method="POST",
                path="v1.0/me/sendMail",
                json_body={"message": {"subject": subject, "body": {"contentType": "Text", "content": body}, "toRecipients": [{"emailAddress": {"address": to}}]}, "saveToSentItems": True},
            )
        if tool_name == "outlook_reply_message":
            message_id = str(payload.get("message_id", "")).strip()
            body = str(payload.get("body", "")).strip()
            reply_all = bool(payload.get("reply_all", False))
            if not message_id or not body:
                raise HTTPException(status_code=400, detail="message_id and body are required.")
            action = "replyAll" if reply_all else "reply"
            return self._microsoft_request(record=record, method="POST", path=f"v1.0/me/messages/{message_id}/{action}", json_body={"comment": body})
        if tool_name == "outlook_list_events":
            params: dict[str, Any] = {"$top": max(1, min(int(payload.get("limit", 10)), 50)), "$orderby": "start/dateTime", "$select": "id,subject,organizer,attendees,start,end,location,bodyPreview,webLink"}
            filters: list[str] = []
            if payload.get("time_min"):
                filters.append(f"start/dateTime ge '{str(payload['time_min'])}'")
            if payload.get("time_max"):
                filters.append(f"end/dateTime le '{str(payload['time_max'])}'")
            if filters:
                params["$filter"] = " and ".join(filters)
            return self._microsoft_request(record=record, method="GET", path="v1.0/me/events", params=params, headers={"Prefer": 'outlook.timezone="UTC"'})
        if tool_name == "outlook_get_event":
            event_id = str(payload.get("event_id", "")).strip()
            if not event_id:
                raise HTTPException(status_code=400, detail="event_id is required.")
            return self._microsoft_request(
                record=record,
                method="GET",
                path=f"v1.0/me/events/{event_id}",
                params={"$select": "id,subject,organizer,attendees,start,end,location,bodyPreview,webLink,body"},
                headers={"Prefer": 'outlook.timezone="UTC"'},
            )
        if tool_name == "outlook_create_event":
            title = str(payload.get("title", "")).strip()
            start = str(payload.get("start", "")).strip()
            end = str(payload.get("end", "")).strip()
            if not title or not start or not end:
                raise HTTPException(status_code=400, detail="title, start, and end are required.")
            attendees = payload.get("attendees")
            attendees_payload = [{"emailAddress": {"address": item}, "type": "required"} for item in attendees if isinstance(item, str) and item.strip()] if isinstance(attendees, list) else []
            event_body: dict[str, Any] = {"subject": title, "start": {"dateTime": start, "timeZone": "UTC"}, "end": {"dateTime": end, "timeZone": "UTC"}}
            description = str(payload.get("description", "")).strip()
            if description:
                event_body["body"] = {"contentType": "Text", "content": description}
            if attendees_payload:
                event_body["attendees"] = attendees_payload
            return self._microsoft_request(record=record, method="POST", path="v1.0/me/events", json_body=event_body)
        if tool_name == "outlook_update_event":
            event_id = str(payload.get("event_id", "")).strip()
            if not event_id:
                raise HTTPException(status_code=400, detail="event_id is required.")
            patch_body: dict[str, Any] = {}
            title = payload.get("title")
            if isinstance(title, str) and title.strip():
                patch_body["subject"] = title.strip()
            start = payload.get("start")
            if isinstance(start, str) and start.strip():
                patch_body["start"] = {"dateTime": start.strip(), "timeZone": "UTC"}
            end = payload.get("end")
            if isinstance(end, str) and end.strip():
                patch_body["end"] = {"dateTime": end.strip(), "timeZone": "UTC"}
            description = payload.get("description")
            if isinstance(description, str):
                patch_body["body"] = {"contentType": "Text", "content": description}
            attendees = payload.get("attendees")
            if isinstance(attendees, list):
                patch_body["attendees"] = [{"emailAddress": {"address": item}, "type": "required"} for item in attendees if isinstance(item, str) and item.strip()]
            if not patch_body:
                raise HTTPException(status_code=400, detail="At least one field to update is required.")
            return self._microsoft_request(record=record, method="PATCH", path=f"v1.0/me/events/{event_id}", json_body=patch_body)
        if tool_name == "outlook_delete_event":
            event_id = str(payload.get("event_id", "")).strip()
            if not event_id:
                raise HTTPException(status_code=400, detail="event_id is required.")
            return self._microsoft_request(record=record, method="DELETE", path=f"v1.0/me/events/{event_id}")
        if tool_name == "sheets_read_values":
            spreadsheet_id = str(payload.get("spreadsheet_id", "")).strip()
            range_name = str(payload.get("range", "")).strip()
            if not spreadsheet_id or not range_name:
                raise HTTPException(status_code=400, detail="spreadsheet_id and range are required.")
            return self._google_request(record=record, method="GET", path=f"sheets/v4/spreadsheets/{spreadsheet_id}/values/{range_name}")
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
            listed = self._slack_request(record=record, method="POST", path="conversations.list", json_body={"limit": int(payload.get("limit", 20))})
            return {"channels": listed.get("channels", [])}
        if tool_name == "slack_search_messages":
            query = str(payload.get("query", "")).strip()
            if not query:
                raise HTTPException(status_code=400, detail="query is required.")
            return self._slack_request(record=record, method="POST", path="search.messages", json_body={"query": query, "count": int(payload.get("limit", 10))})
        if tool_name == "slack_post_message":
            channel = str(payload.get("channel", "")).strip()
            message = str(payload.get("text", "")).strip()
            if not channel or not message:
                raise HTTPException(status_code=400, detail="channel and text are required.")
            return self._slack_request(record=record, method="POST", path="chat.postMessage", json_body={"channel": channel, "text": message})
        raise HTTPException(status_code=400, detail=f"Unsupported integration tool: {tool_name}")


__all__ = [
    "AuthorizableProviderName",
    "AuthorizationStart",
    "ConnectionRecord",
    "ConnectionService",
    "GOOGLE_CONNECTOR_CAPABILITIES",
    "GOOGLE_CONNECTOR_SCOPES",
    "GOOGLE_SCOPES",
    "MICROSOFT_CONNECTOR_SCOPES",
    "ProviderName",
    "SLACK_SCOPES",
    "SUPPORTED_CONNECTION_PROVIDERS",
    "WRITE_TOOL_NAMES",
]
