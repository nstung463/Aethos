from __future__ import annotations

import os
from pathlib import Path

from src.app.core.settings import get_settings
from src.app.services.storage_paths import StoragePathsService, sanitize_project_key


def test_storage_paths_default_to_config_home(tmp_path, monkeypatch):
    config_home = tmp_path / "home-ethos"
    monkeypatch.setenv("ETHOS_CONFIG_HOME", str(config_home))
    monkeypatch.delenv("ETHOS_USERS_DIR", raising=False)
    monkeypatch.delenv("ETHOS_SECURITY_STATE_DIR", raising=False)
    monkeypatch.delenv("ETHOS_CHECKPOINTS_DIR", raising=False)
    monkeypatch.delenv("ETHOS_MANAGED_FILES_DIR", raising=False)
    get_settings.cache_clear()

    service = StoragePathsService()
    workspace = tmp_path / "repo"
    workspace.mkdir()

    assert service.users_dir() == config_home / "users"
    assert service.security_state_dir() == config_home / "security"
    assert service.project_dir(workspace).parent == config_home / "projects"
    assert service.threads_dir(workspace) == service.project_dir(workspace) / "threads"
    assert service.checkpoints_dir(workspace) == service.project_dir(workspace) / "checkpoints"
    assert service.files_dir(workspace) == service.project_dir(workspace) / "files"
    assert service.memory_file(workspace) == service.project_dir(workspace) / "memory" / "MEMORY.md"


def test_project_key_uses_canonical_git_root(tmp_path, monkeypatch):
    monkeypatch.setenv("ETHOS_CONFIG_HOME", str(tmp_path / "home-ethos"))
    get_settings.cache_clear()
    repo = tmp_path / "repo"
    nested = repo / "packages" / "app"
    nested.mkdir(parents=True)
    (repo / ".git").mkdir()

    service = StoragePathsService()

    assert service.project_identity_root(nested) == repo.resolve()
    assert service.project_key(nested) == sanitize_project_key(repo)


def test_project_key_is_case_stable_on_windows(tmp_path):
    first = sanitize_project_key(tmp_path / "Repo")
    second = sanitize_project_key(tmp_path / "Repo")
    assert first == second
    if os.name == "nt":
        assert first == sanitize_project_key(tmp_path / "repo")


def test_migrate_legacy_workspace_copies_without_overwrite(tmp_path, monkeypatch):
    config_home = tmp_path / "home-ethos"
    workspace = tmp_path / "workspace"
    legacy_user = workspace / "users" / "user_1" / "profile.json"
    legacy_checkpoint = workspace / "checkpoints" / "thread_1" / "messages.jsonl"
    legacy_file = workspace / "managed_files" / "index.json"
    legacy_security = workspace / "security" / "auth.json"
    legacy_thread = workspace / "users" / "user_1" / "threads" / "thread_1" / "meta.json"
    legacy_user.parent.mkdir(parents=True)
    legacy_checkpoint.parent.mkdir(parents=True)
    legacy_file.parent.mkdir(parents=True)
    legacy_security.parent.mkdir(parents=True)
    legacy_thread.parent.mkdir(parents=True)
    legacy_user.write_text('{"id":"legacy"}', encoding="utf-8")
    legacy_checkpoint.write_text("{}\n", encoding="utf-8")
    legacy_file.write_text('{"legacy":true}', encoding="utf-8")
    legacy_security.write_text('{"sessions":{}}', encoding="utf-8")
    legacy_thread.write_text('{"id":"thread_1","user_id":"user_1"}', encoding="utf-8")

    monkeypatch.setenv("ETHOS_CONFIG_HOME", str(config_home))
    monkeypatch.delenv("ETHOS_USERS_DIR", raising=False)
    monkeypatch.delenv("ETHOS_SECURITY_STATE_DIR", raising=False)
    monkeypatch.delenv("ETHOS_CHECKPOINTS_DIR", raising=False)
    monkeypatch.delenv("ETHOS_MANAGED_FILES_DIR", raising=False)
    get_settings.cache_clear()

    service = StoragePathsService()
    service.migrate_legacy_workspace(workspace)
    (service.users_dir() / "user_1" / "profile.json").write_text('{"id":"new"}', encoding="utf-8")
    service.migrate_legacy_workspace(workspace)

    assert (service.users_dir() / "user_1" / "profile.json").read_text(encoding="utf-8") == '{"id":"new"}'
    assert (service.checkpoints_dir(workspace) / "thread_1" / "messages.jsonl").exists()
    assert (service.files_dir(workspace) / "index.json").exists()
    assert (service.security_state_dir() / "auth.json").exists()
    assert (service.threads_dir(workspace) / "user_1" / "thread_1" / "meta.json").exists()
