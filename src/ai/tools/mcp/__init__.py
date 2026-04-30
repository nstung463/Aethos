"""MCP tools and builders."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.config import MCPServerSpec
from src.ai.tools.mcp.auth import build_auth_tools
from src.ai.tools.mcp.client import MCPRuntime
from src.ai.tools.mcp.mcp_tool import build_mcp_tool
from src.ai.tools.mcp.native_tools import build_native_mcp_tools
from src.ai.tools.mcp.resources import (
    build_list_mcp_resources_tool,
    build_read_mcp_resource_tool,
)

if TYPE_CHECKING:
    from src.ai.permissions import PermissionContext


def build_mcp_tools(
    servers: list[MCPServerSpec] | None = None,
    runtime: MCPRuntime | None = None,
    permission_context: PermissionContext | None = None,
) -> list:
    """Build all MCP-related tools for the agent.

    Strategy:
    - First tries to discover native first-class tools (``mcp__{server}__{name}``
      with proper JSON Schema) via :func:`build_native_mcp_tools`.
    - Falls back to the single generic ``mcp(server, tool, arguments)`` wrapper
      only when discovery returns nothing (no servers configured or all servers
      unreachable at startup).
    - Resource and auth tools are always included.
    """
    runtime = runtime or MCPRuntime(servers or [])
    native = build_native_mcp_tools(runtime, permission_context=permission_context)
    invocation_tools = native if native else [build_mcp_tool(runtime)]
    return [
        *invocation_tools,
        build_list_mcp_resources_tool(runtime),
        build_read_mcp_resource_tool(runtime),
        *build_auth_tools(runtime),
    ]


__all__ = [
    "MCPRuntime",
    "build_mcp_tool",
    "build_native_mcp_tools",
    "build_list_mcp_resources_tool",
    "build_read_mcp_resource_tool",
    "build_auth_tools",
    "build_mcp_tools",
]

