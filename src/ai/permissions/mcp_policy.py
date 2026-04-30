"""MCP-specific permission policy.

MCP tool calls are gated by this policy before reaching the evaluator.
Default behaviour is ``PASSTHROUGH`` — the evaluator's rule stack and the
current :class:`~src.ai.permissions.types.PermissionMode` determine the
final decision.  Callers can add explicit ``ALLOW`` rules for trusted tool
patterns (e.g. ``mcp__docs__*``) or ``DENY`` rules to block specific tools.
"""

from __future__ import annotations

from types import MappingProxyType

from src.ai.permissions.types import PermissionBehavior, PermissionDecision


class MCPPolicy:
    """Policy for first-class MCP tool invocations.

    All calls default to ``PASSTHROUGH`` so the
    :class:`~src.ai.permissions.evaluator.PermissionEvaluator` rule stack
    (allow/ask/deny rules keyed on ``PermissionSubject.MCP``) and the active
    :class:`~src.ai.permissions.types.PermissionMode` make the final call.
    """

    def check(self, *, tool_name: str) -> PermissionDecision:
        """Return the base policy decision for *tool_name*."""
        return PermissionDecision(
            behavior=PermissionBehavior.PASSTHROUGH,
            reason="MCP tool invocation — subject to permission rules",
            metadata=MappingProxyType({"tool": tool_name}),
        )
