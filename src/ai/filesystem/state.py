from __future__ import annotations

import hashlib
from dataclasses import dataclass

from src.ai.filesystem.backend import FilesystemBackendAdapter
from src.ai.filesystem.pathing import WorkspacePathResolver


@dataclass(frozen=True)
class FileReadState:
    path: str
    is_full_read: bool
    content_hash: str | None = None


class ReadStateStore:
    def __init__(self, resolver: WorkspacePathResolver) -> None:
        self.resolver = resolver
        self._read_states: dict[str, FileReadState] = {}

    def get(self, path: str) -> FileReadState | None:
        return self._read_states.get(self.resolver.normalize_path(path))

    def mark_bytes(self, path: str, content: bytes) -> None:
        normalized = self.resolver.normalize_path(path)
        self._read_states[normalized] = FileReadState(
            path=normalized,
            is_full_read=True,
            content_hash=self.hash_bytes(content),
        )

    def remember_successful_read(
        self,
        path: str,
        rendered: str,
        *,
        limit: int | None,
        pages: str | None,
        adapter: FilesystemBackendAdapter,
        content: bytes | None = None,
    ) -> None:
        if (
            rendered.startswith("Error:")
            or rendered.startswith("Cannot read ")
            or rendered.startswith("File content (")
            or rendered.startswith("This PDF has ")
            or rendered.startswith("Invalid pages parameter:")
            or rendered.startswith("This tool cannot read binary files.")
            or rendered.startswith("File is not a valid PDF")
            or rendered.startswith("PDF is password-protected.")
            or rendered.startswith("PDF file is corrupted or invalid.")
            or rendered.startswith("pdftoppm failed:")
            or rendered.startswith("pdftoppm is not installed.")
        ):
            return

        normalized_path = self.resolver.normalize_path(path)
        is_full_read = limit is None and pages is None and not self.is_partial_read_output(rendered)
        if not is_full_read:
            self._read_states[normalized_path] = FileReadState(path=normalized_path, is_full_read=False)
            return

        payload = content if content is not None else adapter.read_current_bytes(path)
        if payload is None:
            return
        self._read_states[normalized_path] = FileReadState(
            path=normalized_path,
            is_full_read=True,
            content_hash=self.hash_bytes(payload),
        )

    def validate_write_preconditions(self, path: str, adapter: FilesystemBackendAdapter) -> str | None:
        info = adapter.stat_path(path)
        if not info.exists:
            return None
        if info.is_dir:
            return f"Error: '{path}' is a directory. Use ls to list its contents."

        read_state = self.get(path)
        if read_state is None or not read_state.is_full_read:
            return "File has not been read yet. Read it first before writing to it."

        current_content = adapter.read_current_bytes(path)
        if current_content is None:
            return f"Error: '{path}' does not exist."
        if read_state.content_hash != self.hash_bytes(current_content):
            return "File has been modified since read. Read it again before attempting to write it."
        return None

    def hash_bytes(self, content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def is_partial_read_output(self, rendered: str) -> bool:
        return rendered.startswith("[Showing lines ") or "\n\n[Showing lines " in rendered
