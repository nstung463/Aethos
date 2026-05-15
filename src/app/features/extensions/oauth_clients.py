"""OAuth provider helpers and HTTP request clients for native connections."""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException

from src.app.core.settings import Settings
from src.app.repositories.connection_repository import ConnectionRecord

ProviderName = Literal[
    "google",
    "google-gmail",
    "google-drive",
    "google-calendar",
    "google-sheets",
    "microsoft-outlook-mail",
    "microsoft-outlook-calendar",
    "slack",
]
AuthorizableProviderName = Literal[
    "google-gmail",
    "google-drive",
    "google-calendar",
    "google-sheets",
    "microsoft-outlook-mail",
    "microsoft-outlook-calendar",
    "slack",
]


@dataclass(frozen=True)
class AuthorizationStart:
    provider: ProviderName
    authorization_url: str
    state: str

_GOOGLE_IDENTITY_SCOPES = ["openid", "email", "profile"]
GOOGLE_CONNECTOR_SCOPES: dict[str, list[str]] = {
    "google-gmail": [*_GOOGLE_IDENTITY_SCOPES, "https://www.googleapis.com/auth/gmail.modify"],
    "google-drive": [*_GOOGLE_IDENTITY_SCOPES, "https://www.googleapis.com/auth/drive.readonly"],
    "google-calendar": [*_GOOGLE_IDENTITY_SCOPES, "https://www.googleapis.com/auth/calendar"],
    "google-sheets": [*_GOOGLE_IDENTITY_SCOPES, "https://www.googleapis.com/auth/spreadsheets"],
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
_MICROSOFT_IDENTITY_SCOPES = ["openid", "email", "profile", "offline_access", "User.Read"]
MICROSOFT_CONNECTOR_SCOPES: dict[str, list[str]] = {
    "microsoft-outlook-mail": [*_MICROSOFT_IDENTITY_SCOPES, "Mail.Read", "Mail.Send"],
    "microsoft-outlook-calendar": [*_MICROSOFT_IDENTITY_SCOPES, "Calendars.Read", "Calendars.ReadWrite"],
}
MICROSOFT_CONNECTOR_CAPABILITIES: dict[str, list[str]] = {
    "microsoft-outlook-mail": ["outlook_mail"],
    "microsoft-outlook-calendar": ["outlook_calendar"],
}
SLACK_SCOPES = ["channels:read", "groups:read", "chat:write", "search:read"]
WRITE_TOOL_NAMES = {
    "gmail_send_message",
    "calendar_create_event",
    "outlook_send_message",
    "outlook_reply_message",
    "outlook_create_event",
    "outlook_update_event",
    "outlook_delete_event",
    "sheets_append_values",
    "slack_post_message",
}


def now_epoch() -> int:
    return int(time.time())


def is_google_provider(provider: str) -> bool:
    return provider == "google" or provider in GOOGLE_CONNECTOR_SCOPES


def google_scopes_for_provider(provider: str) -> list[str]:
    return GOOGLE_CONNECTOR_SCOPES.get(provider, GOOGLE_SCOPES)


def google_capabilities_for_provider(provider: str) -> list[str]:
    return GOOGLE_CONNECTOR_CAPABILITIES.get(provider, GOOGLE_CONNECTOR_CAPABILITIES["google"])


def is_microsoft_provider(provider: str) -> bool:
    return provider in MICROSOFT_CONNECTOR_SCOPES


def microsoft_scopes_for_provider(provider: str) -> list[str]:
    return MICROSOFT_CONNECTOR_SCOPES[provider]


def microsoft_capabilities_for_provider(provider: str) -> list[str]:
    return MICROSOFT_CONNECTOR_CAPABILITIES[provider]


def ensure_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def build_authorization_start(
    *,
    settings: Settings,
    provider: AuthorizableProviderName,
    state: str,
    callback_redirect_uri: str,
) -> AuthorizationStart:
    public_base_url = (settings.aethos_public_base_url or "").rstrip("/")
    if is_google_provider(provider):
        if not settings.google_client_id or not settings.google_client_secret:
            raise HTTPException(status_code=503, detail="Google OAuth credentials are not configured.")
        query = urlencode(
            {
                "client_id": settings.google_client_id,
                "redirect_uri": callback_redirect_uri,
                "response_type": "code",
                "access_type": "offline",
                "prompt": "consent",
                "include_granted_scopes": "true",
                "scope": " ".join(google_scopes_for_provider(provider)),
                "state": state,
            }
        )
        return AuthorizationStart(provider=provider, authorization_url=f"https://accounts.google.com/o/oauth2/v2/auth?{query}", state=state)
    if provider == "slack":
        if not settings.slack_client_id or not settings.slack_client_secret:
            raise HTTPException(status_code=503, detail="Slack OAuth credentials are not configured.")
        query = urlencode(
            {
                "client_id": settings.slack_client_id,
                "redirect_uri": f"{public_base_url}/v1/extensions/connections/slack/callback",
                "scope": ",".join(SLACK_SCOPES),
                "state": state,
            }
        )
        return AuthorizationStart(provider=provider, authorization_url=f"https://slack.com/oauth/v2/authorize?{query}", state=state)
    if is_microsoft_provider(provider):
        if not settings.microsoft_client_id or not settings.microsoft_client_secret:
            raise HTTPException(status_code=503, detail="Microsoft OAuth credentials are not configured.")
        tenant = (settings.microsoft_tenant_id or "common").strip() or "common"
        query = urlencode(
            {
                "client_id": settings.microsoft_client_id,
                "response_type": "code",
                "redirect_uri": callback_redirect_uri,
                "response_mode": "query",
                "scope": " ".join(microsoft_scopes_for_provider(provider)),
                "state": state,
            }
        )
        return AuthorizationStart(
            provider=provider,
            authorization_url=f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?{query}",
            state=state,
        )
    raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")


class OAuthProviderClient:
    def __init__(self, settings: Settings, active_access_token: Any) -> None:
        self._settings = settings
        self._active_access_token = active_access_token

    def exchange_google_code(self, *, provider: ProviderName, code: str, callback_redirect_uri: str) -> dict[str, Any]:
        response = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": self._settings.google_client_id,
                "client_secret": self._settings.google_client_secret,
                "redirect_uri": callback_redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=20,
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail="Google token exchange failed.")
        return ensure_dict(response.json())

    def exchange_microsoft_code(self, *, provider: ProviderName, code: str, callback_redirect_uri: str) -> dict[str, Any]:
        tenant = (self._settings.microsoft_tenant_id or "common").strip() or "common"
        response = httpx.post(
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
            data={
                "client_id": self._settings.microsoft_client_id,
                "client_secret": self._settings.microsoft_client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": callback_redirect_uri,
            },
            timeout=20,
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail="Microsoft token exchange failed.")
        return ensure_dict(response.json())

    def exchange_slack_code(self, *, code: str) -> dict[str, Any]:
        response = httpx.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": self._settings.slack_client_id,
                "client_secret": self._settings.slack_client_secret,
                "code": code,
            },
            timeout=20,
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail="Slack token exchange failed.")
        payload = ensure_dict(response.json())
        if payload.get("ok") is False:
            raise HTTPException(status_code=502, detail=f"Slack OAuth error: {payload.get('error', 'unknown')}")
        return payload

    def refresh_google_token(self, secrets_data: dict[str, Any]) -> dict[str, Any]:
        refresh_token = str(secrets_data.get("refresh_token", "")).strip()
        if not refresh_token:
            raise HTTPException(status_code=400, detail="Google refresh token is missing.")
        response = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": self._settings.google_client_id,
                "client_secret": self._settings.google_client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=20,
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Google token refresh failed ({response.status_code}).")
        payload = ensure_dict(response.json())
        payload.setdefault("refresh_token", refresh_token)
        if isinstance(payload.get("expires_in"), int):
            payload["expiry"] = now_epoch() + int(payload["expires_in"])
        return payload

    def refresh_microsoft_token(self, secrets_data: dict[str, Any]) -> dict[str, Any]:
        refresh_token = str(secrets_data.get("refresh_token", "")).strip()
        if not refresh_token:
            raise HTTPException(status_code=400, detail="Microsoft refresh token is missing.")
        tenant = (self._settings.microsoft_tenant_id or "common").strip() or "common"
        response = httpx.post(
            f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
            data={
                "client_id": self._settings.microsoft_client_id,
                "client_secret": self._settings.microsoft_client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=20,
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Microsoft token refresh failed ({response.status_code}).")
        payload = ensure_dict(response.json())
        payload.setdefault("refresh_token", refresh_token)
        if isinstance(payload.get("expires_in"), int):
            payload["expiry"] = now_epoch() + int(payload["expires_in"])
        return payload

    def refresh_slack_token(self, secrets_data: dict[str, Any]) -> dict[str, Any]:
        refresh_token = str(secrets_data.get("refresh_token", "")).strip()
        if not refresh_token:
            raise HTTPException(status_code=400, detail="Slack refresh token is missing.")
        response = httpx.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": self._settings.slack_client_id,
                "client_secret": self._settings.slack_client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=20,
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Slack token refresh failed ({response.status_code}).")
        payload = ensure_dict(response.json())
        if payload.get("ok") is False:
            raise HTTPException(status_code=502, detail=f"Slack token refresh failed: {payload.get('error', 'unknown')}")
        payload.setdefault("refresh_token", refresh_token)
        if isinstance(payload.get("expires_in"), int):
            payload["expiry"] = now_epoch() + int(payload["expires_in"])
        return payload

    def google_request(
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
            return ensure_dict(response.json())
        return {"content": response.text}

    def google_binary_request(
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

    def slack_request(
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
            url=f"https://slack.com/api/{path.lstrip('/')}" ,
            json=json_body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Slack API request failed ({response.status_code}).")
        payload = ensure_dict(response.json())
        if payload.get("ok") is False:
            raise HTTPException(status_code=502, detail=f"Slack API error: {payload.get('error', 'unknown')}")
        return payload

    def microsoft_request(
        self,
        *,
        record: ConnectionRecord,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        token = self._active_access_token(record)
        merged_headers = {"Authorization": f"Bearer {token}"}
        if headers:
            merged_headers.update(headers)
        response = httpx.request(
            method=method,
            url=f"https://graph.microsoft.com/{path.lstrip('/')}" ,
            params=params,
            json=json_body,
            headers=merged_headers,
            timeout=30,
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Microsoft Graph request failed ({response.status_code}).")
        if not response.content:
            return {"ok": True}
        if "application/json" in response.headers.get("content-type", ""):
            data = response.json()
            return data if isinstance(data, dict) else {"value": data}
        return {"content": response.text}


__all__ = [
    "AuthorizationStart",
    "AuthorizableProviderName",
    "GOOGLE_CONNECTOR_CAPABILITIES",
    "GOOGLE_CONNECTOR_SCOPES",
    "GOOGLE_SCOPES",
    "MICROSOFT_CONNECTOR_CAPABILITIES",
    "MICROSOFT_CONNECTOR_SCOPES",
    "OAuthProviderClient",
    "ProviderName",
    "SLACK_SCOPES",
    "WRITE_TOOL_NAMES",
    "build_authorization_start",
    "ensure_dict",
    "google_capabilities_for_provider",
    "google_scopes_for_provider",
    "is_google_provider",
    "is_microsoft_provider",
    "microsoft_capabilities_for_provider",
    "microsoft_scopes_for_provider",
    "now_epoch",
]
