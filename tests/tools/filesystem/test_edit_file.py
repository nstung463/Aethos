# tests/tools/filesystem/test_edit_file.py
"""Tests for edit_file tool — parity with Claude Code FileEditTool."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from src.ai.tools.filesystem import build_filesystem_tools
from src.ai.tools.filesystem.edit_file import build_edit_file_tool
from tests.tools.filesystem.test_builder import _FakeSandbox


# ── helpers ───────────────────────────────────────────────────────────────────

def _tools(workspace: Path):
    tools = build_filesystem_tools(root_dir=str(workspace))
    read = next(t for t in tools if t.name == "read_file")
    edit = next(t for t in tools if t.name == "edit_file")
    return read, edit


# ── basic replacement ──────────────────────────────────────────────────────────

def test_edit_replaces_unique_string(workspace: Path) -> None:
    (workspace / "code.py").write_text("x = 1\ny = 2\n")
    read, edit = _tools(workspace)
    read.invoke({"path": "code.py"})
    edit.invoke({"path": "code.py", "old_string": "x = 1", "new_string": "x = 99"})
    assert (workspace / "code.py").read_text() == "x = 99\ny = 2\n"


def test_edit_output_message_single_replace(workspace: Path) -> None:
    (workspace / "f.py").write_text("a = 1\n")
    read, edit = _tools(workspace)
    read.invoke({"path": "f.py"})
    result = edit.invoke({"path": "f.py", "old_string": "a = 1", "new_string": "a = 2"})
    assert result == "The file 'f.py' has been updated successfully."


def test_edit_replace_all(workspace: Path) -> None:
    (workspace / "dup.py").write_text("x = 1\nx = 1\n")
    read, edit = _tools(workspace)
    read.invoke({"path": "dup.py"})
    result = edit.invoke({"path": "dup.py", "old_string": "x = 1", "new_string": "x = 0", "replace_all": True})
    assert (workspace / "dup.py").read_text() == "x = 0\nx = 0\n"
    assert result == "The file 'dup.py' has been updated. All occurrences were successfully replaced."


# ── read-state enforcement ─────────────────────────────────────────────────────

def test_edit_requires_read_first(workspace: Path) -> None:
    (workspace / "f.py").write_text("hello")
    tool = build_edit_file_tool(workspace)
    result = tool.invoke({"path": "f.py", "old_string": "hello", "new_string": "world"})
    assert "has not been read yet" in result.lower()


def test_edit_rejects_partial_read(workspace: Path) -> None:
    (workspace / "f.py").write_text("line1\nline2\nline3\n")
    read, edit = _tools(workspace)
    read.invoke({"path": "f.py", "offset": 1, "limit": 1})
    result = edit.invoke({"path": "f.py", "old_string": "line1", "new_string": "X"})
    assert "has not been read yet" in result.lower()


def test_edit_rejects_stale_file(workspace: Path) -> None:
    (workspace / "f.py").write_text("original")
    read, edit = _tools(workspace)
    read.invoke({"path": "f.py"})
    (workspace / "f.py").write_text("changed externally")
    result = edit.invoke({"path": "f.py", "old_string": "original", "new_string": "new"})
    assert "modified since read" in result.lower()


def test_edit_updates_read_state_so_subsequent_edit_works(workspace: Path) -> None:
    (workspace / "f.py").write_text("a = 1\nb = 2\n")
    read, edit = _tools(workspace)
    read.invoke({"path": "f.py"})
    edit.invoke({"path": "f.py", "old_string": "a = 1", "new_string": "a = 9"})
    # No re-read: second edit should succeed because state was refreshed after first edit
    result = edit.invoke({"path": "f.py", "old_string": "b = 2", "new_string": "b = 9"})
    assert result == "The file 'f.py' has been updated successfully."
    assert (workspace / "f.py").read_text() == "a = 9\nb = 9\n"


# ── guard: same string ─────────────────────────────────────────────────────────

def test_edit_same_string_rejected(workspace: Path) -> None:
    (workspace / "f.py").write_text("hello")
    read, edit = _tools(workspace)
    read.invoke({"path": "f.py"})
    result = edit.invoke({"path": "f.py", "old_string": "hello", "new_string": "hello"})
    assert "no changes to make" in result.lower()


# ── guard: string not found / ambiguous ───────────────────────────────────────

def test_edit_fails_if_old_string_not_found(workspace: Path) -> None:
    (workspace / "f.py").write_text("hello")
    read, edit = _tools(workspace)
    read.invoke({"path": "f.py"})
    result = edit.invoke({"path": "f.py", "old_string": "xyz", "new_string": "abc"})
    assert "not found" in result.lower()
    assert "xyz" in result


def test_edit_fails_if_old_string_not_unique(workspace: Path) -> None:
    (workspace / "dup.py").write_text("x = 1\nx = 1\n")
    read, edit = _tools(workspace)
    read.invoke({"path": "dup.py"})
    result = edit.invoke({"path": "dup.py", "old_string": "x = 1", "new_string": "x = 0"})
    assert "2 matches" in result.lower() or "2 times" in result.lower() or "found 2" in result.lower()
    assert "replace_all" in result.lower()


# ── guard: missing file ────────────────────────────────────────────────────────

def test_edit_missing_file(workspace: Path) -> None:
    tool = build_edit_file_tool(workspace)
    result = tool.invoke({"path": "ghost.py", "old_string": "a", "new_string": "b"})
    assert "does not exist" in result.lower()


# ── create-file path (old_string == "") ───────────────────────────────────────

def test_edit_creates_new_file_with_empty_old_string(workspace: Path) -> None:
    tool = build_edit_file_tool(workspace)
    result = tool.invoke({"path": "new.py", "old_string": "", "new_string": "print('hello')\n"})
    assert "updated successfully" in result.lower()
    assert (workspace / "new.py").read_text() == "print('hello')\n"


def test_edit_rejects_empty_old_string_on_nonempty_existing_file(workspace: Path) -> None:
    (workspace / "existing.py").write_text("has content")
    tool = build_edit_file_tool(workspace)
    result = tool.invoke({"path": "existing.py", "old_string": "", "new_string": "new content"})
    assert "already exists" in result.lower()


def test_edit_allows_empty_old_string_on_empty_existing_file(workspace: Path) -> None:
    (workspace / "empty.py").write_text("")
    tool = build_edit_file_tool(workspace)
    result = tool.invoke({"path": "empty.py", "old_string": "", "new_string": "content\n"})
    assert "updated successfully" in result.lower()
    assert (workspace / "empty.py").read_text() == "content\n"


# ── guard: notebook files ──────────────────────────────────────────────────────

def test_edit_rejects_existing_notebook_file(workspace: Path) -> None:
    (workspace / "demo.ipynb").write_text('{"cells": []}')
    tool = build_edit_file_tool(workspace)
    result = tool.invoke({"path": "demo.ipynb", "old_string": "cells", "new_string": "nodes"})
    assert "jupyter notebook" in result.lower()
    assert "notebook_edit" in result.lower()


def test_edit_allows_creating_new_notebook_with_empty_old_string(workspace: Path) -> None:
    tool = build_edit_file_tool(workspace)
    result = tool.invoke({"path": "new.ipynb", "old_string": "", "new_string": '{"cells": []}'})
    assert "updated successfully" in result.lower()
    assert (workspace / "new.ipynb").exists()


# ── pathing ───────────────────────────────────────────────────────────────────

def test_edit_trims_surrounding_whitespace(workspace: Path) -> None:
    (workspace / "f.py").write_text("x = 1\n")
    read, edit = _tools(workspace)
    read.invoke({"path": "  f.py  "})
    result = edit.invoke({"path": "  f.py  ", "old_string": "x = 1", "new_string": "x = 2"})
    assert "updated successfully" in result.lower()


def test_edit_blocks_path_traversal(workspace: Path) -> None:
    tool = build_edit_file_tool(workspace)
    result = tool.invoke({"path": "../escape.py", "old_string": "a", "new_string": "b"})
    assert "access denied" in result.lower()


# ── permission ────────────────────────────────────────────────────────────────

def test_edit_requires_permission_in_default_mode(workspace: Path) -> None:
    from src.ai.permissions.context import build_default_permission_context
    tool = build_edit_file_tool(workspace, permission_context=build_default_permission_context(workspace))

    def _fake_interrupt(payload):
        return {"approved": False}

    with patch("src.ai.tools.filesystem._shared.interrupt", side_effect=_fake_interrupt):
        result = tool.invoke({"path": "new.py", "old_string": "", "new_string": "hello"})
    assert "permission" in result.lower() or "denied" in result.lower()


def test_edit_protected_ethos_instructions_is_denied(workspace: Path) -> None:
    from src.ai.permissions.context import build_default_permission_context
    from src.ai.permissions.types import PermissionMode

    (workspace / ".ethos").mkdir(parents=True, exist_ok=True)
    (workspace / ".ethos" / "instructions.md").write_text("old", encoding="utf-8")
    tool = build_edit_file_tool(
        workspace,
        permission_context=build_default_permission_context(workspace, mode=PermissionMode.ACCEPT_EDITS),
    )
    result = tool.invoke({"path": ".ethos/instructions.md", "old_string": "old", "new_string": "new"})
    assert "permission denied" in result.lower()
    assert ".ethos" in result.lower()


def test_edit_protected_ethos_skill_is_denied_without_permission_context(workspace: Path) -> None:
    (workspace / ".ethos" / "skills" / "demo").mkdir(parents=True, exist_ok=True)
    (workspace / ".ethos" / "skills" / "demo" / "SKILL.md").write_text("old", encoding="utf-8")
    tool = build_edit_file_tool(workspace)
    result = tool.invoke(
        {"path": ".ethos/skills/demo/SKILL.md", "old_string": "old", "new_string": "new"}
    )
    assert "permission denied" in result.lower()
    assert ".ethos" in result.lower()


# ── sandbox backend ───────────────────────────────────────────────────────────

def test_edit_works_with_sandbox_backend(workspace: Path) -> None:
    backend = _FakeSandbox()
    tools = build_filesystem_tools(root_dir=str(workspace), backend=backend)
    read = next(t for t in tools if t.name == "read_file")
    edit = next(t for t in tools if t.name == "edit_file")

    read.invoke({"path": "src/app.py"})
    result = edit.invoke({"path": "src/app.py", "old_string": "sandbox file", "new_string": "updated"})
    assert "updated successfully" in result.lower()
    assert ("write_bytes", "src/app.py") in [c[:2] for c in backend.calls]
