"""present_output_file tool — publish final user-facing files for the UI."""
from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from src.ai.filesystem import FilesystemService
from src.ai.permissions.types import PermissionContext, PermissionSubject
from src.ai.tools.filesystem._shared import permission_error
from src.app.api.dependencies import build_file_store_for_workspace
from src.backends.protocol import SandboxProtocol as FilesystemBackendProtocol

ArtifactType = Literal["spreadsheet", "document", "presentation", "pdf", "image", "data", "archive", "other"]

PRESENT_OUTPUT_FILE_MARKER = "__aethos_presented_output_file__"

_ARTIFACT_TYPES_BY_SUFFIX: dict[str, ArtifactType] = {
    ".xlsx": "spreadsheet",
    ".xls": "spreadsheet",
    ".ods": "spreadsheet",
    ".csv": "data",
    ".tsv": "data",
    ".json": "data",
    ".parquet": "data",
    ".docx": "document",
    ".doc": "document",
    ".txt": "document",
    ".md": "document",
    ".pptx": "presentation",
    ".ppt": "presentation",
    ".pdf": "pdf",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
    ".webp": "image",
    ".svg": "image",
    ".zip": "archive",
    ".tar": "archive",
    ".gz": "archive",
}


class PresentOutputFileInput(BaseModel):
    path: str = Field(
        description=(
            "Relative or absolute path to an existing final output file. Prefer a workspace-relative path. "
            "Must point to a single file, not a directory."
        )
    )
    title: str | None = Field(
        default=None,
        description=(
            "Short user-facing title shown in the UI, such as 'Q1 Sales Report'. "
            "Defaults to the filename."
        ),
    )
    description: str | None = Field(
        default=None,
        description=(
            "Optional one-sentence user-facing caption describing what the file contains or why it is useful. "
            "Keep it brief."
        ),
    )
    artifact_type: ArtifactType | None = Field(
        default=None,
        description=(
            "Optional artifact category for UI rendering. Set this when the file extension is ambiguous; "
            "otherwise it is auto-detected."
        ),
    )


def detect_artifact_type(filename: str) -> ArtifactType:
    return _ARTIFACT_TYPES_BY_SUFFIX.get(Path(filename).suffix.lower(), "other")


def build_present_output_file_tool(
    root_dir: str | Path,
    *,
    backend: FilesystemBackendProtocol | None = None,
    owner_user_id: str | None = None,
    permission_context: PermissionContext | None = None,
) -> StructuredTool:
    filesystem = FilesystemService(root_dir, backend=backend)
    store = build_file_store_for_workspace(root_dir)

    def _present_output_file(
        path: str,
        title: str | None = None,
        description: str | None = None,
        artifact_type: ArtifactType | None = None,
    ) -> str:
        if not owner_user_id:
            return "Error: present_output_file requires an authenticated user session."

        normalized_path = path.strip() or "."
        try:
            blocked = permission_error(filesystem, permission_context, PermissionSubject.READ, normalized_path)
            display_path, target = filesystem.resolve_permission_target(normalized_path)
        except PermissionError as exc:
            return f"Error: {exc}"
        if blocked:
            return blocked

        stat = filesystem.adapter.stat_path(display_path)
        if not stat.exists:
            return f"Error: output file '{normalized_path}' does not exist."
        if not stat.is_file:
            return f"Error: output path '{normalized_path}' is not a file."

        response = filesystem.adapter.read_bytes(display_path)
        if response.error or response.content is None:
            return f"Error: could not read output file '{normalized_path}': {response.error or 'unknown error'}."

        filename = target.name if backend is None else Path(display_path).name
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        record = store.import_bytes(
            filename=filename,
            content=response.content,
            content_type=content_type,
            owner_user_id=owner_user_id,
        )
        resolved_type = artifact_type or detect_artifact_type(filename)
        artifact = {
            "file_id": record["id"],
            "filename": filename,
            "content_type": record.get("meta", {}).get("content_type") or content_type,
            "size": record.get("meta", {}).get("size", len(response.content)),
            "artifact_type": resolved_type,
            "title": (title or filename).strip() or filename,
            "description": (description or "").strip() or None,
            "content_url": f"/api/files/{record['id']}/content",
        }
        return json.dumps(
            {
                PRESENT_OUTPUT_FILE_MARKER: True,
                "message": f"Presented output file: {filename}",
                "artifact": artifact,
            },
            ensure_ascii=False,
        )

    return StructuredTool.from_function(
        name="present_output_file",
        func=_present_output_file,
        description=(
            "Publish a final user-facing file to the UI after it has already been created on disk. "
            "Use this only for finished deliverables the user should open or download, such as reports, "
            "spreadsheets, PDFs, presentations, images, datasets, or archives. Do not use it for temporary "
            "files, logs, intermediate outputs, or files that are only for the agent's internal work. "
            "Call it once per final artifact version, after verifying the file exists."
        ),
        args_schema=PresentOutputFileInput,
    )


__all__ = [
    "PRESENT_OUTPUT_FILE_MARKER",
    "PresentOutputFileInput",
    "build_present_output_file_tool",
    "detect_artifact_type",
]
