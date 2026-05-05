"""Project-aware file store facade."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.app.core.settings import Settings
from src.app.services.file_store import FileStore
from src.app.services.storage_paths import StoragePathsService


class RoutingFileStore:
    """Aggregate default and project-scoped managed files."""

    def __init__(self, *, storage: StoragePathsService | None = None, settings: Settings | None = None) -> None:
        self._storage = storage or StoragePathsService(settings)
        self._default_store = FileStore(root=self._storage.files_dir())
        self._stores: dict[str, FileStore] = {str(self._default_store.root): self._default_store}

    def _store_for_root(self, root: Path) -> FileStore:
        key = str(root)
        if key not in self._stores:
            self._stores[key] = FileStore(root=root)
        return self._stores[key]

    def _project_file_roots(self) -> list[Path]:
        projects_root = self._storage.projects_dir()
        if not projects_root.exists():
            return []
        return [path for path in projects_root.glob("*/files") if path.is_dir()]

    def _candidate_stores(self) -> list[FileStore]:
        stores = [self._default_store]
        for root in self._project_file_roots():
            store = self._store_for_root(root)
            if store.root != self._default_store.root:
                stores.append(store)
        return stores

    def _store_for_file(self, *, file_id: str, owner_user_id: str) -> FileStore | None:
        for store in self._candidate_stores():
            if store.get_file(file_id, owner_user_id=owner_user_id):
                return store
        return None

    def list_files(self, *, owner_user_id: str) -> list[dict[str, Any]]:
        by_id: dict[str, dict[str, Any]] = {}
        for store in self._candidate_stores():
            for item in store.list_files(owner_user_id=owner_user_id):
                by_id[str(item.get("id"))] = item
        items = list(by_id.values())
        items.sort(key=lambda item: item.get("updated_at", 0), reverse=True)
        return items

    def total_usage_bytes(self, *, owner_user_id: str) -> int:
        return sum(int(item.get("meta", {}).get("size", 0)) for item in self.list_files(owner_user_id=owner_user_id))

    def get_file(self, file_id: str, *, owner_user_id: str) -> dict[str, Any] | None:
        store = self._store_for_file(file_id=file_id, owner_user_id=owner_user_id)
        if store is None:
            return None
        return store.get_file(file_id, owner_user_id=owner_user_id)

    def save_upload(self, **kwargs: Any) -> dict[str, Any]:
        return self._default_store.save_upload(**kwargs)

    def import_bytes(self, **kwargs: Any) -> dict[str, Any]:
        return self._default_store.import_bytes(**kwargs)

    def update_content(self, file_id: str, content: str, *, owner_user_id: str) -> dict[str, Any] | None:
        store = self._store_for_file(file_id=file_id, owner_user_id=owner_user_id)
        if store is None:
            return None
        return store.update_content(file_id, content, owner_user_id=owner_user_id)

    def delete_file(self, file_id: str, *, owner_user_id: str) -> bool:
        store = self._store_for_file(file_id=file_id, owner_user_id=owner_user_id)
        if store is None:
            return False
        return store.delete_file(file_id, owner_user_id=owner_user_id)
