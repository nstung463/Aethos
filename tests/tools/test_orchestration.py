"""Tests for orchestration tools: skill, send_message, team_create, team_delete."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace


def test_skill_invokes_registered_skill() -> None:
    from src.ai.tools.orchestration.skill import build_skill_tool
    tool = build_skill_tool(skill_runner=lambda name, args: f"ran:{name}:{args}")
    result = tool.invoke({"skill": "my-skill", "args": "some args"})
    assert result == "ran:my-skill:some args"


def test_skill_missing_skill() -> None:
    from src.ai.tools.orchestration.skill import build_skill_tool
    def failing_runner(name: str, args: str) -> str:
        raise FileNotFoundError(f"Skill '{name}' not found")
    tool = build_skill_tool(skill_runner=failing_runner)
    result = tool.invoke({"skill": "nope", "args": ""})
    assert "not found" in result.lower() or "error" in result.lower()


def _write_skill(root: Path, frontmatter: str, body: str = "Full instructions.") -> None:
    skill_dir = root / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n{body}\n", encoding="utf-8")


def test_skill_tool_returns_command_and_persists_invoked_skill(workspace: Path) -> None:
    from langchain_core.messages import ToolMessage
    from langgraph.types import Command
    from src.ai.skills import SkillRegistry
    from src.ai.tools.orchestration.skill import build_skill_tool

    _write_skill(workspace, "name: demo\ndescription: Demo skill")
    tool = build_skill_tool(SkillRegistry(workspace))
    runtime = SimpleNamespace(tool_call_id="call-1", state={})

    result = tool.func("demo", "args", runtime)  # type: ignore[misc]

    assert isinstance(result, Command)
    assert "demo" in result.update["invoked_skills"]
    assert result.update["invoked_skills"]["demo"]["args"] == "args"
    message = result.update["messages"][0]
    assert isinstance(message, ToolMessage)
    assert "<command-name>demo</command-name>" in message.content


def test_skill_tool_denies_skill_by_rule(workspace: Path) -> None:
    from src.ai.permissions import PermissionContext, PermissionMode
    from src.ai.permissions.types import PermissionBehavior, PermissionRule, PermissionSource, PermissionSubject
    from src.ai.skills import SkillRegistry
    from src.ai.tools.orchestration.skill import build_skill_tool

    _write_skill(workspace, "name: demo\ndescription: Demo skill")
    context = PermissionContext(
        mode=PermissionMode.DEFAULT,
        workspace_root=workspace,
        working_directories=(workspace,),
        rules=(
            PermissionRule(
                subject=PermissionSubject.SKILL,
                behavior=PermissionBehavior.DENY,
                source=PermissionSource.USER,
                matcher="demo",
            ),
        ),
    )
    tool = build_skill_tool(SkillRegistry(workspace), permission_context=context)

    result = tool.func("demo", "", SimpleNamespace(tool_call_id="call-1", state={}))  # type: ignore[misc]

    assert isinstance(result, str)
    assert "Permission denied" in result


def test_skill_tool_dont_ask_denies_skill_that_requires_tools(workspace: Path) -> None:
    from src.ai.permissions import PermissionContext, PermissionMode
    from src.ai.skills import SkillRegistry
    from src.ai.tools.orchestration.skill import build_skill_tool

    _write_skill(workspace, "name: demo\ndescription: Demo skill\nallowed-tools: Bash")
    context = PermissionContext(
        mode=PermissionMode.DONT_ASK,
        workspace_root=workspace,
        working_directories=(workspace,),
    )
    tool = build_skill_tool(SkillRegistry(workspace), permission_context=context)

    result = tool.func("demo", "", SimpleNamespace(tool_call_id="call-1", state={}))  # type: ignore[misc]

    assert isinstance(result, str)
    assert "Permission denied" in result


def test_skill_tool_bypass_allows_skill_that_requires_tools(workspace: Path) -> None:
    from langgraph.types import Command
    from src.ai.permissions import PermissionContext, PermissionMode
    from src.ai.skills import SkillRegistry
    from src.ai.tools.orchestration.skill import build_skill_tool

    _write_skill(workspace, "name: demo\ndescription: Demo skill\nallowed-tools: Bash")
    context = PermissionContext(
        mode=PermissionMode.BYPASS_PERMISSIONS,
        workspace_root=workspace,
        working_directories=(workspace,),
    )
    tool = build_skill_tool(SkillRegistry(workspace), permission_context=context)

    result = tool.func("demo", "", SimpleNamespace(tool_call_id="call-1", state={}))  # type: ignore[misc]

    assert isinstance(result, Command)


def test_skill_tool_asks_for_skill_that_requires_tools(workspace: Path, monkeypatch) -> None:
    from langgraph.types import Command
    from src.ai.permissions import PermissionContext, PermissionMode
    from src.ai.skills import SkillRegistry
    from src.ai.tools.orchestration import skill as skill_module

    _write_skill(workspace, "name: demo\ndescription: Demo skill\nallowed-tools: Bash")
    captured: dict = {}

    def _approve(payload: dict) -> dict:
        captured.update(payload)
        return {"approved": True}

    monkeypatch.setattr(skill_module, "interrupt", _approve)
    context = PermissionContext(
        mode=PermissionMode.DEFAULT,
        workspace_root=workspace,
        working_directories=(workspace,),
    )
    tool = skill_module.build_skill_tool(SkillRegistry(workspace), permission_context=context)

    result = tool.func("demo", "", SimpleNamespace(tool_call_id="call-1", state={}))  # type: ignore[misc]

    assert isinstance(result, Command)
    assert captured["subject"] == "skill"
    assert captured["skill"] == "demo"
    assert captured["allowed_tools"] == ["Bash"]


def test_send_message_delivers_to_recipient() -> None:
    from src.ai.tools.orchestration.send_message import build_send_message_tool
    mailbox: dict[str, list] = {}
    def deliver(to: str, content: str) -> None:
        mailbox.setdefault(to, []).append(content)
    tool = build_send_message_tool(deliver_fn=deliver)
    result = json.loads(tool.invoke({"to": "agent-2", "content": "hello there"}))
    assert result["delivered"] is True
    assert mailbox["agent-2"] == ["hello there"]


def test_send_message_returns_ack() -> None:
    from src.ai.tools.orchestration.send_message import build_send_message_tool
    tool = build_send_message_tool(deliver_fn=lambda to, content: None)
    result = json.loads(tool.invoke({"to": "team-lead", "content": "done"}))
    assert "delivered" in result


def test_team_create_registers_team() -> None:
    from src.ai.tools.orchestration.team_create import build_team_create_tool
    registry: dict = {}
    tool = build_team_create_tool(registry=registry)
    result = json.loads(tool.invoke({"name": "my-team", "description": "A research team"}))
    assert result["created"] is True
    assert "my-team" in registry


def test_team_delete_removes_team() -> None:
    from src.ai.tools.orchestration.team_delete import build_team_delete_tool
    registry = {"my-team": {"name": "my-team"}}
    tool = build_team_delete_tool(registry=registry)
    result = json.loads(tool.invoke({"name": "my-team"}))
    assert result["deleted"] is True
    assert "my-team" not in registry


def test_team_delete_missing_team() -> None:
    from src.ai.tools.orchestration.team_delete import build_team_delete_tool
    tool = build_team_delete_tool(registry={})
    result = tool.invoke({"name": "ghost-team"})
    assert "not found" in result.lower()

