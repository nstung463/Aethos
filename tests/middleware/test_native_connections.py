from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from src.ai.middleware.native_connections import NativeConnectionsMiddleware, build_native_connections_section
from src.app.repositories.connection_repository import ConnectionRecord


def _connection(
    *,
    provider: str = "google",
    account_label: str = "work@example.com",
    status: str = "active",
    capabilities: list[str] | None = None,
    tools_enabled: bool = True,
) -> ConnectionRecord:
    return ConnectionRecord(
        id="conn_123",
        provider=provider,  # type: ignore[arg-type]
        owner_user_id="user-a",
        project_key="project-1",
        account_label=account_label,
        status=status,
        capabilities=capabilities or ["gmail", "drive"],
        scopes=["scope:a"],
        auth_type="oauth2",
        tools_enabled=tools_enabled,
        created_at=1,
        updated_at=2,
        last_refresh_at=2,
        last_error=None,
    )


@dataclass
class _FakeModelRequest:
    state: dict[str, Any]
    system_prompt: str | None = None

    def override(self, **kwargs: Any) -> "_FakeModelRequest":
        return _FakeModelRequest(
            state=self.state,
            system_prompt=kwargs.get("system_prompt", self.system_prompt),
        )


class _FakeRuntime:
    pass


class _FakeConnectionService:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs

    def list_effective_connections(self, *, owner_user_id: str) -> list[ConnectionRecord]:
        assert owner_user_id == "user-a"
        return [_connection(), _connection(provider="slack", account_label="workspace-name", capabilities=["chat"])]


def test_build_native_connections_section_lists_accounts() -> None:
    section = build_native_connections_section([_connection()])

    assert section is not None
    assert "# Native Connections" in section
    assert "work@example.com" in section
    assert "gmail, drive" in section


def test_build_native_connections_section_returns_none_for_empty() -> None:
    assert build_native_connections_section([]) is None


def test_build_native_connections_section_omits_disabled_connections() -> None:
    section = build_native_connections_section([
        _connection(account_label="enabled@example.com"),
        _connection(account_label="disabled@example.com", tools_enabled=False),
    ])

    assert section is not None
    assert "enabled@example.com" in section
    assert "disabled@example.com" not in section


def test_build_native_connections_section_returns_none_when_only_disabled() -> None:
    assert build_native_connections_section([
        _connection(account_label="disabled@example.com", tools_enabled=False),
    ]) is None


def test_middleware_before_agent_computes_and_caches(monkeypatch) -> None:
    monkeypatch.setattr("src.ai.middleware.native_connections.ConnectionService", _FakeConnectionService)
    middleware = NativeConnectionsMiddleware(root_dir=".", owner_user_id="user-a")

    update = middleware.before_agent(state={}, runtime=_FakeRuntime())
    assert update is not None
    assert "work@example.com" in (update["_native_connections"] or "")

    cached = middleware.before_agent(state={"_native_connections": update["_native_connections"]}, runtime=_FakeRuntime())
    assert cached is None


def test_middleware_async_matches_sync(monkeypatch) -> None:
    monkeypatch.setattr("src.ai.middleware.native_connections.ConnectionService", _FakeConnectionService)
    middleware = NativeConnectionsMiddleware(root_dir=".", owner_user_id="user-a")

    update = asyncio.run(middleware.abefore_agent(state={}, runtime=_FakeRuntime()))

    assert update is not None
    assert "workspace-name" in (update["_native_connections"] or "")


def test_modify_request_appends_native_connection_section() -> None:
    middleware = NativeConnectionsMiddleware(root_dir=".", owner_user_id=None)
    request = _FakeModelRequest(
        state={"_native_connections": "# Native Connections\n- google: work@example.com"},
        system_prompt="Base prompt.",
    )

    updated = middleware.modify_request(request)

    assert updated.system_prompt is not None
    assert "Base prompt." in updated.system_prompt
    assert "work@example.com" in updated.system_prompt
