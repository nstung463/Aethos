from __future__ import annotations

from src.ai.filesystem.pathing import WorkspacePathResolver
from src.backends.protocol import (
    FileDownloadResponse,
    FileUploadResponse,
    LsEntry,
    LsResult,
    PathInfo,
    ReadResult,
    SandboxProtocol as FilesystemBackendProtocol,
    WriteResult,
)

DEFAULT_READ_LIMIT = 200


class FilesystemBackendAdapter:
    def __init__(
        self,
        resolver: WorkspacePathResolver,
        backend: FilesystemBackendProtocol | None = None,
    ) -> None:
        self.resolver = resolver
        self.backend = backend

    def stat_path(self, path: str) -> PathInfo:
        if self.backend is None:
            target = self.resolver.resolve_workspace_path(path)
            exists = target.exists()
            return PathInfo(
                path=path,
                exists=exists,
                is_file=exists and target.is_file(),
                is_dir=exists and target.is_dir(),
                size=target.stat().st_size if exists and target.is_file() else 0,
            )

        stat_path = getattr(self.backend, "stat_path", None)
        if callable(stat_path):
            return stat_path(path)

        read_method = getattr(self.backend, "read", None)
        ls_method = getattr(self.backend, "ls", None)
        if callable(read_method):
            read_result: ReadResult = read_method(path, offset=0, limit=1)
            if read_result.error is None:
                return PathInfo(path=path, exists=True, is_file=True, is_dir=False)
        if callable(ls_method):
            ls_result: LsResult = ls_method(path)
            if ls_result.error is None:
                return PathInfo(path=path, exists=True, is_file=False, is_dir=True)
        return PathInfo(path=path, exists=False, is_file=False, is_dir=False)

    def list_dir(self, path: str) -> LsResult:
        if self.backend is None:
            target = self.resolver.resolve_workspace_path(path)
            if not target.exists():
                return LsResult(error=f"'{path}' does not exist.")
            if target.is_file():
                return LsResult(entries=[LsEntry(path=self.resolver.to_display_path(target), is_dir=False)])
            return LsResult(
                entries=[
                    LsEntry(path=self.resolver.to_display_path(entry), is_dir=entry.is_dir())
                    for entry in target.iterdir()
                ]
            )

        list_dir = getattr(self.backend, "list_dir", None)
        if callable(list_dir):
            return list_dir(path)

        ls_method = getattr(self.backend, "ls", None)
        if callable(ls_method):
            return ls_method(path)
        return LsResult(error=f"'{path}' does not exist.")

    def walk(self, path: str) -> list[LsEntry]:
        if self.backend is None:
            target = self.resolver.resolve_workspace_path(path)
            if not target.exists():
                return []
            if target.is_file():
                return [LsEntry(path=self.resolver.to_display_path(target), is_dir=False)]
            return [
                LsEntry(path=self.resolver.to_display_path(entry), is_dir=entry.is_dir())
                for entry in target.rglob("*")
            ]

        walk = getattr(self.backend, "walk", None)
        if callable(walk):
            return walk(path)

        glob_method = getattr(self.backend, "glob", None)
        if callable(glob_method):
            return [LsEntry(path=match, is_dir=False) for match in glob_method("**/*", path)]
        return []

    def read_bytes(self, path: str, offset: int = 0, limit: int | None = None) -> FileDownloadResponse:
        if self.backend is None:
            target = self.resolver.resolve_workspace_path(path)
            if not target.exists() or target.is_dir():
                return FileDownloadResponse(path=path, error="file_not_found")
            return FileDownloadResponse(path=path, content=target.read_bytes())

        read_bytes = getattr(self.backend, "read_bytes", None)
        if callable(read_bytes):
            return read_bytes(path)

        read_method = getattr(self.backend, "read", None)
        if callable(read_method):
            read_result: ReadResult = read_method(path, offset=offset, limit=limit or DEFAULT_READ_LIMIT)
            if read_result.error:
                return FileDownloadResponse(path=path, error=read_result.error)
            return FileDownloadResponse(path=path, content=(read_result.content or "").encode("utf-8"))
        return FileDownloadResponse(path=path, error="file_not_found")

    def write_bytes(self, path: str, content: bytes) -> FileUploadResponse:
        if self.backend is None:
            target = self.resolver.resolve_workspace_path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            return FileUploadResponse(path=path)

        write_bytes = getattr(self.backend, "write_bytes", None)
        if callable(write_bytes):
            return write_bytes(path, content)

        write_method = getattr(self.backend, "write", None)
        if callable(write_method):
            write_result: WriteResult = write_method(path, content.decode("utf-8"))
            return FileUploadResponse(path=path, error=write_result.error)
        return FileUploadResponse(path=path, error="write_not_supported")

    def read_current_bytes(self, path: str) -> bytes | None:
        response = self.read_bytes(path)
        if response.error or response.content is None:
            return None
        return response.content
