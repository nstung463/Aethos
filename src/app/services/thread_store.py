"""File-backed thread metadata store for project-scoped thread state."""

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

    def _user_lock(self, user_id: str) -> Lock:
        with self._users_lock:
            if user_id not in self._user_locks:
                self._user_locks[user_id] = Lock()
            return self._user_locks[user_id]

    def _thread_dir(self, user_id: str, thread_id: str) -> Path:
        return self.root / user_id / thread_id

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
        record.setdefault("active_run_id", None)
        record.setdefault("run_started_at", None)
        record.setdefault("last_stop_run_id", None)
        record.setdefault("last_stop_reason", None)
        record.setdefault("last_interrupted_at", None)
        record.setdefault("title", None)
        record.setdefault("summary", None)
        record.setdefault("model", None)
        record.setdefault("mode", None)
        record.setdefault("profile_id", None)
        record.setdefault("project", None)
        record.setdefault("is_favorite", False)
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
            "model": None,
            "mode": None,
            "profile_id": None,
            "project": None,
            "is_favorite": False,
            "permission_overlay": {
                "mode": None,
                "working_directories": [],
                "rules": [],
            },
        }
        with self._user_lock(user_id):
            self._write_meta(user_id, record["id"], record)
        return record

    def upsert_thread(self, *, record: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_record(record)
        thread_id = str(normalized.get("id") or "")
        user_id = str(normalized.get("user_id") or "")
        if not thread_id or not user_id:
            raise ValueError("Thread record must include id and user_id")
        with self._user_lock(user_id):
            self._write_meta(user_id, thread_id, normalized)
        return normalized

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
        active_run_id: str | None = None,
        run_started_at: int | None = None,
        last_stop_reason: str | None = None,
        last_interrupted_at: int | None = None,
        clear_active_run: bool = False,
        clear_stop_reason: bool = False,
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
            if active_run_id is not None:
                record["active_run_id"] = active_run_id
            if run_started_at is not None:
                record["run_started_at"] = int(run_started_at)
            if last_stop_reason is not None:
                record["last_stop_reason"] = last_stop_reason
            if last_interrupted_at is not None:
                record["last_interrupted_at"] = int(last_interrupted_at)
            if clear_active_run:
                record["active_run_id"] = None
                record["run_started_at"] = None
            if clear_stop_reason:
                record["last_stop_run_id"] = None
                record["last_stop_reason"] = None
                record["last_interrupted_at"] = None
            record["updated_at"] = int(time.time())
            self._write_meta(user_id, thread_id, record)
        return record

    def stop_run(
        self,
        *,
        thread_id: str,
        user_id: str,
        run_id: str,
        reason: str,
    ) -> dict[str, Any] | None:
        with self._user_lock(user_id):
            record = self._read_meta(user_id, thread_id)
            if not record or record.get("user_id") != user_id:
                return None
            active_run_id = record.get("active_run_id")
            already_stopped = active_run_id is None and record.get("last_stop_run_id") == run_id
            if active_run_id != run_id and not already_stopped:
                return None
            now = int(time.time())
            record["status"] = "interrupted"
            record["active_run_id"] = None
            record["run_started_at"] = None
            record["last_stop_run_id"] = run_id
            current_reason = record.get("last_stop_reason")
            record["last_stop_reason"] = "user_cancel" if "user_cancel" in {current_reason, reason} else reason
            record["last_interrupted_at"] = now
            record["updated_at"] = now
            self._write_meta(user_id, thread_id, record)
        return record

    def update_thread_metadata(
        self,
        *,
        thread_id: str,
        user_id: str,
        title: str | None = None,
        summary: str | None = None,
        model: str | None = None,
        mode: str | None = None,
        profile_id: str | None = None,
        project: str | None = None,
        is_favorite: bool | None = None,
    ) -> dict[str, Any] | None:
        with self._user_lock(user_id):
            record = self._read_meta(user_id, thread_id)
            if not record or record.get("user_id") != user_id:
                return None
            if title is not None:
                record["title"] = title
            if summary is not None:
                record["summary"] = summary
            if model is not None:
                record["model"] = model
            if mode is not None:
                record["mode"] = mode
            if profile_id is not None:
                record["profile_id"] = profile_id
            if project is not None:
                record["project"] = project
            if is_favorite is not None:
                record["is_favorite"] = bool(is_favorite)
            record["updated_at"] = int(time.time())
            self._write_meta(user_id, thread_id, record)
        return record

    def delete_thread(self, *, thread_id: str, user_id: str) -> bool:
        with self._user_lock(user_id):
            record = self._read_meta(user_id, thread_id)
            if not record or record.get("user_id") != user_id:
                return False
            thread_dir = self._thread_dir(user_id, thread_id)
            for path in sorted(thread_dir.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            if thread_dir.exists():
                thread_dir.rmdir()
        return True

    def list_threads(self, *, user_id: str) -> list[dict[str, Any]]:
        threads_root = self.root / user_id
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

    def get_permission_overlay(self, *, thread_id: str, user_id: str) -> dict[str, Any] | None:
        record = self._read_meta(user_id, thread_id)
        if not record or record.get("user_id") != user_id:
            return None
        return self._clean_overlay(record.get("permission_overlay"))

    def update_permission_overlay(self, *, thread_id: str, user_id: str, overlay: dict[str, Any]) -> dict[str, Any] | None:
        with self._user_lock(user_id):
            record = self._read_meta(user_id, thread_id)
            if not record or record.get("user_id") != user_id:
                return None
            record["permission_overlay"] = overlay
            record["updated_at"] = int(time.time())
            self._write_meta(user_id, thread_id, record)
        return overlay

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
