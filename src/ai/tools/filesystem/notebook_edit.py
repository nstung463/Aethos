"""notebook_edit tool — edit a Jupyter notebook cell by index.

Mirrors NotebookEditTool from claude-code-source.
Requires nbformat: pip install nbformat
"""
from __future__ import annotations

from pathlib import Path

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from src.ai.filesystem import FilesystemService
from src.ai.permissions.types import PermissionContext, PermissionSubject
from src.ai.tools.filesystem._shared import permission_error
from src.ai.tools.filesystem._sandbox import resolve


class NotebookEditInput(BaseModel):
    path: str = Field(description="Path to the .ipynb file (relative to workspace root).")
    cell_index: int = Field(description="0-based index of the cell to edit.")
    new_source: str = Field(description="New source content for the cell.")


def _edit_notebook(root: Path, path: str, cell_index: int, new_source: str) -> str:
    try:
        import nbformat
    except ImportError:
        return "Error: nbformat not installed. Run: pip install nbformat"

    if not path.endswith(".ipynb"):
        return f"Error: '{path}' is not a Jupyter notebook (.ipynb)."

    target = resolve(root, path)
    if not target.exists():
        return f"Error: '{path}' does not exist."

    try:
        nb = nbformat.read(str(target), as_version=4)
    except Exception as exc:
        return f"Error reading notebook: {exc}"

    if cell_index < 0 or cell_index >= len(nb.cells):
        return (
            f"Error: cell_index {cell_index} is out of range. "
            f"Notebook has {len(nb.cells)} cells (0–{len(nb.cells) - 1})."
        )

    nb.cells[cell_index].source = new_source

    try:
        nbformat.write(nb, str(target))
    except Exception as exc:
        return f"Error writing notebook: {exc}"

    return f"Edited cell {cell_index} in '{path}'."


def build_notebook_edit_tool(root: Path, permission_context: PermissionContext | None = None) -> StructuredTool:
    filesystem = FilesystemService(root)

    def _tool(path: str, cell_index: int, new_source: str) -> str:
        normalized_path = path.strip() or "."
        try:
            blocked = permission_error(filesystem, permission_context, PermissionSubject.EDIT, normalized_path)
        except PermissionError as exc:
            return str(exc)
        if blocked:
            return blocked
        return _edit_notebook(root, normalized_path, cell_index, new_source)

    return StructuredTool.from_function(
        name="notebook_edit",
        func=_tool,
        description=(
            "Edit the source of a Jupyter notebook cell by its index. "
            "Read the notebook first to identify cell indices. "
            "Only the cell source is changed — outputs and metadata are preserved."
        ),
        args_schema=NotebookEditInput,
    )
