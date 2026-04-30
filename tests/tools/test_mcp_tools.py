from __future__ import annotations

import json
import sys
import types

import pytest
from pydantic import BaseModel

from src.config import get_mcp_servers
from src.ai.tools.mcp import MCPRuntime, build_mcp_tools
from src.ai.tools.mcp.mcp_tool import build_mcp_tool


class _FakeArgs(BaseModel):
    x: int = 0


class _FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name
        self.description = f"Fake tool {name}"
        self.args_schema = _FakeArgs

    async def ainvoke(self, payload: dict) -> dict:
        return {"echo": payload}


class _FakeSession:
    def __init__(self, server: str) -> None:
        self.server = server

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def list_resources(self):
        return types.SimpleNamespace(
            resources=[types.SimpleNamespace(uri=f"mcp://{self.server}/one", name="One")]
        )

    async def read_resource(self, uri: str):
        return types.SimpleNamespace(contents=[{"uri": uri, "text": "hello"}])

    async def list_prompts(self):
        return types.SimpleNamespace(
            prompts=[types.SimpleNamespace(name="summarize", description="Summarize docs")]
        )

    async def get_prompt(self, name: str, arguments: dict):
        return types.SimpleNamespace(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Prompt {name}"},
                        {"type": "text", "text": f"with {arguments.get('arguments', '')}"},
                    ],
                }
            ]
        )


class _FakeMultiServerMCPClient:
    def __init__(self, config: dict[str, dict]) -> None:
        self.config = config

    async def get_tools(self, *, server_name: str | None = None):
        assert server_name is not None
        return [_FakeTool("ping")]

    def session(self, server: str) -> _FakeSession:
        return _FakeSession(server)


def _install_fake_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    client_module = types.ModuleType("langchain_mcp_adapters.client")
    client_module.MultiServerMCPClient = _FakeMultiServerMCPClient
    package = types.ModuleType("langchain_mcp_adapters")

    monkeypatch.setitem(sys.modules, "langchain_mcp_adapters", package)
    monkeypatch.setitem(sys.modules, "langchain_mcp_adapters.client", client_module)


# ---------------------------------------------------------------------------
# Config parsing tests
# ---------------------------------------------------------------------------

def test_get_mcp_servers_accepts_object_map(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "ETHOS_MCP_SERVERS",
        json.dumps(
            {
                "docs": {
                    "transport": "streamable_http",
                    "url": "https://example.com/mcp",
                    "auth_url": "https://example.com/login",
                }
            }
        ),
    )

    servers = get_mcp_servers()

    assert len(servers) == 1
    assert servers[0].name == "docs"
    assert servers[0].auth_url == "https://example.com/login"
    assert servers[0].connection["transport"] == "streamable_http"


def test_get_mcp_servers_accepts_stdio_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "ETHOS_MCP_SERVERS",
        json.dumps(
            {
                "math": {
                    "transport": "stdio",
                    "command": "python",
                    "args": ["/srv/math.py"],
                }
            }
        ),
    )

    servers = get_mcp_servers()

    assert len(servers) == 1
    assert servers[0].name == "math"
    assert servers[0].connection["transport"] == "stdio"
    assert servers[0].connection["command"] == "python"


def test_get_mcp_servers_accepts_websocket_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "ETHOS_MCP_SERVERS",
        json.dumps({"rt": {"transport": "websocket", "url": "ws://localhost:9000/ws"}}),
    )

    servers = get_mcp_servers()

    assert servers[0].connection["transport"] == "websocket"


def test_get_mcp_servers_rejects_unknown_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "ETHOS_MCP_SERVERS",
        json.dumps({"bad": {"transport": "ftp", "url": "ftp://example.com"}}),
    )

    with pytest.raises(ValueError, match="unsupported transport"):
        get_mcp_servers()


# ---------------------------------------------------------------------------
# build_mcp_tools — native tool path
# ---------------------------------------------------------------------------

def test_build_mcp_tools_returns_native_tools_when_discovery_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When MCP discovery works, first-class mcp__{server}__{tool} tools are returned."""
    _install_fake_mcp(monkeypatch)
    monkeypatch.setenv(
        "ETHOS_MCP_SERVERS",
        json.dumps(
            {
                "docs": {
                    "transport": "streamable_http",
                    "url": "https://example.com/mcp",
                    "auth_url": "https://example.com/login",
                }
            }
        ),
    )

    tools = build_mcp_tools(get_mcp_servers())
    names = [tool.name for tool in tools]

    # First-class native tool for the fake "ping" tool
    assert "mcp__docs__ping" in names
    # Generic fallback should NOT be present when native tools are found
    assert "mcp" not in names
    # Resource and auth tools are always present
    assert "list_mcp_resources" in names
    assert "read_mcp_resource" in names
    assert "mcp__docs__authenticate" in names


def test_build_mcp_tools_falls_back_to_generic_when_no_servers() -> None:
    """With no MCP servers, the generic mcp fallback tool is included."""
    tools = build_mcp_tools([])
    names = [tool.name for tool in tools]

    assert "mcp" in names
    assert "list_mcp_resources" in names
    assert "read_mcp_resource" in names


def test_native_mcp_tool_invokes_via_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """The native mcp__docs__ping tool calls runtime.invoke_tool under the hood."""
    _install_fake_mcp(monkeypatch)
    monkeypatch.setenv(
        "ETHOS_MCP_SERVERS",
        json.dumps({"docs": {"transport": "streamable_http", "url": "https://example.com/mcp"}}),
    )
    tools = {tool.name: tool for tool in build_mcp_tools(get_mcp_servers())}

    result = json.loads(tools["mcp__docs__ping"].invoke({"x": 1}))

    assert result["server"] == "docs"
    assert result["tool"] == "ping"
    assert result["result"]["echo"] == {"x": 1}


def test_generic_mcp_tool_still_works_as_explicit_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """The generic mcp tool can still be used directly via build_mcp_tool."""
    _install_fake_mcp(monkeypatch)
    monkeypatch.setenv(
        "ETHOS_MCP_SERVERS",
        json.dumps({"docs": {"transport": "streamable_http", "url": "https://example.com/mcp"}}),
    )
    runtime = MCPRuntime(get_mcp_servers())
    generic_tool = build_mcp_tool(runtime)

    result = json.loads(generic_tool.invoke({"server": "docs", "tool": "ping", "arguments": {"x": 1}}))

    assert result["server"] == "docs"
    assert result["tool"] == "ping"
    assert result["result"]["echo"] == {"x": 1}


# ---------------------------------------------------------------------------
# Resource tools
# ---------------------------------------------------------------------------

def test_list_and_read_mcp_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_mcp(monkeypatch)
    monkeypatch.setenv(
        "ETHOS_MCP_SERVERS",
        json.dumps(
            [
                {
                    "name": "docs",
                    "transport": "streamable_http",
                    "url": "https://example.com/mcp",
                }
            ]
        ),
    )
    tools = {tool.name: tool for tool in build_mcp_tools(get_mcp_servers())}

    listed = json.loads(tools["list_mcp_resources"].invoke({"server": "docs"}))
    read = json.loads(
        tools["read_mcp_resource"].invoke({"server": "docs", "uri": "mcp://docs/one"})
    )

    assert listed["resources"][0]["server"] == "docs"
    assert listed["resources"][0]["uri"] == "mcp://docs/one"
    assert read["contents"][0]["text"] == "hello"


# ---------------------------------------------------------------------------
# Prompt tools
# ---------------------------------------------------------------------------

def test_mcp_runtime_lists_and_gets_prompts(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_mcp(monkeypatch)
    monkeypatch.setenv(
        "ETHOS_MCP_SERVERS",
        json.dumps(
            [
                {
                    "name": "docs",
                    "transport": "streamable_http",
                    "url": "https://example.com/mcp",
                }
            ]
        ),
    )
    runtime = MCPRuntime(get_mcp_servers())

    listed = json.loads(runtime.list_prompts())
    prompt = runtime.get_prompt("docs", "summarize", {"arguments": "topic"})

    assert listed["prompts"][0]["server"] == "docs"
    assert listed["prompts"][0]["name"] == "summarize"
    assert prompt == "Prompt summarize\nwith topic"
