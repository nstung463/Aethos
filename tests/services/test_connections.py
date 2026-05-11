from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import httpx
from fastapi import HTTPException

from src.app.core.settings import get_settings
from src.ai.tools.integrations import build_integration_tools
from src.app.services.connections import (
    ConnectionRepository,
    ConnectionService,
    GOOGLE_CONNECTOR_SCOPES,
    MICROSOFT_CONNECTOR_SCOPES,
    SecretVault,
)
from src.config import MCPServerSpec, _native_provider_for_mcp_server
from src.app.services.storage_paths import StoragePathsService


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace


def test_secret_vault_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AETHOS_SECRETS_KEY", "test-secret-key")
    get_settings.cache_clear()

    vault = SecretVault()
    payload = {"access_token": "access", "refresh_token": "refresh", "expiry": 1234}

    encrypted = vault.encrypt(payload)

    assert vault.decrypt(encrypted) == payload


def test_secret_vault_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AETHOS_SECRETS_KEY", raising=False)
    get_settings.cache_clear()

    vault = SecretVault()

    with pytest.raises(HTTPException) as exc:
        vault.encrypt({"access_token": "x"})

    assert exc.value.status_code == 503


def test_connection_repository_crud_and_secret_isolation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AETHOS_SECRETS_KEY", "test-secret-key")
    get_settings.cache_clear()
    workspace = _workspace(tmp_path)
    storage = StoragePathsService()
    repo = ConnectionRepository(storage.integrations_db_path(workspace))
    vault = SecretVault()
    project_key = storage.project_key(workspace)

    record = repo.save_connection(
        connection_id=None,
        provider="google-gmail",
        owner_user_id="user-a",
        project_key=project_key,
        account_label="work@example.com",
        status="active",
        capabilities=["gmail"],
        scopes=["scope:a"],
    )
    repo.save_secret(connection_id=record.id, ciphertext=vault.encrypt({"access_token": "secret-token"}))

    listed = repo.list_connections(owner_user_id="user-a", project_key=project_key)
    other_user = repo.list_connections(owner_user_id="user-b", project_key=project_key)

    assert [item.id for item in listed] == [record.id]
    assert other_user == []
    assert "secret-token" not in str(listed[0])
    assert listed[0].tools_enabled is True
    assert repo.load_secret(connection_id=record.id) is not None
    assert repo.delete_connection(connection_id=record.id, owner_user_id="user-a") is True
    assert repo.get_connection(connection_id=record.id) is None
    assert repo.load_secret(connection_id=record.id) is None


def test_connection_repository_creates_distinct_records_per_provider_account(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    storage = StoragePathsService()
    repo = ConnectionRepository(storage.integrations_db_path(workspace))
    project_key = storage.project_key(workspace)

    first = repo.save_connection(
        connection_id=None,
        provider="google-gmail",
        owner_user_id="user-a",
        project_key=project_key,
        account_label="first@example.com",
        status="active",
        capabilities=["gmail"],
        scopes=["scope:a"],
    )
    second = repo.save_connection(
        connection_id=None,
        provider="google-gmail",
        owner_user_id="user-a",
        project_key=project_key,
        account_label="second@example.com",
        status="active",
        capabilities=["gmail"],
        scopes=["scope:a"],
    )

    listed = repo.list_connections(owner_user_id="user-a", project_key=project_key)

    assert first.id != second.id
    assert {item.id for item in listed} == {first.id, second.id}
    assert {item.account_label for item in listed} == {"first@example.com", "second@example.com"}


def test_connection_repository_reuses_existing_record_for_same_provider_account(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    storage = StoragePathsService()
    repo = ConnectionRepository(storage.integrations_db_path(workspace))
    project_key = storage.project_key(workspace)

    first = repo.save_connection(
        connection_id=None,
        provider="google-gmail",
        owner_user_id="user-a",
        project_key=project_key,
        account_label="same@example.com",
        status="active",
        capabilities=["gmail"],
        scopes=["scope:a"],
    )
    second = repo.save_connection(
        connection_id=None,
        provider="google-gmail",
        owner_user_id="user-a",
        project_key=project_key,
        account_label="same@example.com",
        status="active",
        capabilities=["gmail"],
        scopes=["scope:b"],
    )

    listed = repo.list_connections(owner_user_id="user-a", project_key=project_key)

    assert second.id == first.id
    assert [item.id for item in listed] == [first.id]
    assert listed[0].scopes == ["scope:b"]


def test_oauth_state_round_trip_keeps_workspace_root(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    storage = StoragePathsService()
    repo = ConnectionRepository(storage.integrations_db_path(workspace))

    state = repo.create_oauth_state(
        provider="google-gmail",
        user_id="user-a",
        project_key=storage.project_key(workspace),
        workspace_root=str(workspace),
        redirect_to="http://localhost:3000/settings",
    )
    payload = repo.consume_oauth_state(state=state, provider="google-gmail")

    assert payload["workspace_root"] == str(workspace.resolve())
    assert payload["redirect_to"] == "http://localhost:3000/settings"


def test_for_oauth_state_restores_user_scope(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    user_service = ConnectionService(workspace_root=workspace, scope="user")

    state = user_service._repo.create_oauth_state(
        provider="google-gmail",
        user_id="user-a",
        project_key=user_service.project_key,
        workspace_root=str(user_service._workspace_root),
        redirect_to=None,
    )
    restored = ConnectionService.for_oauth_state(state=state, provider="google-gmail")

    assert restored.scope == "user"
    assert restored.project_key == "user"


def test_begin_authorization_builds_provider_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AETHOS_PUBLIC_BASE_URL", "http://127.0.0.1:8080")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv("SLACK_CLIENT_ID", "slack-client")
    monkeypatch.setenv("SLACK_CLIENT_SECRET", "slack-secret")
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "microsoft-client")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "microsoft-secret")
    monkeypatch.setenv("MICROSOFT_TENANT_ID", "common")
    monkeypatch.setenv("AETHOS_SECRETS_KEY", "test-secret-key")
    get_settings.cache_clear()
    workspace = _workspace(tmp_path)
    service = ConnectionService(workspace_root=workspace)

    gmail = service.begin_authorization(provider="google-gmail", owner_user_id="user-a", redirect_to="http://localhost/ui")
    drive = service.begin_authorization(provider="google-drive", owner_user_id="user-a")
    calendar = service.begin_authorization(provider="google-calendar", owner_user_id="user-a")
    sheets = service.begin_authorization(provider="google-sheets", owner_user_id="user-a")
    outlook_mail = service.begin_authorization(provider="microsoft-outlook-mail", owner_user_id="user-a")
    outlook_calendar = service.begin_authorization(provider="microsoft-outlook-calendar", owner_user_id="user-a")
    slack = service.begin_authorization(provider="slack", owner_user_id="user-a")

    assert "accounts.google.com" in gmail.authorization_url
    assert "state=" in gmail.authorization_url
    assert "include_granted_scopes=true" in gmail.authorization_url
    assert "https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fgmail.modify" in gmail.authorization_url
    assert "https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fdrive.readonly" not in gmail.authorization_url
    assert "https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fdrive.readonly" in drive.authorization_url
    assert "https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fcalendar" in calendar.authorization_url
    assert "https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fspreadsheets" in sheets.authorization_url
    assert "login.microsoftonline.com/common/oauth2/v2.0/authorize" in outlook_mail.authorization_url
    assert "Mail.Read" in outlook_mail.authorization_url
    assert "Mail.Send" in outlook_mail.authorization_url
    assert "Calendars.Read" in outlook_calendar.authorization_url
    assert "Calendars.ReadWrite" in outlook_calendar.authorization_url
    assert "slack.com/oauth/v2/authorize" in slack.authorization_url


def test_build_integration_tools_only_includes_active_connections(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    storage = StoragePathsService()
    user_scope_root = storage.user_settings_dir() / "__user_scope__"
    repo = ConnectionRepository(storage.integrations_db_path(user_scope_root))
    project_key = "user"
    repo.save_connection(
        connection_id=None,
        provider="google-gmail",
        owner_user_id="user-a",
        project_key=project_key,
        account_label="broken@example.com",
        status="error",
        capabilities=["gmail"],
        scopes=["scope:a"],
    )

    tools = build_integration_tools(root_dir=str(workspace), owner_user_id="user-a")

    assert tools == []


def test_build_integration_tools_skips_connections_with_tools_disabled(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    storage = StoragePathsService()
    user_scope_root = storage.user_settings_dir() / "__user_scope__"
    repo = ConnectionRepository(storage.integrations_db_path(user_scope_root))
    project_key = "user"
    repo.save_connection(
        connection_id=None,
        provider="google-gmail",
        owner_user_id="user-a",
        project_key=project_key,
        account_label="work@example.com",
        status="active",
        capabilities=["gmail"],
        scopes=["scope:a"],
        tools_enabled=False,
    )

    tools = build_integration_tools(root_dir=str(workspace), owner_user_id="user-a")

    assert tools == []


def test_build_integration_tools_only_exposes_enabled_providers(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    storage = StoragePathsService()
    user_scope_root = storage.user_settings_dir() / "__user_scope__"
    repo = ConnectionRepository(storage.integrations_db_path(user_scope_root))
    project_key = "user"
    for provider, capabilities, enabled in (
        ("google-gmail", ["gmail"], True),
        ("google-drive", ["drive"], True),
        ("google-calendar", ["calendar"], False),
        ("google-sheets", ["sheets"], False),
    ):
        repo.save_connection(
            connection_id=None,
            provider=provider,
            owner_user_id="user-a",
            project_key=project_key,
            account_label=f"{provider}@example.com",
            status="active",
            capabilities=capabilities,
            scopes=["scope:a"],
            tools_enabled=enabled,
        )

    tool_names = {tool.name for tool in build_integration_tools(root_dir=str(workspace), owner_user_id="user-a")}

    assert "gmail_search_messages" in tool_names
    assert "drive_search_files" in tool_names
    assert "calendar_list_events" not in tool_names
    assert "sheets_read_values" not in tool_names

def test_build_integration_tools_exposes_outlook_tools(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    storage = StoragePathsService()
    user_scope_root = storage.user_settings_dir() / "__user_scope__"
    repo = ConnectionRepository(storage.integrations_db_path(user_scope_root))
    for provider, capabilities in (
        ("microsoft-outlook-mail", ["outlook_mail"]),
        ("microsoft-outlook-calendar", ["outlook_calendar"]),
    ):
        repo.save_connection(
            connection_id=None,
            provider=provider,
            owner_user_id="user-a",
            project_key="user",
            account_label=f"{provider}@example.com",
            status="active",
            capabilities=capabilities,
            scopes=["scope:a"],
            tools_enabled=True,
        )

    tool_names = {tool.name for tool in build_integration_tools(root_dir=str(workspace), owner_user_id="user-a")}

    assert "outlook_search_messages" in tool_names
    assert "outlook_get_message" in tool_names
    assert "outlook_send_message" in tool_names
    assert "outlook_reply_message" in tool_names
    assert "outlook_list_events" in tool_names
    assert "outlook_get_event" in tool_names
    assert "outlook_create_event" in tool_names
    assert "outlook_update_event" in tool_names
    assert "outlook_delete_event" in tool_names

def test_outlook_reply_message_dispatches_to_graph_reply_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _workspace(tmp_path)
    service = ConnectionService(workspace_root=workspace)
    captured: dict[str, Any] = {}

    def fake_request(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(service, "_microsoft_request", fake_request)

    result = service._dispatch_tool(
        record=service._repo.save_connection(
            connection_id=None,
            provider="microsoft-outlook-mail",
            owner_user_id="user-a",
            project_key=service.project_key,
            account_label="mail@example.com",
            status="active",
            capabilities=["outlook_mail"],
            scopes=["scope:a"],
        ),
        tool_name="outlook_reply_message",
        payload={"message_id": "msg-123", "body": "Thanks!", "reply_all": True},
    )

    assert result == {"ok": True}
    assert captured["method"] == "POST"
    assert captured["path"] == "v1.0/me/messages/msg-123/replyAll"
    assert captured["json_body"] == {"comment": "Thanks!"}

def test_outlook_update_event_requires_fields(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    service = ConnectionService(workspace_root=workspace)
    record = service._repo.save_connection(
        connection_id=None,
        provider="microsoft-outlook-calendar",
        owner_user_id="user-a",
        project_key=service.project_key,
        account_label="calendar@example.com",
        status="active",
        capabilities=["outlook_calendar"],
        scopes=["scope:a"],
    )

    with pytest.raises(HTTPException) as exc:
        service._dispatch_tool(
            record=record,
            tool_name="outlook_update_event",
            payload={"event_id": "evt-1"},
        )

    assert exc.value.status_code == 400
    assert "At least one field to update is required." in str(exc.value.detail)

def test_outlook_calendar_tools_dispatch_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _workspace(tmp_path)
    service = ConnectionService(workspace_root=workspace)
    calls: list[dict[str, Any]] = []

    def fake_request(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr(service, "_microsoft_request", fake_request)
    record = service._repo.save_connection(
        connection_id=None,
        provider="microsoft-outlook-calendar",
        owner_user_id="user-a",
        project_key=service.project_key,
        account_label="calendar@example.com",
        status="active",
        capabilities=["outlook_calendar"],
        scopes=["scope:a"],
    )

    service._dispatch_tool(
        record=record,
        tool_name="outlook_get_event",
        payload={"event_id": "evt-get"},
    )
    service._dispatch_tool(
        record=record,
        tool_name="outlook_update_event",
        payload={"event_id": "evt-update", "title": "Updated title"},
    )
    service._dispatch_tool(
        record=record,
        tool_name="outlook_delete_event",
        payload={"event_id": "evt-delete"},
    )

    assert calls[0]["method"] == "GET"
    assert calls[0]["path"] == "v1.0/me/events/evt-get"
    assert calls[1]["method"] == "PATCH"
    assert calls[1]["path"] == "v1.0/me/events/evt-update"
    assert calls[1]["json_body"]["subject"] == "Updated title"
    assert calls[2]["method"] == "DELETE"
    assert calls[2]["path"] == "v1.0/me/events/evt-delete"


def test_project_scope_falls_back_to_user_connections(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    storage = StoragePathsService()
    user_scope_root = storage.user_settings_dir() / "__user_scope__"
    repo = ConnectionRepository(storage.integrations_db_path(user_scope_root))
    repo.save_connection(
        connection_id=None,
        provider="google-gmail",
        owner_user_id="user-a",
        project_key="user",
        account_label="user@example.com",
        status="active",
        capabilities=["gmail"],
        scopes=["scope:a"],
    )

    service = ConnectionService(workspace_root=workspace)
    records = service.list_effective_connections(owner_user_id="user-a")

    assert [record.account_label for record in records] == ["user@example.com"]
    assert service.get_default_connection(provider="google-gmail", owner_user_id="user-a") is not None


def test_project_scope_prefers_project_connections_over_user_fallback(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    storage = StoragePathsService()
    project_repo = ConnectionRepository(storage.integrations_db_path(workspace))
    user_scope_root = storage.user_settings_dir() / "__user_scope__"
    user_repo = ConnectionRepository(storage.integrations_db_path(user_scope_root))
    project_key = storage.project_key(workspace)
    user_repo.save_connection(
        connection_id=None,
        provider="google-gmail",
        owner_user_id="user-a",
        project_key="user",
        account_label="user@example.com",
        status="active",
        capabilities=["gmail"],
        scopes=["scope:user"],
    )
    project_record = project_repo.save_connection(
        connection_id=None,
        provider="google-gmail",
        owner_user_id="user-a",
        project_key=project_key,
        account_label="project@example.com",
        status="active",
        capabilities=["gmail"],
        scopes=["scope:project"],
    )

    service = ConnectionService(workspace_root=workspace)
    records = service.list_effective_connections(owner_user_id="user-a")
    default = service.get_default_connection(provider="google-gmail", owner_user_id="user-a")

    assert [record.account_label for record in records] == ["project@example.com"]
    assert default is not None
    assert default.id == project_record.id


def test_build_integration_tools_uses_user_fallback_when_project_has_no_connection(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    storage = StoragePathsService()
    user_scope_root = storage.user_settings_dir() / "__user_scope__"
    repo = ConnectionRepository(storage.integrations_db_path(user_scope_root))
    repo.save_connection(
        connection_id=None,
        provider="google-drive",
        owner_user_id="user-a",
        project_key="user",
        account_label="drive@example.com",
        status="active",
        capabilities=["drive"],
        scopes=["scope:a"],
        tools_enabled=True,
    )

    tool_names = {tool.name for tool in build_integration_tools(root_dir=str(workspace), owner_user_id="user-a")}

    assert "drive_search_files" in tool_names


def test_repository_default_connection_skips_tools_disabled_accounts(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    storage = StoragePathsService()
    repo = ConnectionRepository(storage.integrations_db_path(workspace))
    project_key = storage.project_key(workspace)
    enabled = repo.save_connection(
        connection_id=None,
        provider="google-gmail",
        owner_user_id="user-a",
        project_key=project_key,
        account_label="enabled@example.com",
        status="active",
        capabilities=["gmail"],
        scopes=["scope:a"],
    )
    repo.save_connection(
        connection_id=None,
        provider="google-gmail",
        owner_user_id="user-a",
        project_key=project_key,
        account_label="disabled@example.com",
        status="active",
        capabilities=["gmail"],
        scopes=["scope:a"],
        tools_enabled=False,
    )

    default = repo.get_default_connection(
        provider="google-gmail",
        owner_user_id="user-a",
        project_key=project_key,
    )

    assert default is not None
    assert default.id == enabled.id


def test_connection_service_can_toggle_tools_enabled(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    storage = StoragePathsService()
    repo = ConnectionRepository(storage.integrations_db_path(workspace))
    project_key = storage.project_key(workspace)
    record = repo.save_connection(
        connection_id=None,
        provider="google-gmail",
        owner_user_id="user-a",
        project_key=project_key,
        account_label="work@example.com",
        status="active",
        capabilities=["gmail"],
        scopes=["scope:a"],
    )
    service = ConnectionService(workspace_root=workspace)

    disabled = service.set_tools_enabled(connection_id=record.id, owner_user_id="user-a", enabled=False)
    enabled = service.set_tools_enabled(connection_id=record.id, owner_user_id="user-a", enabled=True)

    assert disabled.tools_enabled is False
    assert enabled.tools_enabled is True


def test_connection_service_blocks_disabled_connection_tool_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AETHOS_SECRETS_KEY", "test-secret-key")
    get_settings.cache_clear()
    workspace = _workspace(tmp_path)
    storage = StoragePathsService()
    repo = ConnectionRepository(storage.integrations_db_path(workspace))
    project_key = storage.project_key(workspace)
    record = repo.save_connection(
        connection_id=None,
        provider="google-calendar",
        owner_user_id="user-a",
        project_key=project_key,
        account_label="calendar@example.com",
        status="active",
        capabilities=["calendar"],
        scopes=["scope:a"],
        tools_enabled=False,
    )
    service = ConnectionService(workspace_root=workspace)

    with pytest.raises(HTTPException) as exc:
        service.perform_tool(
            provider="google-calendar",
            tool_name="calendar_list_events",
            owner_user_id="user-a",
            connection_id=record.id,
            payload={},
        )

    assert exc.value.status_code == 403
    assert "Tools are disabled" in str(exc.value.detail)


def test_test_connection_uses_user_fallback_in_project_scope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = _workspace(tmp_path)
    storage = StoragePathsService()
    user_scope_root = storage.user_settings_dir() / "__user_scope__"
    repo = ConnectionRepository(storage.integrations_db_path(user_scope_root))
    record = repo.save_connection(
        connection_id=None,
        provider="google-gmail",
        owner_user_id="user-a",
        project_key="user",
        account_label="user@example.com",
        status="active",
        capabilities=["gmail"],
        scopes=["scope:a"],
    )
    service = ConnectionService(workspace_root=workspace)
    monkeypatch.setattr(
        service,
        "_google_request",
        lambda **kwargs: {"email": "user@example.com"},
    )

    payload = service.test_connection(connection_id=record.id, owner_user_id="user-a")

    assert payload == {"ok": True, "provider": "google-gmail", "label": "user@example.com"}

def test_perform_tool_writes_audit_to_user_fallback_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AETHOS_SECRETS_KEY", "test-secret-key")
    get_settings.cache_clear()
    workspace = _workspace(tmp_path)
    storage = StoragePathsService()
    user_scope_root = storage.user_settings_dir() / "__user_scope__"
    user_repo = ConnectionRepository(storage.integrations_db_path(user_scope_root))
    record = user_repo.save_connection(
        connection_id=None,
        provider="google-gmail",
        owner_user_id="user-a",
        project_key="user",
        account_label="user@example.com",
        status="active",
        capabilities=["gmail"],
        scopes=["scope:a"],
        tools_enabled=True,
    )
    user_repo.save_secret(
        connection_id=record.id,
        ciphertext=SecretVault().encrypt({"access_token": "token", "refresh_token": "refresh"}),
    )
    service = ConnectionService(workspace_root=workspace)
    user_service = service._user_service()
    monkeypatch.setattr(user_service, "_google_request", lambda **kwargs: {"messages": []})
    monkeypatch.setattr(service, "_user_service", lambda: user_service)

    payload = service.perform_tool(
        provider="google-gmail",
        tool_name="gmail_search_messages",
        owner_user_id="user-a",
        connection_id=record.id,
        payload={"query": "from:alice@example.com", "limit": 5},
    )

    assert '"messages": []' in payload
    with user_repo._connect() as conn:
        audit_rows = conn.execute(
            "SELECT connection_id, tool_name, status FROM connection_audit WHERE connection_id = ?",
            (record.id,),
        ).fetchall()
    assert len(audit_rows) == 1
    assert audit_rows[0]["connection_id"] == record.id
    assert audit_rows[0]["tool_name"] == "gmail_search_messages"
    assert audit_rows[0]["status"] == "ok"

def test_perform_tool_user_fallback_uses_user_secret_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AETHOS_SECRETS_KEY", "test-secret-key")
    get_settings.cache_clear()
    workspace = _workspace(tmp_path)
    storage = StoragePathsService()
    user_scope_root = storage.user_settings_dir() / "__user_scope__"
    user_repo = ConnectionRepository(storage.integrations_db_path(user_scope_root))
    record = user_repo.save_connection(
        connection_id=None,
        provider="microsoft-outlook-calendar",
        owner_user_id="user-a",
        project_key="user",
        account_label="calendar@example.com",
        status="active",
        capabilities=["outlook_calendar"],
        scopes=["scope:a"],
        tools_enabled=True,
    )
    user_repo.save_secret(
        connection_id=record.id,
        ciphertext=SecretVault().encrypt({
            "access_token": "token",
            "refresh_token": "refresh",
            "expiry": 4102444800,
            "token_type": "Bearer",
        }),
    )

    service = ConnectionService(workspace_root=workspace)
    user_service = service._user_service()

    def fake_request(**kwargs: Any) -> dict[str, Any]:
        return {"value": []}

    monkeypatch.setattr(user_service, "_microsoft_request", fake_request)
    monkeypatch.setattr(service, "_user_service", lambda: user_service)
    monkeypatch.setattr(service, "_microsoft_request", lambda **kwargs: (_ for _ in ()).throw(AssertionError("project repo path should not be used")))

    payload = service.perform_tool(
        provider="microsoft-outlook-calendar",
        tool_name="outlook_list_events",
        owner_user_id="user-a",
        connection_id=record.id,
        payload={"limit": 5},
    )

    assert '"value": []' in payload


def test_google_connector_scopes_are_split_by_provider() -> None:
    assert GOOGLE_CONNECTOR_SCOPES["google-gmail"] == [
        "openid",
        "email",
        "profile",
        "https://www.googleapis.com/auth/gmail.modify",
    ]
    assert GOOGLE_CONNECTOR_SCOPES["google-drive"] == [
        "openid",
        "email",
        "profile",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    assert GOOGLE_CONNECTOR_SCOPES["google-calendar"] == [
        "openid",
        "email",
        "profile",
        "https://www.googleapis.com/auth/calendar",
    ]
    assert GOOGLE_CONNECTOR_SCOPES["google-sheets"] == [
        "openid",
        "email",
        "profile",
        "https://www.googleapis.com/auth/spreadsheets",
    ]

def test_microsoft_connector_scopes_are_split_by_provider() -> None:
    assert MICROSOFT_CONNECTOR_SCOPES["microsoft-outlook-mail"] == [
        "openid",
        "email",
        "profile",
        "offline_access",
        "User.Read",
        "Mail.Read",
        "Mail.Send",
    ]
    assert MICROSOFT_CONNECTOR_SCOPES["microsoft-outlook-calendar"] == [
        "openid",
        "email",
        "profile",
        "offline_access",
        "User.Read",
        "Calendars.Read",
        "Calendars.ReadWrite",
    ]

def test_native_provider_for_microsoft_mcp_server_detects_mail_and_calendar() -> None:
    mail_spec = MCPServerSpec(
        name="outlook-mail",
        connection={
            "transport": "streamable_http",
            "url": "https://graph.microsoft.com/mcp",
            "oauth": {"scopes": ["Mail.Read", "Mail.Send"]},
        },
    )
    calendar_spec = MCPServerSpec(
        name="outlook-calendar",
        connection={
            "transport": "streamable_http",
            "url": "https://graph.microsoft.com/mcp",
            "oauth": {"scopes": ["Calendars.Read", "Calendars.ReadWrite"]},
        },
    )

    assert _native_provider_for_mcp_server(mail_spec) == "microsoft-outlook-mail"
    assert _native_provider_for_mcp_server(calendar_spec) == "microsoft-outlook-calendar"

def test_native_provider_for_generic_graph_host_without_scope_is_not_forced() -> None:
    spec = MCPServerSpec(
        name="graph-tools",
        connection={
            "transport": "streamable_http",
            "url": "https://graph.microsoft.com/mcp",
        },
    )

    assert _native_provider_for_mcp_server(spec) is None


def test_google_token_exchange_uses_provider_callback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AETHOS_PUBLIC_BASE_URL", "http://127.0.0.1:8080")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv("AETHOS_SECRETS_KEY", "test-secret-key")
    get_settings.cache_clear()
    workspace = _workspace(tmp_path)
    service = ConnectionService(workspace_root=workspace)
    captured: dict[str, Any] = {}

    def fake_post(url: str, data: dict[str, str], timeout: int) -> httpx.Response:
        captured["url"] = url
        captured["data"] = data
        captured["timeout"] = timeout
        return httpx.Response(200, json={"access_token": "token"})

    monkeypatch.setattr(httpx, "post", fake_post)

    payload = service._exchange_google_code(provider="google-gmail", code="auth-code")

    assert payload["access_token"] == "token"
    assert captured["url"] == "https://oauth2.googleapis.com/token"
    assert captured["data"]["redirect_uri"] == "http://127.0.0.1:8080/v1/extensions/connections/google-gmail/callback"
