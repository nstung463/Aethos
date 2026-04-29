"""Tests for MemoryMiddleware."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import SystemMessage

from src.ai.middleware.memory import MEMORY_TEMPLATE, MemoryMiddleware


@dataclass
class _FakeModelRequest:
    state: dict[str, Any]
    system_message: Any = None

    def override(self, **kwargs: Any) -> _FakeModelRequest:
        return _FakeModelRequest(
            state=self.state,
            system_message=kwargs.get("system_message", self.system_message),
        )


class _FakeRuntime:
    pass


class TestMemoryMiddleware:
    def test_loads_agents_md_when_exists(self, tmp_path: Path):
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("You are a helpful coding assistant.")
        mw = MemoryMiddleware(agents_md_path=str(agents_md))
        update = mw.before_agent(state={}, runtime=_FakeRuntime())
        assert update is not None
        assert update["memory_contents"] == "You are a helpful coding assistant."

    def test_returns_none_content_when_agents_md_missing(self, tmp_path: Path):
        mw = MemoryMiddleware(agents_md_path=str(tmp_path / "AGENTS.md"))
        update = mw.before_agent(state={}, runtime=_FakeRuntime())
        assert update is not None
        assert update["memory_contents"] is None

    def test_returns_none_content_when_agents_md_empty(self, tmp_path: Path):
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("   \n   ")
        mw = MemoryMiddleware(agents_md_path=str(agents_md))
        update = mw.before_agent(state={}, runtime=_FakeRuntime())
        assert update["memory_contents"] is None

    def test_before_agent_returns_none_when_already_cached(self, tmp_path: Path):
        mw = MemoryMiddleware(agents_md_path=str(tmp_path / "AGENTS.md"))
        update = mw.before_agent(state={"memory_contents": "cached"}, runtime=_FakeRuntime())
        assert update is None

    @pytest.mark.asyncio
    async def test_abefore_agent_caches_correctly(self, tmp_path: Path):
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("Memory content.")
        mw = MemoryMiddleware(agents_md_path=str(agents_md))
        update = await mw.abefore_agent(state={}, runtime=_FakeRuntime())
        assert update is not None

        update2 = await mw.abefore_agent(
            state={"memory_contents": update["memory_contents"]},
            runtime=_FakeRuntime(),
        )
        assert update2 is None

    def test_modify_request_injects_memory_template(self, tmp_path: Path):
        mw = MemoryMiddleware(agents_md_path=str(tmp_path / "AGENTS.md"))
        content = "Always use pytest."
        req = _FakeModelRequest(
            state={"memory_contents": content},
            system_message=SystemMessage(content="Base."),
        )
        result = mw.modify_request(req)
        sys_text = result.system_message.content
        assert "Always use pytest." in sys_text
        assert "agent_memory" in sys_text  # MEMORY_TEMPLATE uses <agent_memory> tag

    def test_modify_request_skips_when_no_content(self, tmp_path: Path):
        mw = MemoryMiddleware(agents_md_path=str(tmp_path / "AGENTS.md"))
        req = _FakeModelRequest(
            state={"memory_contents": None},
            system_message=SystemMessage(content="Unchanged."),
        )
        result = mw.modify_request(req)
        assert result.system_message.content == "Unchanged."

    def test_memory_template_contains_guidelines(self):
        assert "memory_guidelines" in MEMORY_TEMPLATE
        assert "AGENTS.md" in MEMORY_TEMPLATE

    def test_modify_request_creates_system_message_when_none(self, tmp_path: Path):
        mw = MemoryMiddleware(agents_md_path=str(tmp_path / "AGENTS.md"))
        req = _FakeModelRequest(state={"memory_contents": "Some memory."}, system_message=None)
        result = mw.modify_request(req)
        assert result.system_message is not None
        assert "Some memory." in result.system_message.content
