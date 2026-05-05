# tests/tools/filesystem/test_write_file.py
"""Tests for write_file tool."""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import patch

from src.ai.tools.filesystem import build_filesystem_tools
from src.ai.tools.filesystem.write_file import build_write_file_tool


def test_write_creates_new_file(workspace: Path) -> None:
    tool = build_write_file_tool(workspace)
    tool.invoke({"path": "new.txt", "content": "hello"})
    assert (workspace / "new.txt").read_text() == "hello"


def test_write_creates_parent_dirs(workspace: Path) -> None:
    tool = build_write_file_tool(workspace)
    tool.invoke({"path": "a/b/c.txt", "content": "deep"})
    assert (workspace / "a" / "b" / "c.txt").exists()


def test_write_overwrites_existing(workspace: Path) -> None:
    (workspace / "f.txt").write_text("old")
    tools = build_filesystem_tools(root_dir=str(workspace))
    read_tool = next(item for item in tools if item.name == "read_file")
    write_tool = next(item for item in tools if item.name == "write_file")

    read_tool.invoke({"path": "f.txt"})
    write_tool.invoke({"path": "f.txt", "content": "new"})

    assert (workspace / "f.txt").read_text() == "new"


def test_write_existing_file_requires_full_read_first(workspace: Path) -> None:
    (workspace / "f.txt").write_text("old")
    tool = build_write_file_tool(workspace)

    result = tool.invoke({"path": "f.txt", "content": "new"})

    assert "read it first before writing to it" in result.lower()


def test_write_existing_file_rejects_partial_read(workspace: Path) -> None:
    (workspace / "f.txt").write_text("old\nline2\nline3")
    tools = build_filesystem_tools(root_dir=str(workspace))
    read_tool = next(item for item in tools if item.name == "read_file")
    write_tool = next(item for item in tools if item.name == "write_file")

    read_tool.invoke({"path": "f.txt", "offset": 1, "limit": 1})
    result = write_tool.invoke({"path": "f.txt", "content": "new"})

    assert "read it first before writing to it" in result.lower()


def test_write_existing_file_allows_full_read_first(workspace: Path) -> None:
    (workspace / "f.txt").write_text("old")
    tools = build_filesystem_tools(root_dir=str(workspace))
    read_tool = next(item for item in tools if item.name == "read_file")
    write_tool = next(item for item in tools if item.name == "write_file")

    read_tool.invoke({"path": "f.txt"})
    result = write_tool.invoke({"path": "f.txt", "content": "new"})

    assert "written" in result.lower()
    assert (workspace / "f.txt").read_text() == "new"


def test_write_existing_file_rejects_stale_read(workspace: Path) -> None:
    (workspace / "f.txt").write_text("old")
    tools = build_filesystem_tools(root_dir=str(workspace))
    read_tool = next(item for item in tools if item.name == "read_file")
    write_tool = next(item for item in tools if item.name == "write_file")

    read_tool.invoke({"path": "f.txt"})
    (workspace / "f.txt").write_text("changed by user")
    result = write_tool.invoke({"path": "f.txt", "content": "new"})

    assert "modified since read" in result.lower()
    assert "read it again" in result.lower()


def test_write_reports_line_count(workspace: Path) -> None:
    tool = build_write_file_tool(workspace)
    result = tool.invoke({"path": "lines.txt", "content": "a\nb\nc"})
    assert "3 lines" in result


def test_write_rejects_traversal(workspace: Path) -> None:
    tool = build_write_file_tool(workspace)
    result = tool.invoke({"path": "../escape.txt", "content": "bad"})
    assert "access denied" in result.lower()



def test_write_requires_permission_in_default_mode(workspace: Path) -> None:
    from src.ai.permissions.context import build_default_permission_context
    tool = build_write_file_tool(workspace, permission_context=build_default_permission_context(workspace))

    def _fake_interrupt(payload):
        return {"approved": False}

    with patch("src.ai.tools.filesystem._shared.interrupt", side_effect=_fake_interrupt):
        result = tool.invoke({"path": "blocked.txt", "content": "hello"})
    assert "permission" in result.lower()
    assert "denied" in result.lower()


def test_write_allowed_in_accept_edits_mode(workspace: Path) -> None:
    from src.ai.permissions.context import build_default_permission_context
    from src.ai.permissions.types import PermissionMode
    tool = build_write_file_tool(workspace, permission_context=build_default_permission_context(workspace, mode=PermissionMode.ACCEPT_EDITS))
    result = tool.invoke({"path": "ok.txt", "content": "hello"})
    assert "written" in result.lower()


def test_write_protected_ethos_settings_is_denied_without_permission_context(workspace: Path) -> None:
    tool = build_write_file_tool(workspace)
    result = tool.invoke({"path": ".ethos/settings.json", "content": "{}"})
    assert "permission denied" in result.lower()
    assert ".ethos" in result.lower()


def test_write_protected_ethos_settings_is_denied_in_accept_edits_mode(workspace: Path) -> None:
    from src.ai.permissions.context import build_default_permission_context
    from src.ai.permissions.types import PermissionMode

    tool = build_write_file_tool(
        workspace,
        permission_context=build_default_permission_context(workspace, mode=PermissionMode.ACCEPT_EDITS),
    )
    result = tool.invoke({"path": ".ethos/settings.json", "content": "{}"})
    assert "permission denied" in result.lower()
    assert ".ethos" in result.lower()


def test_write_file_calls_interrupt_not_string_on_ask(workspace: Path) -> None:
    """In default mode, write_file must call interrupt() — not return a permission string."""
    from src.ai.permissions.context import build_default_permission_context
    from src.ai.tools.filesystem.write_file import build_write_file_tool

    ctx = build_default_permission_context(workspace_root=workspace)
    tool = build_write_file_tool(workspace, permission_context=ctx)

    interrupted_payloads: list[dict] = []

    def _fake_interrupt(payload):
        interrupted_payloads.append(payload)
        return {"approved": False}  # simulate user denying

    with patch("src.ai.tools.filesystem._shared.interrupt", side_effect=_fake_interrupt):
        result = tool.invoke({"path": "new.txt", "content": "hello"})

    assert len(interrupted_payloads) == 1
    assert interrupted_payloads[0]["behavior"] == "ask"
    assert interrupted_payloads[0]["subject"] == "edit"
    assert interrupted_payloads[0]["path"] == "new.txt"
    assert "suggested_mode" in interrupted_payloads[0]
    assert "suggestions" in interrupted_payloads[0]
    assert interrupted_payloads[0]["approval_options"] == [
        {"id": "once", "label": "Approve once"},
        {"id": "thread_file", "label": "Allow this file in this thread"},
        {"id": "user_file", "label": "Always allow this file"},
    ]
    assert "denied" in result.lower()


def test_write_file_proceeds_after_interrupt_approval(workspace: Path) -> None:
    """If user approves via interrupt resume, write_file must write the file."""
    from src.ai.permissions.context import build_default_permission_context
    from src.ai.tools.filesystem.write_file import build_write_file_tool

    ctx = build_default_permission_context(workspace_root=workspace)
    tool = build_write_file_tool(workspace, permission_context=ctx)

    def _fake_interrupt(payload):
        return {"approved": True}

    with patch("src.ai.tools.filesystem._shared.interrupt", side_effect=_fake_interrupt):
        result = tool.invoke({"path": "approved.txt", "content": "hello"})

    assert (workspace / "approved.txt").exists()
