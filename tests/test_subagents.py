from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.ai.agents.subagents import build_task_tool


class _FakeRunnable:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.last_state: dict[str, Any] | None = None
        self.async_last_state: dict[str, Any] | None = None

    def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        self.last_state = state
        return self.response

    async def ainvoke(self, state: dict[str, Any]) -> dict[str, Any]:
        self.async_last_state = state
        return self.response


def test_task_tool_filters_private_state_and_returns_tool_message(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_runnable = _FakeRunnable(
        {
            "messages": [AIMessage(content="subagent result")],
            "kept_state": {"ok": True},
            "memory_contents": "do-not-leak",
        }
    )
    create_agent_calls: list[dict[str, Any]] = []

    def fake_create_agent(**kwargs: Any) -> _FakeRunnable:
        create_agent_calls.append(kwargs)
        return fake_runnable

    monkeypatch.setattr("src.ai.agents.subagents.create_agent", fake_create_agent)

    task_tool = build_task_tool(
        model=object(),  # type: ignore[arg-type]
        subagents=[
            {
                "name": "researcher",
                "description": "Research things",
                "system_prompt": "You are a researcher.",
            }
        ],
        base_tools=[],
        default_middleware=["skills", "memory"],  # type: ignore[list-item]
    )

    runtime = SimpleNamespace(
        tool_call_id="tool-1",
        state={
            "messages": ["parent-message"],
            "visible": 123,
            "skills_metadata": ["private-skill"],
            "skills_listing": "- private: skill",
            "invoked_skills": {"private": {"content": "do-not-leak"}},
            "memory_contents": "private-memory",
        },
    )

    result = task_tool.func(  # type: ignore[misc]
        description="Investigate topic X",
        subagent_type="researcher",
        runtime=runtime,
    )

    assert fake_runnable.last_state is not None
    assert fake_runnable.last_state["visible"] == 123
    assert fake_runnable.last_state["messages"] == [HumanMessage(content="Investigate topic X")]
    assert "skills_metadata" not in fake_runnable.last_state
    assert "skills_listing" not in fake_runnable.last_state
    assert "invoked_skills" not in fake_runnable.last_state
    assert "memory_contents" not in fake_runnable.last_state

    assert len(create_agent_calls) == 1
    assert create_agent_calls[0]["middleware"] == ["skills", "memory"]

    tool_message = result.update["messages"][0]
    assert isinstance(tool_message, ToolMessage)
    assert tool_message.content == "subagent result"
    assert result.update["kept_state"] == {"ok": True}
    assert "memory_contents" not in result.update


@pytest.mark.asyncio
async def test_task_tool_async_path_matches_sync_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_runnable = _FakeRunnable(
        {
            "messages": [AIMessage(content=[{"type": "text", "text": "async result"}])],
            "analysis_id": "run-42",
        }
    )

    monkeypatch.setattr("src.ai.agents.subagents.create_agent", lambda **_: fake_runnable)

    task_tool = build_task_tool(
        model=object(),  # type: ignore[arg-type]
        subagents=[
            {
                "name": "analyst",
                "description": "Analyze things",
                "system_prompt": "You are an analyst.",
            }
        ],
    )

    runtime = SimpleNamespace(tool_call_id="tool-2", state={"shared": "value"})
    result = await task_tool.coroutine(  # type: ignore[misc]
        description="Analyze file Y",
        subagent_type="analyst",
        runtime=runtime,
    )

    assert fake_runnable.async_last_state is not None
    assert fake_runnable.async_last_state["shared"] == "value"
    assert fake_runnable.async_last_state["messages"] == [HumanMessage(content="Analyze file Y")]
    assert result.update["analysis_id"] == "run-42"
    assert result.update["messages"][0].content == "async result"


def test_task_tool_rejects_unknown_subagent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.ai.agents.subagents.create_agent",
        lambda **_: _FakeRunnable({"messages": [AIMessage(content="unused")]}),
    )
    task_tool = build_task_tool(
        model=object(),  # type: ignore[arg-type]
        subagents=[
            {
                "name": "planner",
                "description": "Plan things",
                "system_prompt": "You are a planner.",
            }
        ],
    )

    runtime = SimpleNamespace(tool_call_id="tool-3", state={})
    result = task_tool.func(  # type: ignore[misc]
        description="Plan task Z",
        subagent_type="missing",
        runtime=runtime,
    )

    assert "does not exist" in result
    assert "`planner`" in result


def test_task_tool_requires_tool_call_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.ai.agents.subagents.create_agent",
        lambda **_: _FakeRunnable({"messages": [AIMessage(content="unused")]}),
    )
    task_tool = build_task_tool(
        model=object(),  # type: ignore[arg-type]
        subagents=[
            {
                "name": "coder",
                "description": "Write code",
                "system_prompt": "You are a coder.",
            }
        ],
    )

    runtime = SimpleNamespace(tool_call_id=None, state={})
    with pytest.raises(ValueError, match="Tool call ID is required"):
        task_tool.func(  # type: ignore[misc]
            description="Implement feature A",
            subagent_type="coder",
            runtime=runtime,
        )

