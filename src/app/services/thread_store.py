"""Per-thread directory storage — one meta.json per thread."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from threading import Lock
from typing import Any


class ThreadStore:
    """
    File layout:
        root/
          <user_id>/
            threads/
              <thread_id>/
                meta.json    # thread metadata + session permission overlay
    """

    def __init__(self, root: Path, legacy_root: Path | None = None) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

        self._user_locks: dict[str, Lock] = {}
        self._users_lock = Lock()

        if legacy_root is not None:
            self._migrate_from_legacy(legacy_root)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _user_lock(self, user_id: str) -> Lock:
        with self._users_lock:
            if user_id not in self._user_locks:
                self._user_locks[user_id] = Lock()
            return self._user_locks[user_id]

    def _thread_dir(self, user_id: str, thread_id: str) -> Path:
        return self.root / user_id / "threads" / thread_id

    def _meta_path(self, user_id: str, thread_id: str) -> Path:
        return self._thread_dir(user_id, thread_id) / "meta.json"

    def _normalize_record(self, data: dict[str, Any]) -> dict[str, Any]:
        now = int(time.time())
        record = dict(data)
        record.setdefault("created_at", now)
        record.setdefault("updated_at", record["created_at"])
        record.setdefault("last_message_at", None)
        record.setdefault("workspace_root", None)
        record.setdefault("backend", None)
        record.setdefault("status", "idle")
        record.setdefault("title", None)
        record.setdefault("summary", None)
        record["permission_overlay"] = self._clean_overlay(record.get("permission_overlay"))
        return record

    def _read_meta(self, user_id: str, thread_id: str) -> dict[str, Any] | None:
        path = self._meta_path(user_id, thread_id)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(raw, dict):
            return None
        return self._normalize_record(raw)

    def _write_meta(self, user_id: str, thread_id: str, data: dict[str, Any]) -> None:
        path = self._meta_path(user_id, thread_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._normalize_record(data), indent=2), encoding="utf-8")

    def _clean_overlay(self, overlay: Any) -> dict[str, Any]:
        if not isinstance(overlay, dict):
            return {"mode": None, "working_directories": [], "rules": []}
        return {
            "mode": overlay.get("mode") if isinstance(overlay.get("mode"), str) else None,
            "working_directories": [
                item for item in (overlay.get("working_directories") or []) if isinstance(item, str)
            ],
            "rules": [
                item for item in (overlay.get("rules") or []) if isinstance(item, dict)
            ],
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_thread(self, *, user_id: str) -> dict[str, Any]:
        now = int(time.time())
        record: dict[str, Any] = {
            "id": f"thread_{uuid.uuid4().hex}",
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
            "last_message_at": None,
            "workspace_root": None,
            "backend": None,
            "status": "idle",
            "title": None,
            "summary": None,
            "permission_overlay": {
                "mode": None,
                "working_directories": [],
                "rules": [],
            },
        }
        with self._user_lock(user_id):
            self._write_meta(user_id, record["id"], record)
        return record

    def update_session_metadata(
        self,
        *,
        thread_id: str,
        user_id: str,
        workspace_root: str | None = None,
        backend: str | None = None,
        status: str | None = None,
        title: str | None = None,
        summary: str | None = None,
        last_message_at: int | None = None,
    ) -> dict[str, Any] | None:
        with self._user_lock(user_id):
            record = self._read_meta(user_id, thread_id)
            if not record or record.get("user_id") != user_id:
                return None
            if workspace_root is not None:
                record["workspace_root"] = workspace_root
            if backend is not None:
                record["backend"] = backend
            if status is not None:
                record["status"] = status
            if title is not None:
                record["title"] = title
            if summary is not None:
                record["summary"] = summary
            if last_message_at is not None:
                record["last_message_at"] = int(last_message_at)
            record["updated_at"] = int(time.time())
            self._write_meta(user_id, thread_id, record)
        return record

    def list_threads(self, *, user_id: str) -> list[dict[str, Any]]:
        threads_root = self.root / user_id / "threads"
        if not threads_root.exists():
            return []
        items: list[dict[str, Any]] = []
        for meta_file in threads_root.glob("*/meta.json"):
            try:
                data = self._normalize_record(json.loads(meta_file.read_text(encoding="utf-8")))
                if data.get("user_id") == user_id:
                    items.append(data)
            except Exception:
                continue
        items.sort(key=lambda item: item.get("updated_at", 0), reverse=True)
        return items

    def get_thread(self, thread_id: str, user_id: str) -> dict[str, Any] | None:
        return self._read_meta(user_id, thread_id)

    def get_owned_thread(self, *, thread_id: str, user_id: str) -> dict[str, Any] | None:
        record = self._read_meta(user_id, thread_id)
        if not record or record.get("user_id") != user_id:
            return None
        return record

    def touch_thread(self, *, thread_id: str, user_id: str) -> dict[str, Any] | None:
        with self._user_lock(user_id):
            record = self._read_meta(user_id, thread_id)
            if not record or record.get("user_id") != user_id:
                return None
            record["updated_at"] = int(time.time())
            self._write_meta(user_id, thread_id, record)
        return record

    def get_permission_overlay(
        self, *, thread_id: str, user_id: str
    ) -> dict[str, Any] | None:
        record = self._read_meta(user_id, thread_id)
        if not record or record.get("user_id") != user_id:
            return None
        return self._clean_overlay(record.get("permission_overlay"))

    def update_permission_overlay(
        self, *, thread_id: str, user_id: str, overlay: dict[str, Any]
    ) -> dict[str, Any] | None:
        with self._user_lock(user_id):
            record = self._read_meta(user_id, thread_id)
            if not record or record.get("user_id") != user_id:
                return None
            record["permission_overlay"] = overlay
            record["updated_at"] = int(time.time())
            self._write_meta(user_id, thread_id, record)
        return overlay

    # ------------------------------------------------------------------
    # Migration from legacy threads.json
    # ------------------------------------------------------------------

    def _migrate_from_legacy(self, legacy_root: Path) -> None:
        legacy_file = legacy_root / "threads.json"
        migrated_flag = legacy_root / "threads.json.migrated"

        if not legacy_file.exists() or migrated_flag.exists():
            return

        try:
            data = json.loads(legacy_file.read_text(encoding="utf-8"))
        except Exception:
            return

        for record in data.values():
            thread_id = str(record.get("id", ""))
            user_id = str(record.get("user_id", ""))
            if not thread_id or not user_id:
                continue
            if self._meta_path(user_id, thread_id).exists():
                continue
            self._write_meta(user_id, thread_id, record)

        migrated_flag.write_text("migrated", encoding="utf-8")
