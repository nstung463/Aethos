"""First-class MCP tool builders.

Instead of the single generic ``mcp(server, tool, arguments)`` wrapper, this
module creates one :class:`~langchain_core.tools.StructuredTool` per remote
MCP tool, preserving the tool's original JSON Schema so the LLM receives
accurate argument types and required-field information.

Naming convention mirrors Claude Code: ``mcp__{server}__{tool_name}``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from src.logger import get_logger

if TYPE_CHECKING:
    from src.ai.permissions.types import PermissionContext
    from src.ai.tools.mcp.client import MCPRuntime

_logger = get_logger(__name__)

# Module-level singletons — both classes are stateless so one instance is enough.
_MCP_POLICY: Any = None
_MCP_EVALUATOR: Any = None


def _get_policy() -> Any:
    global _MCP_POLICY
    if _MCP_POLICY is None:
        from src.ai.permissions.mcp_policy import MCPPolicy
        _MCP_POLICY = MCPPolicy()
    return _MCP_POLICY


def _get_evaluator() -> Any:
    global _MCP_EVALUATOR
    if _MCP_EVALUATOR is None:
        from src.ai.permissions import PermissionEvaluator
        _MCP_EVALUATOR = PermissionEvaluator()
    return _MCP_EVALUATOR


class _AnyArgs(BaseModel):
    """Permissive fallback schema used when a discovered tool has no schema."""

    model_config = {"extra": "allow"}


def _canonical_name(server: str, raw_name: str) -> str:
    """Return ``mcp__{server}__{tool}`` stripping any existing server prefix."""
    clean = raw_name.removeprefix(f"{server}__")
    return f"mcp__{server}__{clean}"


def _make_native_tool(
    runtime: MCPRuntime,
    server: str,
    native_tool: Any,
    permission_context: PermissionContext | None = None,
) -> StructuredTool:
    """Wrap one discovered MCP tool into a first-class StructuredTool."""
    raw_name: str = getattr(native_tool, "name", "")
    tool_name = _canonical_name(server, raw_name)
    clean_name = tool_name.removeprefix(f"mcp__{server}__")
    description: str = getattr(native_tool, "description", "") or f"MCP tool {clean_name} from server {server}"
    args_schema = getattr(native_tool, "args_schema", None)

    # Capture all required context as closure variables — no default args so
    # StructuredTool does not infer confusing schema fields from the signature.
    _rt = runtime
    _s = server
    _n = clean_name
    _tname = tool_name
    _pctx = permission_context

    def _run(**kwargs: Any) -> str:
        if _pctx is not None:
            from src.ai.permissions.types import PermissionBehavior, PermissionSubject

            decision = _get_evaluator().evaluate(
                context=_pctx,
                subject=PermissionSubject.MCP,
                candidate=_tname,
                policy_decision=_get_policy().check(tool_name=_tname),
            )
            if decision.behavior is PermissionBehavior.DENY:
                return json.dumps({"error": f"MCP tool {_tname} is denied by policy", "tool": _tname})
            if decision.behavior is PermissionBehavior.ASK:
                # In headless / automated contexts the agent cannot prompt the user.
                # Return a structured "pending approval" payload that the caller can
                # surface in the UI as a permission request rather than silently
                # executing or silently blocking.
                return json.dumps({
                    "status": "approval_required",
                    "tool": _tname,
                    "reason": decision.reason,
                })

        return _rt.invoke_tool(server=_s, tool=_n, arguments=kwargs or None)

    return StructuredTool(
        name=tool_name,
        description=description,
        func=_run,
        args_schema=args_schema if args_schema is not None else _AnyArgs,
    )


def build_native_mcp_tools(
    runtime: MCPRuntime,
    permission_context: PermissionContext | None = None,
) -> list[StructuredTool]:
    """Discover all MCP tools and return them as first-class StructuredTools.

    Returns an empty list when no servers are configured or when every server
    fails to connect — the caller falls back to the generic ``mcp`` tool in
    that case.
    """
    pairs = runtime.discover_tools()
    tools: list[StructuredTool] = []
    for server, native_tool in pairs:
        try:
            tools.append(_make_native_tool(runtime, server, native_tool, permission_context))
        except Exception as exc:
            _logger.warning(
                "Failed to wrap MCP tool %r from %r: %s",
                getattr(native_tool, "name", "?"),
                server,
                exc,
            )
    return tools
