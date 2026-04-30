"""Subagent specs and task tool builder."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, NotRequired, TypedDict, cast

from langchain.agents import create_agent
from langchain.agents.middleware.types import AgentMiddleware
from langchain.tools import ToolRuntime
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.types import Command
from pydantic import BaseModel, Field

from src.ai.prompts.catalog import ANALYST_PROMPT, CODER_PROMPT, PLANNER_PROMPT, RESEARCHER_PROMPT
from src.ai.tools.web import tavily_search, web_fetch_tool


class SubAgentSpec(TypedDict):
    """Declarative subagent configuration."""

    name: str
    description: str
    system_prompt: str
    tools: NotRequired[Sequence[BaseTool | Callable | dict[str, Any]]]
    model: NotRequired[BaseChatModel]
    middleware: NotRequired[list[AgentMiddleware]]


class _CompiledSubAgent(TypedDict):
    """Internal spec used by the task tool."""

    name: str
    description: str
    runnable: Runnable


_EXCLUDED_STATE_KEYS = {
    "messages",
        "todos",
    "structured_response",
    "skills_metadata",
    "skills_listing",
    "invoked_skills",
    "memory_contents",
}

PLANNER: SubAgentSpec = {
    "name": "planner",
    "description": (
        "Break down a complex task into clear, ordered, actionable steps. "
        "Use before acting on multi-part requests."
    ),
    "system_prompt": PLANNER_PROMPT,
    "tools": [],
}

RESEARCHER: SubAgentSpec = {
    "name": "researcher",
    "description": (
        "Gather current, accurate information from the web on a specific topic. "
        "Use for research requiring up-to-date knowledge outside the codebase."
    ),
    "system_prompt": RESEARCHER_PROMPT,
    "tools": [tavily_search, web_fetch_tool],
}

CODER: SubAgentSpec = {
    "name": "coder",
    "description": (
        "Implement, debug, or refactor code in isolation. "
        "Use for focused coding tasks that would bloat the main context."
    ),
    "system_prompt": CODER_PROMPT,
}

ANALYST: SubAgentSpec = {
    "name": "analyst",
    "description": (
        "Analyze code, data, logs, or documents and return structured insights. "
        "Use when you need a thorough analysis report."
    ),
    "system_prompt": ANALYST_PROMPT,
    "tools": [web_fetch_tool],
}

DEFAULT_SUBAGENTS: list[SubAgentSpec] = [PLANNER, RESEARCHER, CODER, ANALYST]

TASK_DESCRIPTION = """Launch an ephemeral subagent to handle a complex, isolated task.

Available subagent types:
{available_agents}

Usage notes:
- Provide ALL context in the description. Subagents are stateless after each invocation.
- Launch multiple in parallel when tasks are independent by emitting multiple tool calls in one message.
- Each subagent returns a single final message back to you. Summarize that result for the user.
- Use subagents for tasks that are complex, multi-step, or that benefit from isolated context.
- The subagent output should generally be trusted unless it conflicts with strong evidence from the main thread."""


class TaskInput(BaseModel):
    """Input schema for the `task` tool."""

    description: str = Field(
        description=(
            "Detailed task description for the subagent. "
            "Include all necessary context and specify the expected output format."
        )
    )
    subagent_type: str = Field(
        description="Subagent to use. Must be one of the available types listed above."
    )


def _extract_message_text(message: Any) -> str:
    """Extract plain text from the last subagent message."""
    text = getattr(message, "text", None)
    if isinstance(text, str):
        return text

    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if isinstance(block.get("text"), str):
                    parts.append(block["text"])
            else:
                parts.append(str(block))
        return " ".join(part for part in parts if part).strip()
    return str(content)


def build_task_tool(
    model: BaseChatModel,
    subagents: Sequence[SubAgentSpec],
    base_tools: Sequence[BaseTool | Callable | dict[str, Any]] | None = None,
    default_middleware: Sequence[AgentMiddleware] | None = None,
) -> StructuredTool:
    """Compile subagent specs into agents and return a DeepAgents-style `task` tool."""
    base_tools = base_tools or ()
    default_middleware = default_middleware or ()

    compiled: list[_CompiledSubAgent] = []
    for spec in subagents:
        tools = spec.get("tools", base_tools)
        subagent_model = spec.get("model", model)
        middleware = [*default_middleware, *spec.get("middleware", [])]
        compiled.append(
            {
                "name": spec["name"],
                "description": spec["description"],
                "runnable": create_agent(
                    model=subagent_model,
                    tools=tools,
                    system_prompt=spec["system_prompt"],
                    middleware=middleware,
                    name=spec["name"],
                ),
            }
        )

    agent_runnables = {spec["name"]: spec["runnable"] for spec in compiled}
    agents_desc = "\n".join(f"- {spec['name']}: {spec['description']}" for spec in compiled)
    description = TASK_DESCRIPTION.format(available_agents=agents_desc)

    def _return_command_with_state_update(result: dict[str, Any], tool_call_id: str) -> Command:
        if "messages" not in result:
            raise ValueError("Subagent result must contain a 'messages' key.")

        state_update = {
            key: value
            for key, value in result.items()
            if key not in _EXCLUDED_STATE_KEYS
        }
        message_text = _extract_message_text(result["messages"][-1]).rstrip()
        return Command(
            update={
                **state_update,
                "messages": [ToolMessage(message_text, tool_call_id=tool_call_id)],
            }
        )

    def _validate_and_prepare_state(
        subagent_type: str,
        description: str,
        runtime: ToolRuntime,
    ) -> tuple[Runnable, dict[str, Any]]:
        subagent = cast(Runnable, agent_runnables[subagent_type])
        parent_state = cast(dict[str, Any], getattr(runtime, "state", {}) or {})
        subagent_state = {
            key: value
            for key, value in parent_state.items()
            if key not in _EXCLUDED_STATE_KEYS
        }
        subagent_state["messages"] = [HumanMessage(content=description)]
        return subagent, subagent_state

    def task(
        description: str,
        subagent_type: str,
        runtime: ToolRuntime,
    ) -> str | Command:
        if subagent_type not in agent_runnables:
            allowed = ", ".join(f"`{name}`" for name in agent_runnables)
            return f"We cannot invoke subagent {subagent_type} because it does not exist, the only allowed types are {allowed}"
        if not runtime.tool_call_id:
            raise ValueError("Tool call ID is required for subagent invocation")

        subagent, subagent_state = _validate_and_prepare_state(
            subagent_type, description, runtime
        )
        result = cast(dict[str, Any], subagent.invoke(subagent_state))
        return _return_command_with_state_update(result, runtime.tool_call_id)

    async def atask(
        description: str,
        subagent_type: str,
        runtime: ToolRuntime,
    ) -> str | Command:
        if subagent_type not in agent_runnables:
            allowed = ", ".join(f"`{name}`" for name in agent_runnables)
            return f"We cannot invoke subagent {subagent_type} because it does not exist, the only allowed types are {allowed}"
        if not runtime.tool_call_id:
            raise ValueError("Tool call ID is required for subagent invocation")

        subagent, subagent_state = _validate_and_prepare_state(
            subagent_type, description, runtime
        )
        result = cast(dict[str, Any], await subagent.ainvoke(subagent_state))
        return _return_command_with_state_update(result, runtime.tool_call_id)

    return StructuredTool.from_function(
        name="task",
        func=task,
        coroutine=atask,
        description=description,
        infer_schema=False,
        args_schema=TaskInput,
    )

