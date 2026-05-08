from __future__ import annotations

from src.app.core.settings import get_settings
from src.app.services.file_store import FileStore
from src.app.services.memory_store import MemoryStore
from src.app.services.routing_file_store import RoutingFileStore
from src.app.services.routing_thread_store import RoutingThreadStore
from src.app.services.storage_paths import StoragePathsService


def test_routing_thread_store_moves_metadata_to_active_workspace(tmp_path, monkeypatch):
    config_home = tmp_path / "home-aethos"
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / ".git").mkdir()
    monkeypatch.setenv("AETHOS_CONFIG_HOME", str(config_home))
    monkeypatch.delenv("AETHOS_MANAGED_FILES_DIR", raising=False)
    get_settings.cache_clear()

    storage = StoragePathsService()
    store = RoutingThreadStore(storage=storage)
    thread = store.create_thread(user_id="user_1")

    updated = store.update_session_metadata(
        thread_id=thread["id"],
        user_id="user_1",
        workspace_root=str(workspace),
        status="running",
    )

    assert updated is not None
    assert (storage.threads_dir(workspace) / "user_1" / thread["id"] / "meta.json").exists()
    assert not (storage.threads_dir() / "user_1" / thread["id"] / "meta.json").exists()
    assert store.get_owned_thread(thread_id=thread["id"], user_id="user_1")["workspace_root"] == str(workspace.resolve())


def test_routing_file_store_finds_project_scoped_imports(tmp_path, monkeypatch):
    config_home = tmp_path / "home-aethos"
    workspace = tmp_path / "repo"
    workspace.mkdir()
    monkeypatch.setenv("AETHOS_CONFIG_HOME", str(config_home))
    monkeypatch.delenv("AETHOS_MANAGED_FILES_DIR", raising=False)
    get_settings.cache_clear()

    storage = StoragePathsService()
    project_store = FileStore(root=storage.files_dir(workspace))
    record = project_store.import_bytes(
        filename="out.txt",
        content=b"hello",
        content_type="text/plain",
        owner_user_id="user_1",
        thread_id="thread_1",
    )

    routed = RoutingFileStore(storage=storage)

    assert routed.get_file(record["id"], owner_user_id="user_1")["thread_id"] == "thread_1"
    assert [item["id"] for item in routed.list_files(owner_user_id="user_1")] == [record["id"]]


def test_memory_store_appends_to_project_memory(tmp_path, monkeypatch):
    config_home = tmp_path / "home-aethos"
    workspace = tmp_path / "repo"
    workspace.mkdir()
    monkeypatch.setenv("AETHOS_CONFIG_HOME", str(config_home))
    get_settings.cache_clear()

    storage = StoragePathsService()
    memory_store = MemoryStore(storage)
    path = memory_store.append(workspace_root=workspace, memory="Prefer compact review comments.")

    assert path == storage.memory_file(workspace)
    assert "Prefer compact review comments." in path.read_text(encoding="utf-8")
