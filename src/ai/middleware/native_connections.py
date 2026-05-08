"""Native connection instructions middleware."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, NotRequired, TypedDict

from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    ContextT,
    ModelRequest,
    ModelResponse,
    PrivateStateAttr,
    ResponseT,
)
from langgraph.runtime import Runtime

from src.ai.middleware._utils import append_system_section
from src.app.services.connections import ConnectionRecord, ConnectionService


def build_native_connections_section(connections: list[ConnectionRecord]) -> str | None:
    if not connections:
        return None
    enabled_connections = [connection for connection in connections if connection.tools_enabled]
    if not enabled_connections:
        return None
    lines = [
        "# Native Connections",
        "",
        "The following first-party Aethos connections are available in the current chat context.",
        "Use these native integration tools when they fit the task. Write actions still require explicit approval.",
    ]
    for connection in enabled_connections:
        capabilities = ", ".join(connection.capabilities) if connection.capabilities else "none"
        lines.append(
            f"- {connection.provider}: {connection.account_label} "
            f"(id: {connection.id}, status: {connection.status}, capabilities: {capabilities})"
        )
    return "\n".join(lines)


class _NativeConnectionState(AgentState):
    _native_connections: NotRequired[Annotated[str | None, PrivateStateAttr]]


class _NativeConnectionStateUpdate(TypedDict):
    _native_connections: str | None


class NativeConnectionsMiddleware(AgentMiddleware[_NativeConnectionState, ContextT]):
    state_schema = _NativeConnectionState

    def __init__(self, *, root_dir: str, owner_user_id: str | None) -> None:
        self.root_dir = str(Path(root_dir).expanduser().resolve())
        self.owner_user_id = owner_user_id

    def _compute(self) -> str | None:
        if not self.owner_user_id:
            return None
        service = ConnectionService(workspace_root=self.root_dir)
        connections = [
            item
            for item in service.list_effective_connections(owner_user_id=self.owner_user_id)
            if item.status == "active"
        ]
        return build_native_connections_section(connections)

    def before_agent(
        self,
        state: _NativeConnectionState,
        runtime: Runtime,
    ) -> _NativeConnectionStateUpdate | None:  # type: ignore[override]
        section = self._compute()
        if state.get("_native_connections") == section:
            return None
        return _NativeConnectionStateUpdate(_native_connections=section)

    async def abefore_agent(
        self,
        state: _NativeConnectionState,
        runtime: Runtime,
    ) -> _NativeConnectionStateUpdate | None:  # type: ignore[override]
        section = self._compute()
        if state.get("_native_connections") == section:
            return None
        return _NativeConnectionStateUpdate(_native_connections=section)

    def modify_request(self, request: ModelRequest[ContextT]) -> ModelRequest[ContextT]:
        section: str | None = request.state.get("_native_connections")
        if not section:
            return request
        return append_system_section(request, section)

    def wrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], ModelResponse[ResponseT]],
    ) -> ModelResponse[ResponseT]:
        return handler(self.modify_request(request))

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        return await handler(self.modify_request(request))


__all__ = ["NativeConnectionsMiddleware", "build_native_connections_section"]
