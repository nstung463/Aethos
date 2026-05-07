"""Tests for MCPInstructionsMiddleware and build_mcp_instructions_section()."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from src.ai.middleware.mcp_instructions import (
    MCPInstructionsMiddleware,
    build_mcp_instructions_section,
)
from src.config import MCPServerSpec


def _server(name: str, instructions: str | None = None) -> MCPServerSpec:
    return MCPServerSpec(
        name=name,
        connection={"transport": "streamable_http", "url": "http://fake"},
        instructions=instructions,
    )


@dataclass
class _FakeModelRequest:
    state: dict[str, Any]
    system_prompt: str | None = None

    def override(self, **kwargs: Any) -> _FakeModelRequest:
        return _FakeModelRequest(
            state=self.state,
            system_prompt=kwargs.get("system_prompt", self.system_prompt),
        )


class _FakeRuntime:
    pass


# ---------------------------------------------------------------------------
# Tests: build_mcp_instructions_section()
# ---------------------------------------------------------------------------

class TestBuildMcpInstructionsSection:
    def test_returns_none_when_no_servers(self):
        assert build_mcp_instructions_section([]) is None

    def test_returns_none_when_all_servers_lack_instructions(self):
        servers = [_server("docs"), _server("api")]
        assert build_mcp_instructions_section(servers) is None

    def test_builds_section_from_servers_with_instructions(self):
        servers = [
            _server("docs", "Use this server to look up API docs."),
            _server("api", "Use this server to make API calls."),
        ]
        result = build_mcp_instructions_section(servers)
        assert result is not None
        assert (
            "The following MCP servers have provided instructions for how to use their tools and resources:"
            in result
        )
        assert "## docs" in result
        assert "Use this server to look up API docs." in result
        assert "## api" in result
        assert "Use this server to make API calls." in result

    def test_skips_servers_without_instructions(self):
        servers = [
            _server("docs", "Docs instructions."),
            _server("no-instructions"),
        ]
        result = build_mcp_instructions_section(servers)
        assert result is not None
        assert "## docs" in result
        assert "## no-instructions" not in result

    def test_section_has_top_level_heading(self):
        servers = [_server("docs", "Something.")]
        result = build_mcp_instructions_section(servers)
        assert "# MCP Server Instructions" in result


# ---------------------------------------------------------------------------
# Tests: MCPInstructionsMiddleware
# ---------------------------------------------------------------------------

class TestMCPInstructionsMiddleware:
    def test_before_agent_returns_state_update_first_call(self):
        mw = MCPInstructionsMiddleware(servers=[_server("docs", "Read docs here.")])
        update = mw.before_agent(state={}, runtime=_FakeRuntime())
        assert update is not None
        assert "_mcp_instructions" in update

    def test_before_agent_sets_none_when_no_instructions(self):
        mw = MCPInstructionsMiddleware(servers=[_server("noinstr")])
        update = mw.before_agent(state={}, runtime=_FakeRuntime())
        assert update is not None
        assert update["_mcp_instructions"] is None

    def test_before_agent_returns_none_when_cached(self):
        mw = MCPInstructionsMiddleware(servers=[_server("docs", "Instructions.")])
        section = build_mcp_instructions_section(mw.servers)
        update = mw.before_agent(state={"_mcp_instructions": section}, runtime=_FakeRuntime())
        assert update is None

    def test_before_agent_updates_when_instructions_change(self):
        mw = MCPInstructionsMiddleware(servers=[_server("docs", "Instructions.")])
        update = mw.before_agent(state={"_mcp_instructions": "stale"}, runtime=_FakeRuntime())
        assert update is not None
        assert update["_mcp_instructions"] != "stale"

    def test_before_agent_handles_empty_server_list(self):
        mw = MCPInstructionsMiddleware(servers=[])
        update = mw.before_agent(state={}, runtime=_FakeRuntime())
        assert update["_mcp_instructions"] is None

    def test_abefore_agent_caches_correctly(self):
        mw = MCPInstructionsMiddleware(servers=[_server("docs", "Async docs.")])
        update = asyncio.run(mw.abefore_agent(state={}, runtime=_FakeRuntime()))
        assert update is not None

        update2 = asyncio.run(
            mw.abefore_agent(
                state={"_mcp_instructions": update["_mcp_instructions"]},
                runtime=_FakeRuntime(),
            )
        )
        assert update2 is None

    def test_modify_request_injects_section(self):
        mw = MCPInstructionsMiddleware(servers=[_server("docs", "Doc instructions.")])
        section = build_mcp_instructions_section(mw.servers)
        req = _FakeModelRequest(
            state={"_mcp_instructions": section},
            system_prompt="Base prompt.",
        )
        result = mw.modify_request(req)
        text = result.system_prompt
        assert "Base prompt." in text
        assert "Doc instructions." in text

    def test_modify_request_skips_when_section_is_none(self):
        mw = MCPInstructionsMiddleware(servers=[])
        req = _FakeModelRequest(
            state={"_mcp_instructions": None},
            system_prompt="Untouched.",
        )
        result = mw.modify_request(req)
        assert result.system_prompt == "Untouched."

    def test_modify_request_creates_system_message_when_none(self):
        mw = MCPInstructionsMiddleware(servers=[_server("docs", "Info.")])
        section = build_mcp_instructions_section(mw.servers)
        req = _FakeModelRequest(state={"_mcp_instructions": section}, system_prompt=None)
        result = mw.modify_request(req)
        assert result.system_prompt is not None
        assert "Info." in result.system_prompt
