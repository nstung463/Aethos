"""Project-aware thread storage facade."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from src.app.core.settings import Settings
from src.app.services.storage_paths import StoragePathsService
from src.app.services.thread_index import ThreadIndex
from src.app.services.thread_store import ThreadStore


class ThreadStoreHandle(Protocol):
    """Internal contract for per-project thread stores used by routing."""

    root: Path

    def create_thread(self, *, user_id: str) -> dict[str, Any]: ...

    def upsert_thread(self, *, record: dict[str, Any]) -> dict[str, Any]: ...

    def update_session_metadata(
        self,
        *,
        thread_id: str,
        user_id: str,
        workspace_root: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | None: ...

    def list_threads(self, *, user_id: str) -> list[dict[str, Any]]: ...

    def get_thread(self, thread_id: str, user_id: str) -> dict[str, Any] | None: ...

    def get_owned_thread(self, *, thread_id: str, user_id: str) -> dict[str, Any] | None: ...

    def touch_thread(self, *, thread_id: str, user_id: str) -> dict[str, Any] | None: ...

    def stop_run(self, *, thread_id: str, user_id: str, run_id: str, reason: str) -> dict[str, Any] | None: ...

    def update_thread_metadata(self, *, thread_id: str, user_id: str, **kwargs: Any) -> dict[str, Any] | None: ...

    def delete_thread(self, *, thread_id: str, user_id: str) -> bool: ...

    def get_permission_overlay(self, *, thread_id: str, user_id: str) -> dict[str, Any] | None: ...

    def update_permission_overlay(
        self,
        *,
        thread_id: str,
        user_id: str,
        overlay: dict[str, Any],
    ) -> dict[str, Any] | None: ...


class RoutingThreadStore:
    """Route thread metadata to the project storage selected by workspace_root."""

    def __init__(
        self,
        *,
        storage: StoragePathsService | None = None,
        settings: Settings | None = None,
        legacy_root: Path | None = None,
    ) -> None:
        self._storage = storage or StoragePathsService(settings)
        self._index = ThreadIndex(self._storage)
        self._default_store = ThreadStore(
            root=self._storage.threads_dir(),
            legacy_root=legacy_root,
        )
        self._stores: dict[str, ThreadStoreHandle] = {str(self._default_store.root): self._default_store}

    def _store_for_workspace(self, workspace_root: str | Path | None) -> ThreadStoreHandle:
        root = self._storage.threads_dir(workspace_root)
        key = str(root)
        if key not in self._stores:
            self._storage.ensure_project_metadata(workspace_root)
            self._stores[key] = ThreadStore(root=root)
        return self._stores[key]

    def _store_for_route(self, route: dict[str, Any] | None) -> ThreadStoreHandle:
        if not route:
            return self._default_store
        workspace_root = route.get("workspace_root") or route.get("canonical_root")
        return self._store_for_workspace(str(workspace_root) if workspace_root else None)

    def _find_unindexed_thread(self, *, thread_id: str, user_id: str) -> ThreadStoreHandle | None:
        if self._default_store.get_owned_thread(thread_id=thread_id, user_id=user_id):
            return self._default_store
        projects_root = self._storage.projects_dir()
        if not projects_root.exists():
            return None
        for meta_path in projects_root.glob(f"*/threads/{user_id}/{thread_id}/meta.json"):
            try:
                raw = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(raw, dict) or raw.get("user_id") != user_id:
                continue
            workspace_root = raw.get("workspace_root")
            if isinstance(workspace_root, str) and workspace_root.strip():
                self._index.upsert(user_id=user_id, thread_id=thread_id, workspace_root=workspace_root)
                return self._store_for_workspace(workspace_root)
            return ThreadStore(root=meta_path.parents[2])
        return None

    def _store_for_thread(self, *, thread_id: str, user_id: str) -> ThreadStoreHandle:
        route = self._index.get(user_id=user_id, thread_id=thread_id)
        if route is not None:
            return self._store_for_route(route)
        return self._find_unindexed_thread(thread_id=thread_id, user_id=user_id) or self._default_store

    def _move_to_workspace(
        self,
        *,
        thread_id: str,
        user_id: str,
        workspace_root: str | Path,
    ) -> ThreadStoreHandle:
        target = self._store_for_workspace(workspace_root)
        current = self._store_for_thread(thread_id=thread_id, user_id=user_id)
        if current.root == target.root:
            self._index.upsert(user_id=user_id, thread_id=thread_id, workspace_root=workspace_root)
            return target
        record = current.get_owned_thread(thread_id=thread_id, user_id=user_id)
        if record is None and current.root != self._default_store.root:
            record = self._default_store.get_owned_thread(thread_id=thread_id, user_id=user_id)
            current = self._default_store if record is not None else current
        target_record = target.get_owned_thread(thread_id=thread_id, user_id=user_id)
        if record is not None and target_record is None:
            target.upsert_thread(record=record)
            target_record = record
        if target_record is not None and current.root != target.root:
            current.delete_thread(thread_id=thread_id, user_id=user_id)
        self._index.upsert(user_id=user_id, thread_id=thread_id, workspace_root=workspace_root)
        return target

    def create_thread(self, *, user_id: str) -> dict[str, Any]:
        thread = self._default_store.create_thread(user_id=user_id)
        self._index.upsert(user_id=user_id, thread_id=str(thread["id"]), workspace_root=None)
        return thread

    def update_session_metadata(
        self,
        *,
        thread_id: str,
        user_id: str,
        workspace_root: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        store = (
            self._move_to_workspace(thread_id=thread_id, user_id=user_id, workspace_root=workspace_root)
            if workspace_root
            else self._store_for_thread(thread_id=thread_id, user_id=user_id)
        )
        return store.update_session_metadata(thread_id=thread_id, user_id=user_id, workspace_root=workspace_root, **kwargs)

    def list_threads(self, *, user_id: str) -> list[dict[str, Any]]:
        by_id: dict[str, dict[str, Any]] = {}
        for thread in self._default_store.list_threads(user_id=user_id):
            by_id[str(thread["id"])] = thread
        for route in self._index.list(user_id=user_id):
            thread_id = str(route.get("thread_id") or "")
            if not thread_id:
                continue
            thread = self._store_for_route(route).get_owned_thread(thread_id=thread_id, user_id=user_id)
            if thread:
                by_id[thread_id] = thread
        threads = list(by_id.values())
        threads.sort(key=lambda item: item.get("updated_at", 0), reverse=True)
        return threads

    def get_thread(self, thread_id: str, user_id: str) -> dict[str, Any] | None:
        return self._store_for_thread(thread_id=thread_id, user_id=user_id).get_thread(thread_id, user_id)

    def get_owned_thread(self, *, thread_id: str, user_id: str) -> dict[str, Any] | None:
        return self._store_for_thread(thread_id=thread_id, user_id=user_id).get_owned_thread(thread_id=thread_id, user_id=user_id)

    def touch_thread(self, *, thread_id: str, user_id: str) -> dict[str, Any] | None:
        return self._store_for_thread(thread_id=thread_id, user_id=user_id).touch_thread(thread_id=thread_id, user_id=user_id)

    def stop_run(self, *, thread_id: str, user_id: str, run_id: str, reason: str) -> dict[str, Any] | None:
        return self._store_for_thread(thread_id=thread_id, user_id=user_id).stop_run(thread_id=thread_id, user_id=user_id, run_id=run_id, reason=reason)

    def update_thread_metadata(self, *, thread_id: str, user_id: str, **kwargs: Any) -> dict[str, Any] | None:
        return self._store_for_thread(thread_id=thread_id, user_id=user_id).update_thread_metadata(thread_id=thread_id, user_id=user_id, **kwargs)

    def delete_thread(self, *, thread_id: str, user_id: str) -> bool:
        deleted = self._store_for_thread(thread_id=thread_id, user_id=user_id).delete_thread(thread_id=thread_id, user_id=user_id)
        if deleted:
            self._index.delete(user_id=user_id, thread_id=thread_id)
        return deleted

    def get_permission_overlay(self, *, thread_id: str, user_id: str) -> dict[str, Any] | None:
        return self._store_for_thread(thread_id=thread_id, user_id=user_id).get_permission_overlay(thread_id=thread_id, user_id=user_id)

    def update_permission_overlay(self, *, thread_id: str, user_id: str, overlay: dict[str, Any]) -> dict[str, Any] | None:
        return self._store_for_thread(thread_id=thread_id, user_id=user_id).update_permission_overlay(thread_id=thread_id, user_id=user_id, overlay=overlay)
