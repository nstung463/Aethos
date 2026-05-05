from __future__ import annotations

import json
import mimetypes
import shutil
import time
import uuid
from pathlib import Path
from threading import Lock
from typing import Any


class FileStore:
    """Small local file registry for OpenWebUI-compatible managed files."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.index_path = self.root / "index.json"
        self._lock = Lock()
        self.root.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self.index_path.write_text("{}", encoding="utf-8")

    def _user_blobs_dir(self, owner_user_id: str) -> Path:
        return self.root / owner_user_id / "blobs"

    def _read_index(self) -> dict[str, dict[str, Any]]:
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_index(self, index: dict[str, dict[str, Any]]) -> None:
        self.index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")

    def list_files(self, *, owner_user_id: str) -> list[dict[str, Any]]:
        with self._lock:
            index = self._read_index()
        items = [item for item in index.values() if item.get("owner_user_id") == owner_user_id]
        items.sort(key=lambda item: item.get("updated_at", 0), reverse=True)
        return items

    def total_usage_bytes(self, *, owner_user_id: str) -> int:
        return sum(int(item.get("meta", {}).get("size", 0)) for item in self.list_files(owner_user_id=owner_user_id))

    def get_file(self, file_id: str, *, owner_user_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._read_index().get(file_id)
        if not record or record.get("owner_user_id") != owner_user_id:
            return None
        return record

    def save_upload(
        self,
        *,
        filename: str,
        content_type: str | None,
        source_path: Path,
        owner_user_id: str,
    ) -> dict[str, Any]:
        file_id = str(uuid.uuid4())
        stored_name = f"{file_id}_{filename}"
        destination = self._user_blobs_dir(owner_user_id) / stored_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)
        return self._register_file(
            file_id=file_id,
            filename=filename,
            stored_path=destination,
            content_type=content_type,
            owner_user_id=owner_user_id,
        )

    def import_bytes(
        self,
        *,
        filename: str,
        content: bytes,
        content_type: str | None = None,
        owner_user_id: str,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        file_id = str(uuid.uuid4())
        stored_name = f"{file_id}_{filename}"
        destination = self._user_blobs_dir(owner_user_id) / stored_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        return self._register_file(
            file_id=file_id,
            filename=filename,
            stored_path=destination,
            content_type=content_type,
            owner_user_id=owner_user_id,
            thread_id=thread_id,
        )

    def _register_file(
        self,
        *,
        file_id: str,
        filename: str,
        stored_path: Path,
        content_type: str | None,
        owner_user_id: str,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        now = int(time.time())
        resolved_type = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        record = {
            "id": file_id,
            "filename": filename,
            "path": str(stored_path),
            "owner_user_id": owner_user_id,
            "thread_id": thread_id,
            "meta": {
                "name": filename,
                "content_type": resolved_type,
                "size": stored_path.stat().st_size,
            },
            "data": {},
            "created_at": now,
            "updated_at": now,
        }
        with self._lock:
            index = self._read_index()
            index[file_id] = record
            self._write_index(index)
        return record

    def update_content(self, file_id: str, content: str, *, owner_user_id: str) -> dict[str, Any] | None:
        with self._lock:
            index = self._read_index()
            record = index.get(file_id)
            if not record or record.get("owner_user_id") != owner_user_id:
                return None
            path = Path(record["path"])
            path.write_text(content, encoding="utf-8")
            record["meta"]["size"] = path.stat().st_size
            record["updated_at"] = int(time.time())
            index[file_id] = record
            self._write_index(index)
            return record

    def delete_file(self, file_id: str, *, owner_user_id: str) -> bool:
        with self._lock:
            index = self._read_index()
            record = index.pop(file_id, None)
            if not record or record.get("owner_user_id") != owner_user_id:
                if record is not None:
                    index[file_id] = record
                return False
            self._write_index(index)
        try:
            Path(record["path"]).unlink(missing_ok=True)
        except Exception:
            pass
        return True
