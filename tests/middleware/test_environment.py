"""Tests for EnvironmentMiddleware and build_environment_section()."""

from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import BaseMessage, SystemMessage

from src.ai.middleware.environment import (
    EnvironmentMiddleware,
    _collect_project_instructions,
    build_environment_section,
)


# ---------------------------------------------------------------------------
# Fake ModelRequest — mirrors the real interface used by middleware
# ---------------------------------------------------------------------------

@dataclass
class _FakeModelRequest:
    state: dict[str, Any]
    system_message: BaseMessage | None = None
    _overrides: dict[str, Any] = field(default_factory=dict)

    def override(self, **kwargs: Any) -> _FakeModelRequest:
        return _FakeModelRequest(
            state=self.state,
            system_message=kwargs.get("system_message", self.system_message),
        )


# ---------------------------------------------------------------------------
# Fake Runtime (no-op — middleware doesn't use it for env section)
# ---------------------------------------------------------------------------

class _FakeRuntime:
    pass


# ---------------------------------------------------------------------------
# Tests: build_environment_section()
# ---------------------------------------------------------------------------

class TestBuildEnvironmentSection:
    def test_includes_working_directory(self, tmp_path: Path):
        result = build_environment_section(str(tmp_path))
        assert str(tmp_path) in result

    def test_includes_today_date(self, tmp_path: Path):
        result = build_environment_section(str(tmp_path))
        assert date.today().isoformat() in result

    def test_includes_platform(self, tmp_path: Path):
        result = build_environment_section(str(tmp_path))
        assert platform.system().lower() in result

    def test_git_info_absent_when_not_git_repo(self, tmp_path: Path, monkeypatch):
        # Patch _git_info to simulate a directory outside any git repo
        monkeypatch.setattr("src.ai.middleware.environment._git_info", lambda _cwd: None)
        result = build_environment_section(str(tmp_path))
        assert "Is a git repository: no" in result
        assert "Current branch" not in result

    def test_git_info_injected_when_git_repo(self, tmp_path: Path, monkeypatch):
        fake_git = {"branch": "main", "status": "M  src/foo.py", "commits": "abc1234 feat: add foo", "user": "Tester"}
        monkeypatch.setattr("src.ai.middleware.environment._git_info", lambda _cwd: fake_git)
        result = build_environment_section(str(tmp_path))
        assert "Is a git repository: yes" in result
        assert "Current branch: main" in result
        assert "Tester" in result

    def test_model_name_injected_when_provided(self, tmp_path: Path):
        result = build_environment_section(str(tmp_path), model_name="claude-sonnet-4-5")
        assert "claude-sonnet-4-5" in result

    def test_model_name_absent_when_not_provided(self, tmp_path: Path):
        result = build_environment_section(str(tmp_path))
        assert "Model:" not in result

    def test_project_instructions_injected_when_ethos_md_exists(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()  # stop hierarchy walk at tmp_path
        (tmp_path / "ETHOS.md").write_text("# My Project\nThis is a test project.")
        result = build_environment_section(str(tmp_path))
        assert "Project Instructions" in result
        assert "This is a test project" in result

    def test_project_instructions_absent_when_no_file(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()  # stop hierarchy walk at tmp_path — no instruction files here
        result = build_environment_section(str(tmp_path))
        assert "Project Instructions" not in result

    def test_claude_md_used_when_ethos_md_missing(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        (tmp_path / "CLAUDE.md").write_text("# CLAUDE\nInstructions here.")
        result = build_environment_section(str(tmp_path))
        assert "Instructions here" in result


# ---------------------------------------------------------------------------
# Tests: _collect_project_instructions() hierarchy walk
# ---------------------------------------------------------------------------

class TestCollectProjectInstructions:
    def test_returns_none_when_no_files(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()  # stop walk at tmp_path, no instruction files here
        result = _collect_project_instructions(str(tmp_path))
        assert result is None

    def test_reads_single_ethos_md(self, tmp_path: Path):
        (tmp_path / "ETHOS.md").write_text("Root instructions.")
        result = _collect_project_instructions(str(tmp_path))
        assert result is not None
        assert "Root instructions." in result

    def test_hierarchy_walk_merges_parent_and_child(self, tmp_path: Path):
        # Parent dir has CLAUDE.md; child subdir has ETHOS.md
        child = tmp_path / "project"
        child.mkdir()
        (tmp_path / "CLAUDE.md").write_text("Global rules.")
        (child / "ETHOS.md").write_text("Project-specific rules.")
        # Mark parent as git root to limit walk
        (tmp_path / ".git").mkdir()

        result = _collect_project_instructions(str(child))
        assert result is not None
        assert "Global rules." in result
        assert "Project-specific rules." in result
        # project-specific should appear AFTER global (outermost first → reversed)
        assert result.index("Global rules.") < result.index("Project-specific rules.")

    def test_stops_at_git_root(self, tmp_path: Path):
        # git root has CLAUDE.md; above git root also has CLAUDE.md — should NOT be included
        git_root = tmp_path / "repo"
        above = tmp_path
        git_root.mkdir()
        (git_root / ".git").mkdir()
        (git_root / "CLAUDE.md").write_text("Repo level.")
        (above / "CLAUDE.md").write_text("Above repo — should be ignored.")

        result = _collect_project_instructions(str(git_root))
        assert "Repo level." in result
        assert "Above repo" not in result

    def test_ethos_md_takes_priority_over_claude_md(self, tmp_path: Path):
        (tmp_path / "ETHOS.md").write_text("Ethos wins.")
        (tmp_path / "CLAUDE.md").write_text("Claude loses.")
        result = _collect_project_instructions(str(tmp_path))
        assert "Ethos wins." in result
        assert "Claude loses." not in result

    def test_empty_file_skipped(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()  # stop walk at tmp_path
        (tmp_path / "ETHOS.md").write_text("   ")  # whitespace only
        result = _collect_project_instructions(str(tmp_path))
        assert result is None


# ---------------------------------------------------------------------------
# Tests: EnvironmentMiddleware
# ---------------------------------------------------------------------------

class TestEnvironmentMiddleware:
    def test_before_agent_returns_state_update_first_call(self, tmp_path: Path):
        mw = EnvironmentMiddleware(root_dir=str(tmp_path))
        update = mw.before_agent(state={}, runtime=_FakeRuntime())
        assert update is not None
        assert "_env_section" in update
        assert isinstance(update["_env_section"], str)

    def test_before_agent_returns_none_when_already_cached(self, tmp_path: Path):
        mw = EnvironmentMiddleware(root_dir=str(tmp_path))
        cached_state = {"_env_section": "already computed"}
        update = mw.before_agent(state=cached_state, runtime=_FakeRuntime())
        assert update is None

    @pytest.mark.asyncio
    async def test_abefore_agent_caches_correctly(self, tmp_path: Path):
        mw = EnvironmentMiddleware(root_dir=str(tmp_path))
        update = await mw.abefore_agent(state={}, runtime=_FakeRuntime())
        assert update is not None
        assert "_env_section" in update

        update2 = await mw.abefore_agent(state={"_env_section": update["_env_section"]}, runtime=_FakeRuntime())
        assert update2 is None

    def test_modify_request_appends_to_existing_system_message(self, tmp_path: Path):
        mw = EnvironmentMiddleware(root_dir=str(tmp_path))
        section = "# Environment\n- Working directory: /tmp"
        req = _FakeModelRequest(
            state={"_env_section": section},
            system_message=SystemMessage(content="Base prompt."),
        )
        result = mw.modify_request(req)
        content = result.system_message.content
        assert "Base prompt." in content
        assert "# Environment" in content

    def test_modify_request_creates_system_message_when_none(self, tmp_path: Path):
        mw = EnvironmentMiddleware(root_dir=str(tmp_path))
        section = "# Environment\n- Working directory: /tmp"
        req = _FakeModelRequest(state={"_env_section": section}, system_message=None)
        result = mw.modify_request(req)
        assert result.system_message is not None
        assert "# Environment" in result.system_message.content

    def test_modify_request_skips_when_no_section(self, tmp_path: Path):
        mw = EnvironmentMiddleware(root_dir=str(tmp_path))
        req = _FakeModelRequest(state={"_env_section": None}, system_message=SystemMessage(content="Unchanged."))
        result = mw.modify_request(req)
        assert result.system_message.content == "Unchanged."

    def test_model_name_passed_through(self, tmp_path: Path):
        mw = EnvironmentMiddleware(root_dir=str(tmp_path), model_name="gpt-4o")
        update = mw.before_agent(state={}, runtime=_FakeRuntime())
        assert "gpt-4o" in update["_env_section"]
