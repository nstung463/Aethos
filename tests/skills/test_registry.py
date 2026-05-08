from __future__ import annotations

from pathlib import Path

import pytest

from src.ai.skills import SkillNotFoundError, SkillRegistry


def _write_skill(root: Path, folder: str, frontmatter: str, body: str = "Full instructions.") -> None:
    skill_dir = root / folder
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n{body}\n", encoding="utf-8")


def _registry(workspace: Path, user_root: Path | None = None) -> SkillRegistry:
    return SkillRegistry(workspace, user_ethos_skill_root=user_root or workspace / "__no_user_ethos__")


def test_discovers_supported_skill_sources(workspace: Path) -> None:
    _write_skill(workspace / ".ethos" / "skills", "ethos", "name: ethos\ndescription: Project Ethos skill")
    _write_skill(workspace / "__user_ethos__" / ".ethos" / "skills", "user", "name: user\ndescription: User Ethos skill")

    registry = _registry(workspace, user_root=workspace / "__user_ethos__" / ".ethos" / "skills")
    skills = {skill.name: skill for skill in registry.discover()}

    assert set(skills) == {"ethos", "user"}
    assert skills["ethos"].source == "ethos_project"
    assert skills["user"].source == "ethos_user"


def test_parses_claude_compatible_frontmatter(workspace: Path) -> None:
    _write_skill(
        workspace / ".ethos" / "skills",
        "review",
        "\n".join(
            [
                "name: review",
                "description: Review code",
                "when_to_use: Before merging",
                "aliases: pr-review, /codereview",
                "allowed-tools: Bash, Read",
                "argument-hint: PR number",
                "arguments:",
                "  - pr",
                "model: claude-sonnet",
                "effort: high",
                "context: fork",
                "agent: reviewer",
                "paths:",
                "  - src/**",
                "unknown-field: preserved",
            ]
        ),
    )

    skill = _registry(workspace).get("review")

    assert skill.when_to_use == "Before merging"
    assert skill.aliases == ("pr-review", "codereview")
    assert skill.allowed_tools == ("Bash", "Read")
    assert skill.argument_hint == "PR number"
    assert skill.arguments == ("pr",)
    assert skill.model == "claude-sonnet"
    assert skill.effort == "high"
    assert skill.context == "fork"
    assert skill.agent == "reviewer"
    assert skill.paths == ("src/**",)
    assert skill.raw_frontmatter["unknown-field"] == "preserved"


def test_duplicate_names_use_source_priority(workspace: Path) -> None:
    user_root = workspace / "__user_ethos__" / ".ethos" / "skills"
    _write_skill(workspace / ".ethos" / "skills", "dupe", "name: same\ndescription: Project Ethos version")
    _write_skill(user_root, "dupe", "name: same\ndescription: User Ethos version")

    skill = _registry(workspace, user_root=user_root).get("same")

    assert skill.source == "ethos_project"
    assert skill.description == "Project Ethos version"


def test_ignores_claude_skills_directory(workspace: Path) -> None:
    _write_skill(workspace / ".claude" / "skills", "ignored", "name: ignored\ndescription: Ignored skill")

    assert _registry(workspace).discover() == []


def test_ignores_invalid_skills(workspace: Path) -> None:
    invalid = workspace / ".ethos" / "skills" / "invalid"
    invalid.mkdir(parents=True)
    (invalid / "SKILL.md").write_text("---\nname: missing-description\n---\nBody", encoding="utf-8")

    assert _registry(workspace).discover() == []


def test_render_listing_excludes_full_body(workspace: Path) -> None:
    _write_skill(
        workspace / ".ethos" / "skills",
        "writer",
        "name: writer\ndescription: Write things\nwhen_to_use: When drafting",
        body="Secret full instructions.",
    )

    listing = _registry(workspace).render_listing()

    assert "- writer: Write things - When drafting" in listing
    assert "Secret full instructions" not in listing


def test_render_skill_prompt_includes_body_and_metadata(workspace: Path) -> None:
    _write_skill(
        workspace / ".ethos" / "skills",
        "writer",
        "name: writer\ndescription: Write things\nallowed-tools: Bash, Read\ncontext: fork",
        body="Follow this exact workflow.",
    )

    prompt = _registry(workspace).render_skill_prompt("writer", "draft README")

    assert "<command-message>writer</command-message>" in prompt
    assert "<command-name>writer</command-name>" in prompt
    assert "<skill-format>true</skill-format>" in prompt
    assert "Base directory for this skill:" in prompt
    assert "Skill arguments: draft README" in prompt
    assert "This skill requests additional tool permissions: Bash, Read" in prompt
    assert "Forked skill execution is not supported" in prompt
    assert "Follow this exact workflow." in prompt
    assert "---\nname:" not in prompt


def test_unknown_skill_raises_clear_error(workspace: Path) -> None:
    with pytest.raises(SkillNotFoundError):
        _registry(workspace).get("missing")


def test_does_not_generate_default_aliases(workspace: Path) -> None:
    _write_skill(
        workspace / ".ethos" / "skills",
        "spreadsheets",
        "name: Spreadsheets\ndescription: Create spreadsheet files (.xlsx, .csv)",
    )

    registry = _registry(workspace)
    skill = registry.get("Spreadsheets")

    assert skill.name == "Spreadsheets"
    assert skill.aliases == ()
    listing = registry.render_listing()
    assert "aliases:" not in listing


class _FakeMCPRuntime:
    def __init__(self) -> None:
        self.arguments = None

    def list_prompts(self, server: str | None = None) -> str:
        return (
            '{"prompts": ['
            '{"server": "docs", "name": "generic", "description": "Plain prompt"},'
            '{"server": "docs", "name": "summarize", "description": "Summarize docs", "_meta": {"skill": true}}'
            "]}"
        )

    def get_prompt(self, server: str, name: str, arguments: dict | None = None) -> str:
        self.arguments = arguments
        return "Remote prompt with ${CLAUDE_SKILL_DIR}"


def test_discovers_mcp_prompts_as_namespaced_skills(workspace: Path) -> None:
    registry = SkillRegistry(
        workspace,
        mcp_runtime=_FakeMCPRuntime(),
        user_ethos_skill_root=workspace / "__no_user_ethos__",
    )

    skill = registry.get("mcp:docs:summarize")

    assert skill.loaded_from == "mcp"
    assert skill.source == "mcp"
    assert skill.server == "docs"
    assert skill.remote_name == "summarize"
    assert "- mcp:docs:summarize: Summarize docs" in registry.render_listing()
    assert "mcp:docs:generic" not in registry.render_listing()


def test_render_mcp_skill_prompt_does_not_substitute_skill_dir(workspace: Path) -> None:
    runtime = _FakeMCPRuntime()
    registry = SkillRegistry(
        workspace,
        mcp_runtime=runtime,
        user_ethos_skill_root=workspace / "__no_user_ethos__",
    )

    prompt = registry.render_skill_prompt("mcp:docs:summarize", "topic")

    assert "<command-name>mcp:docs:summarize</command-name>" in prompt
    assert "MCP skill source: docs:summarize" in prompt
    assert "${CLAUDE_SKILL_DIR}" in prompt
    assert runtime.arguments == {"arguments": "topic"}


def test_discovers_user_ethos_skill_root(workspace: Path, tmp_path: Path) -> None:
    user_root = tmp_path / ".ethos" / "skills"
    _write_skill(user_root, "user-review", "name: user-review\ndescription: User skill")

    skills = {skill.name: skill for skill in _registry(workspace, user_root=user_root).discover()}

    assert "user-review" in skills
    assert skills["user-review"].source == "ethos_user"
