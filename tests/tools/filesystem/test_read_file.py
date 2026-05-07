# tests/tools/filesystem/test_read_file.py
"""Tests for read_file tool."""
from __future__ import annotations

import base64
from pathlib import Path

import pytest

from src.ai.tools.filesystem.read_file import build_read_file_tool
from src.ai.tools.filesystem.read_prompt import render_read_tool_description
from src.ai.permissions.types import (
    PermissionBehavior,
    PermissionContext,
    PermissionMode,
    PermissionRule,
    PermissionSource,
    PermissionSubject,
)

try:
    import nbformat
except ImportError:  # pragma: no cover - optional dependency in dev only
    nbformat = None

HAS_NBFORMAT = nbformat is not None

PNG_1X1_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO5W8"
    "GQAAAAASUVORK5CYII="
)


def test_read_file_returns_numbered_lines(workspace: Path) -> None:
    (workspace / "hello.txt").write_text("line1\nline2\nline3")
    tool = build_read_file_tool(workspace)
    result = tool.invoke({"path": "hello.txt"})
    assert "     1\tline1" in result
    assert "     2\tline2" in result
    assert "     3\tline3" in result


def test_read_file_missing_file(workspace: Path) -> None:
    tool = build_read_file_tool(workspace)
    result = tool.invoke({"path": "missing.txt"})
    assert "does not exist" in result


def test_read_file_redirects_remote_urls_to_web_fetch(workspace: Path) -> None:
    tool = build_read_file_tool(workspace)
    result = tool.invoke({"path": "https://example.com/report.pdf"})
    assert "remote URL" in result
    assert "Use web_fetch" in result


def test_read_file_directory(workspace: Path) -> None:
    (workspace / "d").mkdir()
    tool = build_read_file_tool(workspace)
    result = tool.invoke({"path": "d"})
    assert "directory" in result


def test_read_file_pagination_offset(workspace: Path) -> None:
    lines = "\n".join(f"line{i}" for i in range(1, 11))
    (workspace / "big.txt").write_text(lines)
    tool = build_read_file_tool(workspace)
    result = tool.invoke({"path": "big.txt", "offset": 6, "limit": 3})
    assert "line6" in result
    assert "line7" in result
    assert "line8" in result
    assert "line5" not in result
    assert "line9" not in result


def test_read_file_empty(workspace: Path) -> None:
    (workspace / "empty.txt").write_text("")
    tool = build_read_file_tool(workspace)
    result = tool.invoke({"path": "empty.txt"})
    assert result == "(empty file)"


def test_read_file_offset_past_end(workspace: Path) -> None:
    (workspace / "short.txt").write_text("a\nb")
    tool = build_read_file_tool(workspace)
    result = tool.invoke({"path": "short.txt", "offset": 100})
    assert "past the end" in result


def test_read_file_offset_is_one_based(workspace: Path) -> None:
    (workspace / "one-based.txt").write_text("a\nb\nc")
    tool = build_read_file_tool(workspace)
    result = tool.invoke({"path": "one-based.txt", "offset": 2, "limit": 1})
    assert "     2\tb" in result
    assert "     1\ta" not in result


def test_read_file_shows_truncation_hint(workspace: Path) -> None:
    lines = "\n".join(f"line{i}" for i in range(1, 250))
    (workspace / "long.txt").write_text(lines)
    tool = build_read_file_tool(workspace)
    result = tool.invoke({"path": "long.txt", "limit": 5})
    assert "Showing lines" in result or "offset=" in result


def test_read_file_trims_surrounding_whitespace(workspace: Path) -> None:
    (workspace / "trimmed.txt").write_text("ok")
    tool = build_read_file_tool(workspace)
    result = tool.invoke({"path": "  trimmed.txt  "})
    assert "     1\tok" in result


def test_read_file_blocks_path_traversal_outside_workspace(workspace: Path) -> None:
    tool = build_read_file_tool(workspace)
    result = tool.invoke({"path": "../outside.txt"})
    assert "Access denied" in result


def test_read_file_respects_read_permissions(workspace: Path) -> None:
    (workspace / "secret.txt").write_text("secret")
    permission_context = PermissionContext(
        mode=PermissionMode.DEFAULT,
        workspace_root=workspace,
        working_directories=(workspace,),
        rules=(
            PermissionRule(
                subject=PermissionSubject.READ,
                behavior=PermissionBehavior.DENY,
                source=PermissionSource.SESSION,
                matcher="secret.txt",
            ),
        ),
        headless=True,
    )
    tool = build_read_file_tool(workspace, permission_context=permission_context)
    result = tool.invoke({"path": "secret.txt"})
    assert result == "Permission denied: Denied by session rule"


def test_read_file_strips_utf8_bom(workspace: Path) -> None:
    (workspace / "bom.txt").write_bytes(b"\xef\xbb\xbfline1\nline2")
    tool = build_read_file_tool(workspace)
    result = tool.invoke({"path": "bom.txt"})
    assert "     1\tline1" in result
    assert "\ufeff" not in result


def test_read_file_rejects_large_file_without_limit(workspace: Path) -> None:
    (workspace / "huge.txt").write_text("a" * (300 * 1024), encoding="utf-8")
    tool = build_read_file_tool(workspace)
    result = tool.invoke({"path": "huge.txt"})
    assert "exceeds maximum allowed size" in result


def test_read_file_allows_large_file_when_limit_is_explicit(workspace: Path) -> None:
    lines = "\n".join(f"line{i}" for i in range(40000))
    (workspace / "huge-lines.txt").write_text(lines, encoding="utf-8")
    tool = build_read_file_tool(workspace)
    result = tool.invoke({"path": "huge-lines.txt", "offset": 11, "limit": 2})
    assert "    11\tline10" in result
    assert "    12\tline11" in result


def test_read_file_rejects_known_binary_extensions(workspace: Path) -> None:
    (workspace / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    tool = build_read_file_tool(workspace)
    result = tool.invoke({"path": "image.png"})
    assert "image/png" in result.lower()
    assert "1x1" not in result.lower()  # malformed image should not claim dimensions


@pytest.mark.skipif(not HAS_NBFORMAT, reason="nbformat not installed")
def test_read_file_reads_notebook_cells(workspace: Path) -> None:
    notebook_path = workspace / "demo.ipynb"
    notebook = nbformat.v4.new_notebook()
    notebook.cells = [
        nbformat.v4.new_markdown_cell("## Heading"),
        nbformat.v4.new_code_cell("print('hi')"),
    ]
    nbformat.write(notebook, str(notebook_path))

    tool = build_read_file_tool(workspace)
    result = tool.invoke({"path": "demo.ipynb"})
    assert '<cell id="' in result
    assert "<cell_type>markdown</cell_type>## Heading</cell>" in result
    assert "print('hi')" in result


def test_read_file_reads_image_metadata(workspace: Path) -> None:
    image_path = workspace / "pixel.png"
    image_path.write_bytes(base64.b64decode(PNG_1X1_BASE64))
    tool = build_read_file_tool(workspace)
    result = tool.invoke({"path": "pixel.png"})
    assert "image/png" in result.lower()
    assert "1x1" in result


def test_read_file_reads_pdf_summary(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf_path = workspace / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF")
    monkeypatch.setattr("src.ai.filesystem.read.get_pdf_page_count", lambda path: 3)
    tool = build_read_file_tool(workspace)
    result = tool.invoke({"path": "doc.pdf"})
    assert "pdf" in result.lower()
    assert "pages: 3" in result.lower()


def test_read_file_rejects_invalid_pdf_pages_argument(workspace: Path) -> None:
    pdf_path = workspace / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")
    tool = build_read_file_tool(workspace)
    result = tool.invoke({"path": "doc.pdf", "pages": "abc"})
    assert 'Invalid pages parameter: "abc"' in result


def test_read_file_requires_page_range_for_large_pdfs(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf_path = workspace / "large.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")
    monkeypatch.setattr("src.ai.filesystem.read.get_pdf_page_count", lambda path: 25)
    tool = build_read_file_tool(workspace)
    result = tool.invoke({"path": "large.pdf"})
    assert "too many to read at once" in result


def test_read_file_description_directs_media_requests_to_read_media_file() -> None:
    description = render_read_tool_description()
    assert "Prefer this tool for code, text, JSON, Markdown, logs, notebooks" in description
    assert "If you need the model to inspect an image, screenshot, or PDF as media content instead of text, use read_media_file." in description
    assert "If the document is hosted on the web, use web_fetch instead of this tool." in description
    assert "ALWAYS use this tool to read the file at that path" not in description

