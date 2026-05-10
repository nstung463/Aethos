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
from src.app.dependencies import build_file_store_for_workspace
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
    path: str = Field(description="Path to the final output file in the current workspace or sandbox.")
    title: str | None = Field(default=None, description="Short display title. Defaults to the filename.")
    description: str | None = Field(default=None, description="Optional short description shown in the UI.")
    artifact_type: ArtifactType | None = Field(
        default=None,
        description="Optional UI artifact type. Auto-detected from the file extension when omitted.",
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
            "Call this after creating a final user-facing output file so the UI can show it as a "
            "downloadable/viewable artifact. Use it for final files like spreadsheets, PDFs, documents, "
            "presentations, images, datasets, or archives that the user should open or download."
        ),
        args_schema=PresentOutputFileInput,
    )


__all__ = [
    "PRESENT_OUTPUT_FILE_MARKER",
    "PresentOutputFileInput",
    "build_present_output_file_tool",
    "detect_artifact_type",
]
