from __future__ import annotations

from pathlib import Path

from src.ai.tools.filesystem import (
    FilesystemService,
    FilesystemToolBuilder,
    build_filesystem_tools,
)
from src.ai.tools.filesystem.read_prompt import render_read_tool_description
from dataclasses import dataclass

from src.backends.protocol import FileDownloadResponse, FileUploadResponse, LsEntry, LsResult


@dataclass
class PathInfo:
    """Local stand-in for the removed PathInfo type from protocol."""
    path: str
    exists: bool
    is_file: bool
    is_dir: bool
    size: int = 0


class _FakeSandbox:
    supported_shells: list[str] = []

    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def stat_path(self, path: str) -> PathInfo:
        self.calls.append(("stat_path", path))
        if path == "src/app.py":
            return PathInfo(path=path, exists=True, is_file=True, is_dir=False, size=12)
        return PathInfo(path=path, exists=True, is_file=False, is_dir=True)

    def list_dir(self, path: str) -> LsResult:
        self.calls.append(("list_dir", path))
        return LsResult(entries=[LsEntry("src", True), LsEntry("src/app.py", False)])

    def walk(self, path: str) -> list[LsEntry]:
        self.calls.append(("walk", path))
        return [LsEntry("src/app.py", False)]

    def read_bytes(self, path: str) -> FileDownloadResponse:
        self.calls.append(("read_bytes", path))
        return FileDownloadResponse(path=path, content=b"sandbox file")

    def write_bytes(self, path: str, content: bytes) -> FileUploadResponse:
        self.calls.append(("write_bytes", path, content))
        return FileUploadResponse(path=path)


def test_filesystem_tool_builder_is_importable() -> None:
    assert FilesystemToolBuilder is not None
    assert FilesystemService is not None


def test_build_filesystem_tools_local_contract(workspace: Path) -> None:
    tools = build_filesystem_tools(root_dir=str(workspace))
    assert [tool.name for tool in tools] == ["ls", "read_file", "read_media_file", "write_file", "edit_file", "glob", "grep"]


def test_build_filesystem_tools_sandbox_contract(workspace: Path) -> None:
    backend = _FakeSandbox()
    tools = build_filesystem_tools(root_dir=str(workspace), backend=backend)
    assert [tool.name for tool in tools] == ["ls", "read_file", "read_media_file", "write_file", "edit_file", "glob", "grep"]

    read_file_tool = next(tool for tool in tools if tool.name == "read_file")
    result = read_file_tool.invoke({"path": "src/app.py"})
    assert "sandbox file" in result
    assert ("read_bytes", "src/app.py") in backend.calls


def test_build_filesystem_tools_sandbox_uses_shared_tool_definitions(workspace: Path) -> None:
    local_tools = build_filesystem_tools(root_dir=str(workspace))
    sandbox_tools = build_filesystem_tools(root_dir=str(workspace), backend=_FakeSandbox())
    local_map = {
        tool.name: {
            "description": tool.description,
            "args_schema": type(tool.args_schema).__name__ if tool.args_schema is not None else None,
        }
        for tool in local_tools
    }
    sandbox_map = {
        tool.name: {
            "description": tool.description,
            "args_schema": type(tool.args_schema).__name__ if tool.args_schema is not None else None,
        }
        for tool in sandbox_tools
    }
    assert sandbox_map == local_map


def test_read_file_tool_description_ports_claude_guidance_without_overstating_runtime(
    workspace: Path,
) -> None:
    tool = next(tool for tool in build_filesystem_tools(root_dir=str(workspace)) if tool.name == "read_file")
    description = tool.description or ""

    assert "Read a file from the local filesystem." in description
    assert "By default, it reads up to 2000 lines starting from the beginning of the file." in description
    assert "Results are returned using cat -n format, with line numbers starting at 1." in description
    assert "You can optionally specify a line offset and limit" in description
    assert "When you already know which part of the file you need, only read that part." in description
    assert "This tool can read PDF files (.pdf)." in description
    assert "This tool can read Jupyter notebooks (.ipynb files)" in description
    assert "If the user provides a path to a screenshot, ALWAYS use this tool" in description
    assert "must be an absolute path" not in description
    assert "presented visually" not in description


def test_render_read_tool_description_matches_tool_description() -> None:
    description = render_read_tool_description()

    assert description.startswith("Read a file from the local filesystem.")
    assert "Paths are relative to the workspace root." in description


def test_write_file_tool_description_ports_claude_guidance(workspace: Path) -> None:
    tool = next(tool for tool in build_filesystem_tools(root_dir=str(workspace)) if tool.name == "write_file")
    description = tool.description or ""

    assert "must use the read_file tool first" in description.lower()
    assert "never create documentation files" in description.lower()
