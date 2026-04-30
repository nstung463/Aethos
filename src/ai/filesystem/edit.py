from __future__ import annotations

from pathlib import Path

from src.ai.filesystem.backend import FilesystemBackendAdapter
from src.ai.filesystem.pathing import WorkspacePathResolver
from src.ai.filesystem.state import ReadStateStore


def edit_file(
    resolver: WorkspacePathResolver,
    adapter: FilesystemBackendAdapter,
    state: ReadStateStore,
    path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> str:
    path = resolver.sanitize_input_path(path)

    if old_string == new_string:
        return "No changes to make: old_string and new_string are exactly the same."

    info = adapter.stat_path(path)
    if info.is_dir:
        return f"Error: '{path}' is a directory. Use ls to list its contents."

    if old_string == "":
        if info.exists:
            response = adapter.read_bytes(path)
            if response.error:
                return f"Error reading '{path}': {response.error}."
            existing = response.content or b""
            if existing.strip():
                return "Cannot create new file - file already exists."
        updated_bytes = new_string.encode("utf-8")
        write_result = adapter.write_bytes(path, updated_bytes)
        if write_result.error:
            return f"Error: {write_result.error}"
        state.mark_bytes(path, updated_bytes)
        return f"The file '{path}' has been updated successfully."

    if not info.exists:
        return f"Error: '{path}' does not exist. Read the file before editing."

    if Path(path).suffix.lower() == ".ipynb":
        return "File is a Jupyter Notebook. Use the notebook_edit tool to edit this file."

    read_state = state.get(path)
    if read_state is None or not read_state.is_full_read:
        return "File has not been read yet. Read it first before editing it."

    response = adapter.read_bytes(path)
    if response.error or response.content is None:
        return f"Error: '{path}' does not exist."

    if read_state.content_hash != state.hash_bytes(response.content):
        return "File has been modified since read. Read it again before attempting to edit it."

    try:
        content = response.content.decode("utf-8")
    except UnicodeDecodeError:
        return f"Error: '{path}' is not a text file."

    count = content.count(old_string)
    if count == 0:
        return f"String to replace not found in file.\nString: {old_string}"
    if count > 1 and not replace_all:
        return (
            f"Found {count} matches of the string to replace, but replace_all is false. "
            "To replace all occurrences, set replace_all to true. "
            "To replace only one occurrence, provide more context to uniquely identify the instance.\n"
            f"String: {old_string}"
        )

    updated = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)
    updated_bytes = updated.encode("utf-8")
    write_result = adapter.write_bytes(path, updated_bytes)
    if write_result.error:
        return f"Error: {write_result.error}"

    state.mark_bytes(path, updated_bytes)
    if replace_all:
        return f"The file '{path}' has been updated. All occurrences were successfully replaced."
    return f"The file '{path}' has been updated successfully."
