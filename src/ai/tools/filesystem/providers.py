from __future__ import annotations

from pathlib import Path

from src.ai.filesystem import FilesystemService, GlobSearchResult, GrepSearchResult

class BaseFilesystemToolProvider:
    def __init__(self, root_dir: str | Path, *, backend: object | None = None) -> None:
        self.filesystem = FilesystemService(root_dir, backend=backend)
        self.root = self.filesystem.root

    def resolve_permission_target(self, path: str, *, base: str | None = None) -> tuple[str, Path]:
        return self.filesystem.resolve_permission_target(path, base=base)

    def normalize_path(self, path: str, *, base: str | None = None) -> str:
        return self.filesystem.normalize_path(path, base=base)

    def format_glob_matches(self, pattern: str, path: str, matches: list[str]) -> str:
        return self.filesystem.format_glob_matches(pattern, path, matches)

    def format_grep_matches(self, pattern: str, output_mode: str, matches: list[dict[str, object]]) -> str:
        return self.filesystem.format_grep_matches(pattern, output_mode, matches)

    def ls(self, path: str = ".") -> str:
        return self.filesystem.ls(path)

    def read_file(self, path: str, offset: int = 0, limit: int | None = None) -> str:
        return self.filesystem.read_file(path, offset=offset, limit=limit)

    def write_file(self, path: str, content: str) -> str:
        return self.filesystem.write_file(path, content)

    def edit_file(
        self,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> str:
        return self.filesystem.edit_file(path, old_string, new_string, replace_all)

    def glob_search(self, pattern: str, path: str = ".") -> GlobSearchResult:
        return self.filesystem.glob_search(pattern, path)

    def grep_search(self, pattern: str, path: str = ".", glob: str | None = None) -> GrepSearchResult:
        return self.filesystem.grep_search(pattern, path, glob)


class LocalFilesystemToolProvider(BaseFilesystemToolProvider):
    def __init__(self, root_dir: str | Path) -> None:
        super().__init__(root_dir)


class SandboxFilesystemToolProvider(BaseFilesystemToolProvider):
    def __init__(self, root_dir: str | Path, backend: object) -> None:
        super().__init__(root_dir, backend=backend)

