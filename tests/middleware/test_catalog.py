"""Tests for src/ai/prompts/catalog.py — static system prompt section builders."""

import pytest

from src.ai.prompts.catalog import (
    BASE_SYSTEM_PROMPT,
    build_base_prompt,
    _identity_section,
    _system_section,
    _doing_tasks_section,
    _actions_section,
    _tools_section,
    _tone_section,
)


class TestBuildBasePrompt:
    def test_contains_all_section_headings(self):
        prompt = build_base_prompt()
        for heading in ["# System", "# Doing Tasks", "# Executing Actions", "# Using Your Tools", "# Tone"]:
            assert heading in prompt, f"Missing section: {heading}"

    def test_sections_joined_with_double_newline(self):
        prompt = build_base_prompt()
        assert "\n\n" in prompt

    def test_non_empty(self):
        assert len(build_base_prompt()) > 100

    def test_backward_compat_base_system_prompt(self):
        assert BASE_SYSTEM_PROMPT == build_base_prompt()

    def test_deterministic(self):
        assert build_base_prompt() == build_base_prompt()


class TestIdentitySection:
    def test_mentions_aethos(self):
        assert "Aethos" in _identity_section()

    def test_mentions_tools(self):
        assert "tool" in _identity_section().lower()

    def test_mentions_terminal_or_ui(self):
        text = _identity_section().lower()
        assert "terminal" in text or "ui" in text or "interactive" in text


class TestSystemSection:
    def test_mentions_markdown(self):
        assert "markdown" in _system_section().lower()

    def test_mentions_permission(self):
        assert "permission" in _system_section().lower()

    def test_mentions_prompt_injection(self):
        assert "injection" in _system_section().lower()

    def test_mentions_context_limits(self):
        text = _system_section().lower()
        assert "compact" in text or "context" in text


class TestDoingTasksSection:
    def test_mentions_todos(self):
        assert "write_todos" in _doing_tasks_section() or "todo" in _doing_tasks_section().lower()

    def test_discourages_over_engineering(self):
        text = _doing_tasks_section().lower()
        assert "abstract" in text or "over-engineer" in text or "beyond what" in text

    def test_encourages_completion(self):
        text = _doing_tasks_section().lower()
        assert "complete" in text or "fully" in text


class TestActionsSection:
    def test_mentions_reversibility(self):
        text = _actions_section().lower()
        assert "revers" in text

    def test_lists_risky_examples(self):
        text = _actions_section().lower()
        assert "delet" in text or "force" in text or "push" in text

    def test_discourages_destructive_shortcuts(self):
        text = _actions_section().lower()
        assert "destruct" in text or "shortcut" in text or "root cause" in text


class TestToolsSection:
    def test_mentions_parallel_calls(self):
        assert "parallel" in _tools_section().lower()

    def test_mentions_dedicated_tools(self):
        text = _tools_section().lower()
        assert "read_file" in text or "edit_file" in text or "dedicated" in text

    def test_mentions_task_delegation(self):
        assert "task" in _tools_section().lower()


class TestToneSection:
    def test_discourages_emojis(self):
        assert "emoji" in _tone_section().lower()

    def test_requires_conciseness(self):
        text = _tone_section().lower()
        assert "concise" in text or "short" in text

    def test_mentions_file_line_format(self):
        assert "line_number" in _tone_section() or "line" in _tone_section().lower()

    def test_discourages_preamble(self):
        text = _tone_section().lower()
        assert "sure" in text or "preamble" in text or "narrat" in text
