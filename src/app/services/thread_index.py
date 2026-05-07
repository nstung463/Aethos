"""Per-user index that maps thread ids to project-scoped storage."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from src.app.core.settings import Settings
from src.app.services.storage_paths import StoragePathsService


class ThreadIndex:
    """Small routing index stored under ``~/.ethos/users/<user_id>/threads``."""

    def __init__(self, storage: StoragePathsService | None = None, settings: Settings | None = None) -> None:
        self._storage = storage or StoragePathsService(settings)

    def _index_dir(self, user_id: str) -> Path:
        return self._storage.users_dir() / user_id / "threads"

    def _path(self, *, user_id: str, thread_id: str) -> Path:
        return self._index_dir(user_id) / f"{thread_id}.json"

    def get(self, *, user_id: str, thread_id: str) -> dict[str, Any] | None:
        try:
            raw = json.loads(self._path(user_id=user_id, thread_id=thread_id).read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(raw, dict) or raw.get("thread_id") != thread_id or raw.get("user_id") != user_id:
            return None
        return raw

    def upsert(
        self,
        *,
        user_id: str,
        thread_id: str,
        workspace_root: str | Path | None,
    ) -> dict[str, Any]:
        now = int(time.time())
        existing = self.get(user_id=user_id, thread_id=thread_id) or {}
        root = self._storage.project_identity_root(workspace_root)
        record = {
            "thread_id": thread_id,
            "user_id": user_id,
            "workspace_root": str(Path(workspace_root).expanduser().resolve()) if workspace_root else str(root),
            "canonical_root": str(root),
            "project_key": self._storage.project_key(root),
            "created_at": int(existing.get("created_at") or now),
            "updated_at": now,
        }
        path = self._path(user_id=user_id, thread_id=thread_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(record, indent=2), encoding="utf-8")
        tmp.replace(path)
        return record

    def delete(self, *, user_id: str, thread_id: str) -> None:
        self._path(user_id=user_id, thread_id=thread_id).unlink(missing_ok=True)

    def list(self, *, user_id: str) -> list[dict[str, Any]]:
        root = self._index_dir(user_id)
        if not root.exists():
            return []
        records: list[dict[str, Any]] = []
        for path in root.glob("*.json"):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(raw, dict) and raw.get("user_id") == user_id:
                records.append(raw)
        records.sort(key=lambda item: item.get("updated_at", 0), reverse=True)
        return records
