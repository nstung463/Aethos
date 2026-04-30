from __future__ import annotations

from src.ai.filesystem.backend import FilesystemBackendAdapter
from src.ai.filesystem.pathing import WorkspacePathResolver
from src.ai.filesystem.state import ReadStateStore


def write_file(
    resolver: WorkspacePathResolver,
    adapter: FilesystemBackendAdapter,
    state: ReadStateStore,
    path: str,
    content: str,
) -> str:
    path = resolver.sanitize_input_path(path)
    validation_error = state.validate_write_preconditions(path, adapter)
    if validation_error:
        return validation_error

    encoded = content.encode("utf-8")
    result = adapter.write_bytes(path, encoded)
    if result.error:
        return f"Error: {result.error}"

    state.mark_bytes(path, encoded)
    lines = content.count("\n") + 1
    return f"Written {len(content)} characters ({lines} lines) to '{path}'."
