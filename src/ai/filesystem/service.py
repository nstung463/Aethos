from __future__ import annotations

from pathlib import Path
from typing import Any

from src.ai.filesystem.backend import FilesystemBackendAdapter
from src.ai.filesystem.edit import edit_file as edit_file_core
from src.ai.filesystem.pathing import WorkspacePathResolver
from src.ai.filesystem.read import read_file as read_file_core, read_media_file as read_media_file_core
from src.ai.filesystem.search import (
    GlobSearchResult,
    GrepSearchResult,
    format_glob_matches,
    format_grep_matches,
    glob_search,
    grep_search,
    list_path,
)
from src.ai.filesystem.state import ReadStateStore
from src.ai.filesystem.write import write_file as write_file_core
from src.backends.protocol import SandboxProtocol as FilesystemBackendProtocol


class FilesystemService:
    def __init__(
        self,
        root_dir: str | Path,
        *,
        backend: FilesystemBackendProtocol | None = None,
    ) -> None:
        self.resolver = WorkspacePathResolver(root_dir)
        self.root = self.resolver.root
        self.backend = backend
        self.adapter = FilesystemBackendAdapter(self.resolver, backend=backend)
        self.state = ReadStateStore(self.resolver)

    def resolve_permission_target(self, path: str, *, base: str | None = None) -> tuple[str, Path]:
        return self.resolver.resolve_permission_target(path, base=base)

    def normalize_path(self, path: str, *, base: str | None = None) -> str:
        return self.resolver.normalize_path(path, base=base)

    def format_glob_matches(self, pattern: str, path: str, matches: list[str]) -> str:
        return format_glob_matches(pattern, path, matches)

    def format_grep_matches(self, pattern: str, output_mode: str, matches: list[dict[str, object]]) -> str:
        return format_grep_matches(pattern, output_mode, matches)

    def ls(self, path: str = ".") -> str:
        try:
            return list_path(self.resolver, self.adapter, path)
        except PermissionError as exc:
            return str(exc)

    def read_file(
        self,
        path: str,
        offset: int = 1,
        limit: int | None = None,
        pages: str | None = None,
    ) -> str:
        try:
            return read_file_core(self.resolver, self.adapter, self.state, path, offset=offset, limit=limit, pages=pages)
        except PermissionError as exc:
            return str(exc)

    def read_media_file(
        self,
        path: str,
        *,
        pages: str | None = None,
        allow_image_blocks: bool = False,
        allow_file_blocks: bool = False,
    ) -> str | list[dict[str, Any]]:
        try:
            return read_media_file_core(
                self.resolver,
                self.adapter,
                path,
                pages=pages,
                allow_image_blocks=allow_image_blocks,
                allow_file_blocks=allow_file_blocks,
            )
        except PermissionError as exc:
            return str(exc)

    def write_file(self, path: str, content: str) -> str:
        try:
            return write_file_core(self.resolver, self.adapter, self.state, path, content)
        except PermissionError as exc:
            return str(exc)

    def edit_file(self, path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
        try:
            return edit_file_core(
                self.resolver,
                self.adapter,
                self.state,
                path,
                old_string,
                new_string,
                replace_all,
            )
        except PermissionError as exc:
            return str(exc)

    def glob_search(self, pattern: str, path: str = ".") -> GlobSearchResult:
        try:
            return glob_search(self.resolver, self.adapter, pattern, path)
        except PermissionError as exc:
            return GlobSearchResult(error=str(exc))

    def grep_search(self, pattern: str, path: str = ".", glob: str | None = None) -> GrepSearchResult:
        try:
            return grep_search(self.resolver, self.adapter, pattern, path, glob)
        except PermissionError as exc:
            return GrepSearchResult(error=str(exc))
