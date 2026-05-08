from __future__ import annotations

from pathlib import Path

import pytest

from src.ai.permissions.context import build_default_permission_context
from src.ai.permissions.filesystem_policy import FilesystemPolicy
from src.ai.permissions.types import PermissionBehavior, PermissionContext, PermissionMode


def test_read_inside_workspace_is_allowed_in_default_mode(tmp_path):
    context = build_default_permission_context(workspace_root=tmp_path)
    policy = FilesystemPolicy()
    target = tmp_path / "file.txt"
    decision = policy.check_read(context=context, target=target)
    assert decision.behavior is PermissionBehavior.ALLOW


def test_read_outside_workspace_asks(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    context = build_default_permission_context(workspace_root=workspace)
    policy = FilesystemPolicy()
    # A path inside workspace root but outside working_directories would ask,
    # but since build_default sets working_directories = (root,), we need a
    # subdirectory that is inside workspace but outside a restricted working dir.
    # Instead, create a context with a narrower working directory.
    subdir = workspace / "subdir"
    subdir.mkdir()
    narrow_context = PermissionContext(
        mode=PermissionMode.DEFAULT,
        workspace_root=workspace.resolve(),
        working_directories=(subdir.resolve(),),
    )
    other_dir = workspace / "other"
    other_dir.mkdir()
    target = other_dir / "file.txt"
    decision = policy.check_read(context=narrow_context, target=target)
    assert decision.behavior is PermissionBehavior.ASK


def test_read_path_traversal_is_denied(tmp_path):
    context = build_default_permission_context(workspace_root=tmp_path)
    policy = FilesystemPolicy()
    outside = tmp_path.parent / "secret.txt"
    decision = policy.check_read(context=context, target=outside)
    assert decision.behavior is PermissionBehavior.DENY
    assert "workspace" in decision.reason.lower()


def test_edit_inside_workspace_asks_in_default_mode(tmp_path):
    context = build_default_permission_context(workspace_root=tmp_path)
    policy = FilesystemPolicy()
    target = tmp_path / "file.txt"
    decision = policy.check_edit(context=context, target=target)
    assert decision.behavior is PermissionBehavior.ASK


def test_edit_inside_workspace_is_allowed_in_accept_edits_mode(tmp_path):
    context = build_default_permission_context(
        workspace_root=tmp_path, mode=PermissionMode.ACCEPT_EDITS
    )
    policy = FilesystemPolicy()
    target = tmp_path / "file.txt"
    decision = policy.check_edit(context=context, target=target)
    assert decision.behavior is PermissionBehavior.ALLOW


def test_edit_inside_workspace_is_allowed_in_bypass_permissions_mode(tmp_path):
    context = build_default_permission_context(
        workspace_root=tmp_path, mode=PermissionMode.BYPASS_PERMISSIONS
    )
    policy = FilesystemPolicy()
    target = tmp_path / "file.txt"
    decision = policy.check_edit(context=context, target=target)
    assert decision.behavior is PermissionBehavior.ALLOW


def test_edit_path_traversal_is_denied(tmp_path):
    context = build_default_permission_context(workspace_root=tmp_path)
    policy = FilesystemPolicy()
    outside = tmp_path.parent / "secret.txt"
    decision = policy.check_edit(context=context, target=outside)
    assert decision.behavior is PermissionBehavior.DENY
    assert "workspace" in decision.reason.lower()


def test_edit_protected_aethos_settings_is_denied_even_in_accept_edits_mode(tmp_path):
    context = build_default_permission_context(
        workspace_root=tmp_path,
        mode=PermissionMode.ACCEPT_EDITS,
    )
    policy = FilesystemPolicy()
    target = tmp_path / ".aethos" / "settings.json"
    decision = policy.check_edit(context=context, target=target)
    assert decision.behavior is PermissionBehavior.DENY
    assert ".aethos" in decision.reason.lower()


def test_edit_protected_aethos_settings_is_denied_even_in_bypass_permissions_mode(tmp_path):
    context = build_default_permission_context(
        workspace_root=tmp_path,
        mode=PermissionMode.BYPASS_PERMISSIONS,
    )
    policy = FilesystemPolicy()
    target = tmp_path / ".aethos" / "settings.local.json"
    decision = policy.check_edit(context=context, target=target)
    assert decision.behavior is PermissionBehavior.DENY
    assert ".aethos" in decision.reason.lower()


def test_edit_protected_aethos_skill_is_denied(tmp_path):
    context = build_default_permission_context(
        workspace_root=tmp_path,
        mode=PermissionMode.ACCEPT_EDITS,
    )
    policy = FilesystemPolicy()
    target = tmp_path / ".aethos" / "skills" / "python" / "SKILL.md"
    decision = policy.check_edit(context=context, target=target)
    assert decision.behavior is PermissionBehavior.DENY
    assert ".aethos" in decision.reason.lower()


def test_read_protected_aethos_settings_is_still_allowed_inside_workspace(tmp_path):
    context = build_default_permission_context(workspace_root=tmp_path)
    policy = FilesystemPolicy()
    target = tmp_path / ".aethos" / "settings.json"
    decision = policy.check_read(context=context, target=target)
    assert decision.behavior is PermissionBehavior.ALLOW
