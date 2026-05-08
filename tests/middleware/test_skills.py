from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.ai.middleware.skills import SkillsMiddleware


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


def _write_skill(root: Path) -> None:
    skill_dir = root / ".aethos" / "skills" / "review"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: review\ndescription: Review code\nwhen_to_use: before merging\n---\nFull body.",
        encoding="utf-8",
    )


def test_before_agent_caches_compact_listing(workspace: Path) -> None:
    _write_skill(workspace)
    mw = SkillsMiddleware(root_dir=str(workspace))

    update = mw.before_agent(state={}, runtime=_FakeRuntime())

    assert update == {"skills_listing": "- review: Review code - before merging"}
    assert mw.before_agent(state=update, runtime=_FakeRuntime()) is None


def test_modify_request_injects_tool_first_guidance_without_full_body(workspace: Path) -> None:
    _write_skill(workspace)
    mw = SkillsMiddleware(root_dir=str(workspace))
    state = mw.before_agent(state={}, runtime=_FakeRuntime())
    req = _FakeModelRequest(state=state, system_prompt="Base prompt.")

    result = mw.modify_request(req)
    text = result.system_prompt

    assert "Base prompt." in text
    assert "- review: Review code - before merging" in text
    assert "BLOCKING REQUIREMENT" in text
    assert "NEVER mention a skill without actually calling the `skill` tool" in text
    assert "<command-name> tag" in text
    assert "Full body." not in text


def test_modify_request_injects_only_compact_loaded_skill_reminder(workspace: Path) -> None:
    _write_skill(workspace)
    mw = SkillsMiddleware(root_dir=str(workspace))
    state = {
        "skills_listing": "- review: Review code - before merging",
        "invoked_skills": {
            "review": {
                "name": "review",
                "content": "Full body should not be repeated.",
            }
        },
    }
    req = _FakeModelRequest(state=state, system_prompt="Base prompt.")

    result = mw.modify_request(req)
    text = result.system_prompt

    assert "## Loaded Skill Reminder" in text
    assert "review" in text
    assert "Full body should not be repeated." not in text
