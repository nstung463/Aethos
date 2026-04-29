"""MCP Instructions middleware — injects per-server instructions into the system prompt once per session."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Annotated, NotRequired, TypedDict

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

from src.ai.middleware._utils import append_to_system_message

if TYPE_CHECKING:
    from src.config import MCPServerSpec

logger = logging.getLogger(__name__)


def build_mcp_instructions_section(servers: list[MCPServerSpec]) -> str | None:
    """Build the # MCP Server Instructions block from servers that have instructions set."""
    servers_with_instructions = [s for s in servers if s.instructions]
    if not servers_with_instructions:
        return None
    parts = ["# MCP Server Instructions\n"]
    for s in servers_with_instructions:
        parts.append(f"## {s.name}\n{s.instructions}")
    return "\n\n".join(parts)


class _McpState(AgentState):
    """Extends AgentState with a cached MCP instructions section."""

    _mcp_instructions: NotRequired[Annotated[str | None, PrivateStateAttr]]


class _McpStateUpdate(TypedDict):
    _mcp_instructions: str | None


class MCPInstructionsMiddleware(AgentMiddleware[_McpState, ContextT]):
    """Injects per-server MCP instructions into the system prompt once per session.

    Servers that have no `instructions` field set are silently skipped.
    The section is computed once on the first agent turn and cached via
    PrivateStateAttr for the lifetime of the thread — identical to the
    MemoryMiddleware and SkillsMiddleware caching pattern.
    """

    state_schema = _McpState

    def __init__(self, servers: list[MCPServerSpec]) -> None:
        self.servers = servers

    def before_agent(self, state: _McpState, runtime: Runtime) -> _McpStateUpdate | None:  # type: ignore[override]
        if "_mcp_instructions" in state:
            return None
        section = build_mcp_instructions_section(self.servers)
        logger.debug(
            "MCPInstructionsMiddleware: %s",
            f"injected {len(section)} chars" if section else "no instructions to inject",
        )
        return _McpStateUpdate(_mcp_instructions=section)

    async def abefore_agent(self, state: _McpState, runtime: Runtime) -> _McpStateUpdate | None:  # type: ignore[override]
        if "_mcp_instructions" in state:
            return None
        section = build_mcp_instructions_section(self.servers)
        return _McpStateUpdate(_mcp_instructions=section)

    def modify_request(self, request: ModelRequest[ContextT]) -> ModelRequest[ContextT]:
        section: str | None = request.state.get("_mcp_instructions")
        if not section:
            return request
        new_sys = append_to_system_message(request.system_message, section)
        return request.override(system_message=new_sys)

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
