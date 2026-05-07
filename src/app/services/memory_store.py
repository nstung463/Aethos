"""Auto-managed Ethos memory storage."""

from __future__ import annotations

import time
from pathlib import Path

from src.app.core.settings import Settings
from src.app.services.storage_paths import StoragePathsService


class MemoryStore:
    """Append-only project memory stored outside the source tree."""

    def __init__(self, storage: StoragePathsService | None = None, settings: Settings | None = None) -> None:
        self._storage = storage or StoragePathsService(settings)

    def memory_path(self, workspace_root: str | Path | None) -> Path:
        return self._storage.memory_file(workspace_root)

    def read(self, *, workspace_root: str | Path | None) -> str:
        path = self.memory_path(workspace_root)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def append(self, *, workspace_root: str | Path | None, memory: str) -> Path:
        content = memory.strip()
        if not content:
            raise ValueError("Memory content cannot be empty")
        path = self.memory_path(workspace_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        prefix = "\n\n" if path.exists() and path.read_text(encoding="utf-8").strip() else ""
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{prefix}- {timestamp}: {content}\n")
        return path
