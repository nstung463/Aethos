from __future__ import annotations

import json
from pathlib import Path

from src.app.services.settings import (
    SettingsService,
    extract_permission_profile,
    is_protected_aethos_path,
)


def test_get_settings_for_source_normalizes_legacy_permission_profile(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    settings_dir = workspace / ".aethos"
    settings_dir.mkdir(parents=True)
    (settings_dir / "settings.json").write_text(
        json.dumps(
            {
                "mode": "accept_edits",
                "working_directories": ["src"],
                "rules": [{"subject": "edit", "behavior": "allow", "matcher": "src/**"}],
                "mcpServers": {"docs": {"transport": "http", "url": "https://example.com/mcp"}},
            }
        ),
        encoding="utf-8",
    )

    service = SettingsService(
        config_home=tmp_path / "home-aethos",
        managed_settings_dir=tmp_path / "managed-settings",
    )
    loaded = service.get_settings_for_source("project", workspace_root=workspace)

    assert loaded["permissions"] == {
        "mode": "accept_edits",
        "workingDirectories": ["src"],
        "rules": [{"subject": "edit", "behavior": "allow", "matcher": "src/**"}],
    }
    assert loaded["mcpServers"]["docs"]["url"] == "https://example.com/mcp"


def test_get_effective_settings_merges_user_project_local_and_managed(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / ".aethos").mkdir(parents=True)
    home = tmp_path / "home-aethos"
    home.mkdir()
    managed = tmp_path / "managed-settings"
    (managed / "managed-settings.d").mkdir(parents=True)

    (home / "settings.json").write_text(
        json.dumps({"mcpServers": {"user": {"transport": "http", "url": "https://user.example.com"}}}),
        encoding="utf-8",
    )
    (workspace / ".aethos" / "settings.json").write_text(
        json.dumps({"mcpServers": {"project": {"transport": "http", "url": "https://project.example.com"}}}),
        encoding="utf-8",
    )
    (workspace / ".aethos" / "settings.local.json").write_text(
        json.dumps({"mcpServers": {"project": {"transport": "http", "url": "https://local.example.com"}}}),
        encoding="utf-8",
    )
    (managed / "managed-settings.json").write_text(
        json.dumps({"mcpServers": {"managed": {"transport": "http", "url": "https://managed.example.com"}}}),
        encoding="utf-8",
    )

    service = SettingsService(config_home=home, managed_settings_dir=managed)
    effective = service.get_effective_settings(workspace_root=workspace)

    assert effective["mcpServers"] == {
        "user": {"transport": "http", "url": "https://user.example.com"},
        "project": {"transport": "http", "url": "https://local.example.com"},
        "managed": {"transport": "http", "url": "https://managed.example.com"},
    }


def test_load_managed_settings_merges_drop_ins_in_alphabetic_order(tmp_path: Path) -> None:
    managed = tmp_path / "managed-settings"
    drop_ins = managed / "managed-settings.d"
    drop_ins.mkdir(parents=True)
    (managed / "managed-settings.json").write_text(
        json.dumps({"permissions": {"mode": "accept_edits"}}),
        encoding="utf-8",
    )
    (drop_ins / "10-base.json").write_text(
        json.dumps({"permissions": {"workingDirectories": ["src"]}}),
        encoding="utf-8",
    )
    (drop_ins / "20-override.json").write_text(
        json.dumps({"permissions": {"mode": "dont_ask"}}),
        encoding="utf-8",
    )

    service = SettingsService(config_home=tmp_path / "home-aethos", managed_settings_dir=managed)
    managed_settings = service.load_managed_settings()

    assert managed_settings["permissions"]["mode"] == "dont_ask"
    assert managed_settings["permissions"]["workingDirectories"] == ["src"]


def test_update_settings_for_source_writes_unified_schema(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    service = SettingsService(
        config_home=tmp_path / "home-aethos",
        managed_settings_dir=tmp_path / "managed-settings",
    )

    service.update_settings_for_source(
        "project",
        {
            "permissions": {
                "mode": "accept_edits",
                "working_directories": ["src"],
                "rules": [{"subject": "read", "behavior": "allow", "matcher": "src/**"}],
            }
        },
        workspace_root=workspace,
    )

    data = json.loads((workspace / ".aethos" / "settings.json").read_text(encoding="utf-8"))
    assert data == {
        "permissions": {
            "mode": "accept_edits",
            "workingDirectories": ["src"],
            "rules": [{"subject": "read", "behavior": "allow", "matcher": "src/**"}],
        }
    }


def test_extract_permission_profile_reads_unified_permissions_shape() -> None:
    settings_data = {
        "permissions": {
            "mode": "accept_edits",
            "workingDirectories": ["src"],
            "rules": [{"subject": "edit", "behavior": "allow", "matcher": "src/**"}],
        }
    }

    assert extract_permission_profile(settings_data) == {
        "mode": "accept_edits",
        "working_directories": ["src"],
        "rules": [{"subject": "edit", "behavior": "allow", "matcher": "src/**"}],
    }


def test_is_protected_aethos_path_matches_settings_and_skill_paths(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    assert is_protected_aethos_path(workspace, workspace / ".aethos" / "settings.json") is True
    assert is_protected_aethos_path(workspace, workspace / ".aethos" / "skills" / "demo" / "SKILL.md") is True
    assert is_protected_aethos_path(workspace, workspace / "src" / "app.py") is False

