"""LocalBackend — runs commands via subprocess on the local machine.

Used when no remote sandbox is configured. The workspace root acts as
the sandbox boundary; commands run in a subprocess with cwd=root.
"""

from __future__ import annotations

import fnmatch
import os
import re
import subprocess
from pathlib import Path
from uuid import uuid4

from src.backends.protocol import (
    EditResult,
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
    LsEntry,
    LsResult,
    PathInfo,
    ReadResult,
    WriteResult,
)
from src.backends.sandbox import CommandBackedBackend
from src.ai.tools.filesystem._sandbox import resolve


def _is_windows() -> bool:
    return os.name == "nt"


class LocalBackend(CommandBackedBackend):
    """Local backend. Shell commands run via subprocess; filesystem ops are native."""

    def __init__(self, root_dir: str = "./workspace", timeout: int = 120) -> None:
        self._root = Path(root_dir).resolve()
        self._root.mkdir(parents=True, exist_ok=True)
        self._default_timeout = timeout
        self._id = str(uuid4())

    @property
    def id(self) -> str:
        return self._id

    @property
    def supported_shells(self) -> set[str]:
        return {"powershell"} if _is_windows() else {"bash"}

    @property
    def root(self) -> Path:
        return self._root

    def ls(self, path: str) -> LsResult:
        target = resolve(self._root, path)
        entries: list[LsEntry] = []
        if not target.exists():
            return LsResult(entries=entries)
        if target.is_file():
            return LsResult(entries=[LsEntry(path=str(target), is_dir=False)])
        try:
            for child in target.iterdir():
                entries.append(LsEntry(path=str(child), is_dir=child.is_dir()))
        except OSError:
            entries = []
        return LsResult(entries=entries)

    def read_bytes(self, path: str) -> FileDownloadResponse:
        target = resolve(self._root, path)
        if not target.exists() or not target.is_file():
            return FileDownloadResponse(path=path, error="file_not_found")
        return FileDownloadResponse(path=path, content=target.read_bytes())

    def write_bytes(self, path: str, content: bytes) -> FileUploadResponse:
        target = resolve(self._root, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return FileUploadResponse(path=path)

    def stat_path(self, path: str) -> PathInfo:
        target = resolve(self._root, path)
        exists = target.exists()
        is_file = target.is_file()
        return PathInfo(
            path=path,
            exists=exists,
            is_file=is_file,
            is_dir=exists and target.is_dir(),
            size=target.stat().st_size if is_file else None,
        )

    def list_dir(self, path: str) -> LsResult:
        target = resolve(self._root, path)
        if not target.exists():
            return LsResult(error="path_not_found")
        if target.is_file():
            return LsResult(entries=[LsEntry(path=target.relative_to(self._root).as_posix(), is_dir=False)])

        entries: list[LsEntry] = []
        try:
            for child in target.iterdir():
                entries.append(
                    LsEntry(
                        path=child.relative_to(self._root).as_posix(),
                        is_dir=child.is_dir(),
                    )
                )
        except OSError as exc:
            return LsResult(error=str(exc))
        return LsResult(entries=entries)

    def walk(self, path: str) -> list[LsEntry]:
        target = resolve(self._root, path)
        if not target.exists():
            return []
        if target.is_file():
            return [LsEntry(path=path, is_dir=False)]

        entries: list[LsEntry] = []
        for child in sorted(target.rglob("*")):
            entries.append(
                LsEntry(
                    path=child.relative_to(self._root).as_posix(),
                    is_dir=child.is_dir(),
                )
            )
        return entries

    def read(self, file_path: str, offset: int = 0, limit: int | None = 200) -> ReadResult:
        target = resolve(self._root, file_path)
        if not target.exists() or not target.is_file():
            return ReadResult(error=f"'{file_path}': file_not_found")

        try:
            all_lines = target.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            return ReadResult(error=f"'{file_path}': not_a_text_file")

        if not all_lines:
            return ReadResult(content="(empty file)")

        start = max(0, offset)
        end = len(all_lines) if limit is None else min(len(all_lines), start + limit)
        selected = all_lines[start:end]
        if not selected:
            return ReadResult(
                content=f"[File has {len(all_lines)} lines, but offset={offset} is past the end.]"
            )

        numbered = [f"{i + start + 1:>6}\t{line}" for i, line in enumerate(selected)]
        content = "\n".join(numbered)
        if end < len(all_lines):
            content += (
                f"\n\n[Showing lines {start + 1}-{end} of {len(all_lines)}. "
                f"Use offset={end} to read more.]"
            )
        return ReadResult(content=content)

    def write(self, file_path: str, content: str) -> WriteResult:
        target = resolve(self._root, file_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return WriteResult(path=file_path)

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> EditResult:
        target = resolve(self._root, file_path)
        if not target.exists() or not target.is_file():
            return EditResult(error=f"File '{file_path}' not found. Read it before editing.")

        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return EditResult(error=f"'{file_path}' is not a text file.")

        count = content.count(old_string)
        if count == 0:
            return EditResult(
                error=f"old_string not found in '{file_path}'. Check exact whitespace and indentation."
            )
        if count > 1 and not replace_all:
            return EditResult(
                error=f"old_string appears {count} times in '{file_path}'. Add more context or use replace_all=True."
            )

        updated = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)
        target.write_text(updated, encoding="utf-8")
        return EditResult(path=file_path, occurrences=count if replace_all else 1)

    def glob(self, pattern: str, path: str = "/") -> list[str]:
        search_root = resolve(self._root, path)
        if not search_root.exists():
            return []

        return [
            match.relative_to(search_root).as_posix()
            for match in sorted(search_root.glob(pattern))
        ]

    def grep(self, pattern: str, path: str = ".", glob: str | None = None) -> list[dict]:
        target = resolve(self._root, path)
        if not target.exists():
            return []

        try:
            regex = re.compile(pattern)
        except re.error:
            return []

        if target.is_file():
            files = [target]
        else:
            files = sorted(candidate for candidate in target.rglob("*") if candidate.is_file())
            if glob:
                files = [candidate for candidate in files if fnmatch.fnmatch(candidate.name, glob)]

        matches: list[dict] = []
        for file_path in files:
            try:
                lines = file_path.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue

            for line_number, line in enumerate(lines, start=1):
                if regex.search(line):
                    matches.append(
                        {
                            "path": file_path.relative_to(self._root).as_posix(),
                            "line": line_number,
                            "text": line,
                        }
                    )
        return matches

    def _normalize_command_for_platform(self, command: str) -> str:
        if not _is_windows():
            return command
        # CommandBackedBackend templates use `python3`; on Windows this alias may be absent.
        return command.replace("python3 -c", "python -c")

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        """Run a shell command in the workspace root via subprocess."""
        effective_timeout = timeout if timeout is not None else self._default_timeout
        normalized_command = self._normalize_command_for_platform(command)
        try:
            result = subprocess.run(
                normalized_command,
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(self._root),
                timeout=effective_timeout,
            )
            output = result.stdout
            if result.stderr.strip():
                output += f"\n<stderr>{result.stderr.strip()}</stderr>"
            return ExecuteResponse(
                output=output,
                exit_code=result.returncode,
                truncated=False,
            )
        except subprocess.TimeoutExpired:
            return ExecuteResponse(
                output=f"Command timed out after {effective_timeout}s",
                exit_code=124,
                truncated=False,
            )
        except Exception as e:
            return ExecuteResponse(output=str(e), exit_code=1, truncated=False)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        responses = []
        for path, content in files:
            try:
                p = Path(path)
                if not p.is_absolute():
                    p = self._root / path
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(content)
                responses.append(FileUploadResponse(path=path))
            except Exception as e:
                responses.append(FileUploadResponse(path=path, error=str(e)))
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses = []
        for path in paths:
            try:
                p = Path(path)
                if not p.is_absolute():
                    p = self._root / path
                if not p.exists():
                    responses.append(FileDownloadResponse(path=path, error="file_not_found"))
                else:
                    responses.append(FileDownloadResponse(path=path, content=p.read_bytes()))
            except Exception as e:
                responses.append(FileDownloadResponse(path=path, error=str(e)))
        return responses


# Backward-compatible alias while call sites migrate.
LocalSandbox = LocalBackend
