"""skill tool - invoke a named skill by name."""
from __future__ import annotations

import time
from typing import Annotated, Callable

from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg, StructuredTool
from langchain_core.messages import ToolMessage
from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field

from src.ai.permissions.evaluator import PermissionEvaluator
from src.ai.permissions.types import (
    PermissionBehavior,
    PermissionContext,
    PermissionDecision,
    PermissionSubject,
)
from src.ai.skills import SkillDefinition, SkillRegistry


class SkillInput(BaseModel):
    skill: str = Field(description="Name of the skill to invoke.")
    args: str = Field(default="", description="Optional arguments to pass to the skill.")


def _default_skill_policy(skill: SkillDefinition) -> PermissionDecision:
    if skill.loaded_from == "mcp" or skill.allowed_tools or skill.context == "fork":
        return PermissionDecision(
            behavior=PermissionBehavior.ASK,
            reason="Skill requires approval because it is remote, requests tools, or uses forked execution",
        )
    return PermissionDecision(
        behavior=PermissionBehavior.ALLOW,
        reason="Local skill without elevated tool requirements",
    )


def _approval_options() -> list[dict[str, str]]:
    return [
        {"id": "once", "label": "Approve once"},
        {"id": "thread_skill", "label": "Allow this skill in this thread"},
        {"id": "user_skill", "label": "Always allow this skill"},
    ]


def _permission_error(
    *,
    skill: SkillDefinition,
    permission_context: PermissionContext | None,
) -> str | None:
    if permission_context is None:
        return None

    decision = PermissionEvaluator().evaluate(
        context=permission_context,
        subject=PermissionSubject.SKILL,
        candidate=skill.name,
        policy_decision=_default_skill_policy(skill),
    )

    if decision.behavior is PermissionBehavior.ALLOW:
        return None
    if decision.behavior is PermissionBehavior.ASK:
        user_decision = interrupt(
            {
                "behavior": "ask",
                "reason": decision.reason,
                "subject": PermissionSubject.SKILL.value,
                "skill": skill.name,
                "source": skill.source,
                "path": str(skill.path) if skill.path else None,
                "server": skill.server,
                "allowed_tools": list(skill.allowed_tools),
                "approval_options": _approval_options(),
                "suggestions": [s.value for s in (decision.suggestions or [])],
            }
        )
        if user_decision.get("approved", False):
            return None
        return "Permission denied by user."

    return f"Permission denied: {decision.reason}"


def _invoked_skill_record(skill: SkillDefinition, args: str, content: str) -> dict:
    return {
        "name": skill.name,
        "path": str(skill.path) if skill.path else None,
        "source": skill.source,
        "loaded_from": skill.loaded_from,
        "server": skill.server,
        "remote_name": skill.remote_name,
        "args": args,
        "content": content,
        "invoked_at": time.time(),
    }


def build_skill_tool(
    skill_runner: Callable[[str, str], str] | SkillRegistry,
    permission_context: PermissionContext | None = None,
) -> StructuredTool:
    if isinstance(skill_runner, SkillRegistry):
        registry: SkillRegistry | None = skill_runner
        runner = skill_runner.render_skill_prompt
    else:
        registry = None
        runner = skill_runner

    def _invoke(skill: str, args: str = "", runtime: Annotated[ToolRuntime | None, InjectedToolArg] = None) -> str | Command:
        try:
            definition = registry.get(skill) if registry is not None else None
            if definition is not None:
                error = _permission_error(skill=definition, permission_context=permission_context)
                if error is not None:
                    return error
            prompt = runner(skill, args)
            if definition is None or runtime is None or not runtime.tool_call_id:
                return prompt
            invoked = dict(getattr(runtime, "state", {}).get("invoked_skills", {}) or {})
            invoked[definition.name] = _invoked_skill_record(definition, args, prompt)
            return Command(
                update={
                    "invoked_skills": invoked,
                    "messages": [ToolMessage(prompt, tool_call_id=runtime.tool_call_id)],
                }
            )
        except FileNotFoundError as exc:
            return f"Error: {exc}"
        except Exception as exc:
            return f"Error invoking skill '{skill}': {exc}"

    return StructuredTool.from_function(
        name="skill", func=_invoke,
        description=(
            "Execute a skill within the main conversation\n\n"
            "When users ask you to perform tasks, check if any of the available skills match. "
            "Skills provide specialized capabilities and domain knowledge.\n\n"
            'When users reference a "slash command" or "/<something>" '
            '(e.g., "/commit", "/review-pr"), they are referring to a skill. '
            "Use this tool to invoke it.\n\n"
            "How to invoke:\n"
            "- Use this tool with the skill name and optional arguments\n"
            '- Examples: skill: "pdf"; skill: "commit", args: "-m \'Fix bug\'"; '
            'skill: "review-pr", args: "123"; skill: "ms-office-suite:pdf"\n\n'
            "Important:\n"
            "- Available skills are listed in system-reminder messages in the conversation\n"
            "- When a skill matches the user's request, this is a BLOCKING REQUIREMENT: "
            "invoke the relevant skill tool BEFORE generating any other response about the task\n"
            "- NEVER mention a skill without actually calling this tool\n"
            "- Do not invoke a skill that is already running\n"
            "- Do not use this tool for built-in CLI commands\n"
            "- If you see a <command-name> tag in the current conversation turn, "
            "the skill has ALREADY been loaded - follow the instructions directly instead of calling this tool again"
        ),
        infer_schema=False,
        args_schema=SkillInput,
    )
