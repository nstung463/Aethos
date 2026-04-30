from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from src.ai.filesystem import FilesystemService
from src.ai.permissions.types import PermissionContext, PermissionSubject
from src.ai.tools.filesystem._shared import permission_error
from src.ai.tools.filesystem.media_support import MediaBlockSupport
from src.ai.tools.filesystem.read_media_prompt import render_read_media_tool_description
from src.backends.protocol import FilesystemBackendProtocol


class ReadMediaFileInput(BaseModel):
    path: str = Field(description="Media file path to read (relative to workspace root).")
    pages: str | None = Field(
        default=None,
        description=(
            'PDF page range (e.g. "1-5", "3", "10-20"). '
            "Only applies to PDF files."
        ),
    )


def build_read_media_file_tool(
    root: Path,
    backend: FilesystemBackendProtocol | None = None,
    permission_context: PermissionContext | None = None,
    filesystem: FilesystemService | None = None,
    media_block_support: MediaBlockSupport | None = None,
) -> StructuredTool:
    filesystem = filesystem or FilesystemService(root, backend=backend)
    media_block_support = media_block_support or MediaBlockSupport()

    def _tool(path: str, pages: str | None = None) -> str | list[dict[str, Any]]:
        normalized_path = path.strip() or "."
        try:
            blocked = permission_error(
                filesystem,
                permission_context,
                PermissionSubject.READ,
                normalized_path,
            )
        except PermissionError as exc:
            return str(exc)
        if blocked:
            return blocked
        return filesystem.read_media_file(
            normalized_path,
            pages=pages,
            allow_image_blocks=media_block_support.image_blocks,
            allow_file_blocks=media_block_support.file_blocks,
        )

    return StructuredTool.from_function(
        name="read_media_file",
        func=_tool,
        description=render_read_media_tool_description(),
        args_schema=ReadMediaFileInput,
    )


__all__ = ["ReadMediaFileInput", "build_read_media_file_tool"]
