"""Tests for first-class MCP native tool building."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest
from pydantic import BaseModel

from src.config import MCPServerSpec
from src.ai.tools.mcp.client import MCPRuntime
from src.ai.tools.mcp.native_tools import _canonical_name, _make_native_tool, build_native_mcp_tools
from src.ai.permissions import (
    PermissionBehavior,
    PermissionContext,
    PermissionMode,
    PermissionRule,
    PermissionSource,
    PermissionSubject,
    build_default_permission_context,
)


class _PingArgs(BaseModel):
    query: str = ""


class _FakeTool:
    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description or f"Fake {name}"
        self.args_schema = _PingArgs

    async def ainvoke(self, payload: dict) -> dict:
        return {"echoed": payload}


class _FakeMultiServerMCPClient:
    call_count = 0

    def __init__(self, config: dict) -> None:
        self.config = config
        self._tools: list[_FakeTool] = [_FakeTool("ping"), _FakeTool("search")]

    async def get_tools(self, *, server_name: str | None = None) -> list[_FakeTool]:
        type(self).call_count += 1
        return list(self._tools)


@pytest.fixture(autouse=True)
def _reset_mcp_discovery_cache() -> None:
    MCPRuntime.clear_discovery_cache()
    _FakeMultiServerMCPClient.call_count = 0
    yield
    MCPRuntime.clear_discovery_cache()

    def session(self, server: str):
        raise NotImplementedError


class _FailingMultiServerMCPClient:
    def __init__(self, config: dict) -> None: ...
    async def get_tools(self, *, server_name: str | None = None):
        raise ConnectionError("server offline")


def _install_fake_mcp(monkeypatch: pytest.MonkeyPatch, client_cls=_FakeMultiServerMCPClient) -> None:
    mod = types.ModuleType("langchain_mcp_adapters.client")
    mod.MultiServerMCPClient = client_cls
    pkg = types.ModuleType("langchain_mcp_adapters")
    monkeypatch.setitem(sys.modules, "langchain_mcp_adapters", pkg)
    monkeypatch.setitem(sys.modules, "langchain_mcp_adapters.client", mod)


def _make_spec(name: str = "docs") -> MCPServerSpec:
    return MCPServerSpec(name=name, connection={"transport": "http", "url": "https://example.com/mcp"})


def _make_runtime(names: list[str] = None) -> MCPRuntime:
    specs = [_make_spec(n) for n in (names or ["docs"])]
    return MCPRuntime(specs)


# ---------------------------------------------------------------------------
# _canonical_name
# ---------------------------------------------------------------------------

def test_canonical_name_basic() -> None:
    assert _canonical_name("docs", "search") == "mcp__docs__search"


def test_canonical_name_strips_server_prefix() -> None:
    # langchain-mcp-adapters may already prefix the tool with the server name
    assert _canonical_name("docs", "docs__search") == "mcp__docs__search"


def test_canonical_name_leaves_double_prefix_alone() -> None:
    # If the tool is already "mcp__docs__search", it should not double-prefix
    assert _canonical_name("docs", "search") == "mcp__docs__search"


# ---------------------------------------------------------------------------
# _make_native_tool
# ---------------------------------------------------------------------------

def test_make_native_tool_name_and_description(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_mcp(monkeypatch)
    runtime = _make_runtime()
    fake = _FakeTool("ping", "Ping the server")

    tool = _make_native_tool(runtime, "docs", fake)

    assert tool.name == "mcp__docs__ping"
    assert "Ping the server" in tool.description


def test_make_native_tool_uses_args_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_mcp(monkeypatch)
    runtime = _make_runtime()
    fake = _FakeTool("ping")

    tool = _make_native_tool(runtime, "docs", fake)

    assert tool.args_schema is _PingArgs


def test_make_native_tool_fallback_description(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_mcp(monkeypatch)
    runtime = _make_runtime()

    class _NoDesc:
        name = "query"
        description = ""
        args_schema = None

    tool = _make_native_tool(runtime, "docs", _NoDesc())

    assert "docs" in tool.description
    assert "query" in tool.description


# ---------------------------------------------------------------------------
# build_native_mcp_tools — discovery
# ---------------------------------------------------------------------------

def test_build_native_tools_returns_one_per_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_mcp(monkeypatch)
    runtime = _make_runtime()

    tools = build_native_mcp_tools(runtime)

    names = [t.name for t in tools]
    assert "mcp__docs__ping" in names
    assert "mcp__docs__search" in names
    assert len(tools) == 2


def test_build_native_tools_multi_server(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_mcp(monkeypatch)
    runtime = _make_runtime(["alpha", "beta"])

    tools = build_native_mcp_tools(runtime)

    names = [t.name for t in tools]
    # 2 tools per server × 2 servers
    assert len(tools) == 4
    assert "mcp__alpha__ping" in names
    assert "mcp__beta__ping" in names


def test_build_native_tools_discovery_cache_reuses_previous_result(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_mcp(monkeypatch)
    _FakeMultiServerMCPClient.call_count = 0
    runtime = _make_runtime(["docs"])

    first = build_native_mcp_tools(runtime)
    second = build_native_mcp_tools(runtime)

    assert len(first) == len(second) == 2
    assert _FakeMultiServerMCPClient.call_count == 1


def test_build_native_tools_empty_when_no_servers() -> None:
    runtime = MCPRuntime([])
    assert build_native_mcp_tools(runtime) == []


def test_build_native_tools_skips_failing_servers(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_mcp(monkeypatch, client_cls=_FailingMultiServerMCPClient)
    runtime = _make_runtime()

    # Should not raise — returns empty, logs a warning
    tools = build_native_mcp_tools(runtime)

    assert tools == []


# ---------------------------------------------------------------------------
# Native tool invocation
# ---------------------------------------------------------------------------

def test_native_tool_invoke_calls_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_mcp(monkeypatch)
    runtime = _make_runtime()

    tools = {t.name: t for t in build_native_mcp_tools(runtime)}
    result = json.loads(tools["mcp__docs__ping"].invoke({"query": "hello"}))

    assert result["server"] == "docs"
    assert result["tool"] == "ping"
    assert result["result"]["echoed"] == {"query": "hello"}


def test_native_tool_with_no_args(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_mcp(monkeypatch)
    runtime = _make_runtime()

    tools = {t.name: t for t in build_native_mcp_tools(runtime)}
    # invoke with empty dict — query defaults to ""
    result = json.loads(tools["mcp__docs__ping"].invoke({}))

    assert result["server"] == "docs"


# ---------------------------------------------------------------------------
# Permission checks
# ---------------------------------------------------------------------------

def _make_permission_context(
    *,
    mode: PermissionMode = PermissionMode.DEFAULT,
    rules: tuple = (),
) -> PermissionContext:
    return build_default_permission_context(
        Path("."),
        mode=mode,
        rules=tuple(rules),
    )


def test_native_tool_denied_by_permission_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_mcp(monkeypatch)
    runtime = _make_runtime()
    deny_rule = PermissionRule(
        subject=PermissionSubject.MCP,
        behavior=PermissionBehavior.DENY,
        source=PermissionSource.SESSION,
        matcher="mcp__docs__ping",
    )
    ctx = _make_permission_context(rules=(deny_rule,))

    tools = {t.name: t for t in build_native_mcp_tools(runtime, permission_context=ctx)}
    result = json.loads(tools["mcp__docs__ping"].invoke({}))

    assert "error" in result
    assert "denied" in result["error"].lower()


def test_native_tool_allow_rule_passes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_mcp(monkeypatch)
    runtime = _make_runtime()
    allow_rule = PermissionRule(
        subject=PermissionSubject.MCP,
        behavior=PermissionBehavior.ALLOW,
        source=PermissionSource.SESSION,
        matcher="mcp__docs__ping",
    )
    ctx = _make_permission_context(rules=(allow_rule,))

    tools = {t.name: t for t in build_native_mcp_tools(runtime, permission_context=ctx)}
    result = json.loads(tools["mcp__docs__ping"].invoke({"query": "hi"}))

    assert result["server"] == "docs"
    assert result["result"]["echoed"] == {"query": "hi"}


def test_native_tool_bypass_permissions_allows_all(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_mcp(monkeypatch)
    runtime = _make_runtime()
    ctx = _make_permission_context(mode=PermissionMode.BYPASS_PERMISSIONS)

    tools = {t.name: t for t in build_native_mcp_tools(runtime, permission_context=ctx)}
    result = json.loads(tools["mcp__docs__ping"].invoke({}))

    assert result["server"] == "docs"


def test_native_tool_ask_returns_approval_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """DEFAULT mode + no rules → evaluator says ASK → tool returns approval_required payload."""
    _install_fake_mcp(monkeypatch)
    runtime = _make_runtime()
    # No rules, DEFAULT mode → evaluator converts PASSTHROUGH → ASK
    ctx = _make_permission_context(mode=PermissionMode.DEFAULT, rules=())

    tools = {t.name: t for t in build_native_mcp_tools(runtime, permission_context=ctx)}
    result = json.loads(tools["mcp__docs__ping"].invoke({}))

    assert result["status"] == "approval_required"
    assert result["tool"] == "mcp__docs__ping"
    assert "reason" in result
