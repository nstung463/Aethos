"""Tests for MCP permission policy and evaluator integration."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.ai.permissions import (
    PermissionBehavior,
    PermissionEvaluator,
    PermissionMode,
    PermissionRule,
    PermissionSource,
    PermissionSubject,
    MCPPolicy,
    build_default_permission_context,
)
from src.ai.permissions.types import PermissionDecision


def _ctx(mode=PermissionMode.DEFAULT, rules=()):
    return build_default_permission_context(
        Path("."),
        mode=mode,
        rules=tuple(rules),
    )


evaluator = PermissionEvaluator()
policy = MCPPolicy()


# ---------------------------------------------------------------------------
# MCPPolicy
# ---------------------------------------------------------------------------

def test_mcp_policy_returns_passthrough() -> None:
    decision = policy.check(tool_name="mcp__docs__search")

    assert decision.behavior is PermissionBehavior.PASSTHROUGH
    assert decision.metadata["tool"] == "mcp__docs__search"


def test_mcp_policy_always_passthrough_regardless_of_name() -> None:
    for name in ("mcp__gmail__send_email", "mcp__docs__read", "mcp__custom__tool"):
        decision = policy.check(tool_name=name)
        assert decision.behavior is PermissionBehavior.PASSTHROUGH


# ---------------------------------------------------------------------------
# Evaluator with MCP subject
# ---------------------------------------------------------------------------

def test_evaluator_mcp_defaults_to_ask_in_default_mode() -> None:
    """No rules + DEFAULT mode → PASSTHROUGH becomes ASK."""
    ctx = _ctx()
    decision = evaluator.evaluate(
        context=ctx,
        subject=PermissionSubject.MCP,
        candidate="mcp__docs__search",
        policy_decision=policy.check(tool_name="mcp__docs__search"),
    )
    assert decision.behavior is PermissionBehavior.ASK


def test_evaluator_mcp_allow_rule_grants_access() -> None:
    rule = PermissionRule(
        subject=PermissionSubject.MCP,
        behavior=PermissionBehavior.ALLOW,
        source=PermissionSource.SESSION,
        matcher="mcp__docs__search",
    )
    ctx = _ctx(rules=(rule,))

    decision = evaluator.evaluate(
        context=ctx,
        subject=PermissionSubject.MCP,
        candidate="mcp__docs__search",
        policy_decision=policy.check(tool_name="mcp__docs__search"),
    )

    assert decision.behavior is PermissionBehavior.ALLOW


def test_evaluator_mcp_deny_rule_blocks_access() -> None:
    rule = PermissionRule(
        subject=PermissionSubject.MCP,
        behavior=PermissionBehavior.DENY,
        source=PermissionSource.SESSION,
        matcher="mcp__docs__delete",
    )
    ctx = _ctx(rules=(rule,))

    decision = evaluator.evaluate(
        context=ctx,
        subject=PermissionSubject.MCP,
        candidate="mcp__docs__delete",
        policy_decision=policy.check(tool_name="mcp__docs__delete"),
    )

    assert decision.behavior is PermissionBehavior.DENY


def test_evaluator_mcp_deny_rule_does_not_affect_other_tools() -> None:
    rule = PermissionRule(
        subject=PermissionSubject.MCP,
        behavior=PermissionBehavior.DENY,
        source=PermissionSource.SESSION,
        matcher="mcp__docs__delete",
    )
    ctx = _ctx(rules=(rule,))

    decision = evaluator.evaluate(
        context=ctx,
        subject=PermissionSubject.MCP,
        candidate="mcp__docs__search",  # different tool
        policy_decision=policy.check(tool_name="mcp__docs__search"),
    )

    # No deny rule matches → PASSTHROUGH → ASK (default mode)
    assert decision.behavior is PermissionBehavior.ASK


def test_evaluator_mcp_bypass_permissions_allows_everything() -> None:
    ctx = _ctx(mode=PermissionMode.BYPASS_PERMISSIONS)

    decision = evaluator.evaluate(
        context=ctx,
        subject=PermissionSubject.MCP,
        candidate="mcp__gmail__send_email",
        policy_decision=policy.check(tool_name="mcp__gmail__send_email"),
    )

    assert decision.behavior is PermissionBehavior.ALLOW


def test_evaluator_mcp_tool_wide_deny_overrides_allow_rule() -> None:
    """A tool-wide DENY (matcher=None) overrides any more specific rule."""
    deny_all = PermissionRule(
        subject=PermissionSubject.MCP,
        behavior=PermissionBehavior.DENY,
        source=PermissionSource.SESSION,
        matcher=None,
    )
    allow_specific = PermissionRule(
        subject=PermissionSubject.MCP,
        behavior=PermissionBehavior.ALLOW,
        source=PermissionSource.SESSION,
        matcher="mcp__docs__search",
    )
    ctx = _ctx(rules=(deny_all, allow_specific))

    decision = evaluator.evaluate(
        context=ctx,
        subject=PermissionSubject.MCP,
        candidate="mcp__docs__search",
        policy_decision=policy.check(tool_name="mcp__docs__search"),
    )

    assert decision.behavior is PermissionBehavior.DENY


def test_evaluator_mcp_dont_ask_mode_converts_ask_to_deny() -> None:
    ctx = _ctx(mode=PermissionMode.DONT_ASK)

    decision = evaluator.evaluate(
        context=ctx,
        subject=PermissionSubject.MCP,
        candidate="mcp__docs__search",
        policy_decision=policy.check(tool_name="mcp__docs__search"),
    )

    assert decision.behavior is PermissionBehavior.DENY
