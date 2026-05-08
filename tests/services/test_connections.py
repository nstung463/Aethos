from __future__ import annotations

from pathlib import Path

import pytest
import httpx
from fastapi import HTTPException

from src.app.core.settings import get_settings
from src.ai.tools.integrations import build_integration_tools
from src.app.services.connections import (
    ConnectionRepository,
    ConnectionService,
    GOOGLE_CONNECTOR_SCOPES,
    SecretVault,
)
from src.app.services.storage_paths import StoragePathsService


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace


def test_secret_vault_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ETHOS_SECRETS_KEY", "test-secret-key")
    get_settings.cache_clear()

    vault = SecretVault()
    payload = {"access_token": "access", "refresh_token": "refresh", "expiry": 1234}

    encrypted = vault.encrypt(payload)

    assert vault.decrypt(encrypted) == payload


def test_secret_vault_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ETHOS_SECRETS_KEY", raising=False)
    get_settings.cache_clear()

    vault = SecretVault()

    with pytest.raises(HTTPException) as exc:
        vault.encrypt({"access_token": "x"})

    assert exc.value.status_code == 503


def test_connection_repository_crud_and_secret_isolation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ETHOS_SECRETS_KEY", "test-secret-key")
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


def test_begin_authorization_builds_provider_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ETHOS_PUBLIC_BASE_URL", "http://127.0.0.1:8080")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv("SLACK_CLIENT_ID", "slack-client")
    monkeypatch.setenv("SLACK_CLIENT_SECRET", "slack-secret")
    monkeypatch.setenv("ETHOS_SECRETS_KEY", "test-secret-key")
    get_settings.cache_clear()
    workspace = _workspace(tmp_path)
    service = ConnectionService(workspace_root=workspace)

    gmail = service.begin_authorization(provider="google-gmail", owner_user_id="user-a", redirect_to="http://localhost/ui")
    drive = service.begin_authorization(provider="google-drive", owner_user_id="user-a")
    calendar = service.begin_authorization(provider="google-calendar", owner_user_id="user-a")
    sheets = service.begin_authorization(provider="google-sheets", owner_user_id="user-a")
    slack = service.begin_authorization(provider="slack", owner_user_id="user-a")

    assert "accounts.google.com" in gmail.authorization_url
    assert "state=" in gmail.authorization_url
    assert "include_granted_scopes=true" in gmail.authorization_url
    assert "https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fgmail.modify" in gmail.authorization_url
    assert "https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fdrive.readonly" not in gmail.authorization_url
    assert "https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fdrive.readonly" in drive.authorization_url
    assert "https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fcalendar" in calendar.authorization_url
    assert "https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fspreadsheets" in sheets.authorization_url
    assert "slack.com/oauth/v2/authorize" in slack.authorization_url


def test_build_integration_tools_only_includes_active_connections(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    storage = StoragePathsService()
    repo = ConnectionRepository(storage.integrations_db_path(workspace))
    project_key = storage.project_key(workspace)
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
    repo = ConnectionRepository(storage.integrations_db_path(workspace))
    project_key = storage.project_key(workspace)
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
    repo = ConnectionRepository(storage.integrations_db_path(workspace))
    project_key = storage.project_key(workspace)
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
    monkeypatch.setenv("ETHOS_SECRETS_KEY", "test-secret-key")
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


def test_google_token_exchange_uses_provider_callback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ETHOS_PUBLIC_BASE_URL", "http://127.0.0.1:8080")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "google-client")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv("ETHOS_SECRETS_KEY", "test-secret-key")
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
