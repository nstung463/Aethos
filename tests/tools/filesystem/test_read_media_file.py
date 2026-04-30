from __future__ import annotations

import base64
from pathlib import Path

import pytest

from src.ai.tools.filesystem.media_support import MediaBlockSupport
from src.ai.tools.filesystem.read_media_file import build_read_media_file_tool

PNG_1X1_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO5W8"
    "GQAAAAASUVORK5CYII="
)


def test_read_media_file_rejects_non_media_file(workspace: Path) -> None:
    (workspace / "notes.txt").write_text("hello", encoding="utf-8")
    tool = build_read_media_file_tool(workspace)
    result = tool.invoke({"path": "notes.txt"})
    assert "Unsupported media file type" in result
    assert "Use read_file instead" in result


def test_read_media_file_returns_image_summary_without_multimodal_support(workspace: Path) -> None:
    (workspace / "pixel.png").write_bytes(base64.b64decode(PNG_1X1_BASE64))
    tool = build_read_media_file_tool(workspace)
    result = tool.invoke({"path": "pixel.png"})
    assert isinstance(result, str)
    assert "image/png" in result.lower()
    assert "1x1" in result


def test_read_media_file_returns_image_blocks_when_supported(workspace: Path) -> None:
    image_bytes = base64.b64decode(PNG_1X1_BASE64)
    (workspace / "pixel.png").write_bytes(image_bytes)
    tool = build_read_media_file_tool(
        workspace,
        media_block_support=MediaBlockSupport(image_blocks=True),
    )
    result = tool.invoke({"path": "pixel.png"})
    assert isinstance(result, list)
    assert result[0]["type"] == "text"
    assert result[1]["type"] == "image"
    assert result[1]["mime_type"] == "image/png"
    assert result[1]["base64"] == base64.b64encode(image_bytes).decode("ascii")


def test_read_media_file_returns_pdf_summary_without_multimodal_support(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (workspace / "doc.pdf").write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF")
    monkeypatch.setattr("src.ai.filesystem.read.get_pdf_page_count", lambda path: 3)
    tool = build_read_media_file_tool(workspace)
    result = tool.invoke({"path": "doc.pdf"})
    assert isinstance(result, str)
    assert "PDF file read" in result
    assert "Pages: 3" in result


def test_read_media_file_returns_pdf_file_block_when_supported(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pdf_bytes = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    (workspace / "doc.pdf").write_bytes(pdf_bytes)
    monkeypatch.setattr("src.ai.filesystem.read.get_pdf_page_count", lambda path: 3)
    tool = build_read_media_file_tool(
        workspace,
        media_block_support=MediaBlockSupport(file_blocks=True),
    )
    result = tool.invoke({"path": "doc.pdf"})
    assert isinstance(result, list)
    assert result[0]["type"] == "text"
    assert result[1]["type"] == "file"
    assert result[1]["mime_type"] == "application/pdf"
    assert result[1]["base64"] == base64.b64encode(pdf_bytes).decode("ascii")


def test_read_media_file_requires_page_range_for_large_pdf(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (workspace / "large.pdf").write_bytes(b"%PDF-1.4\n%%EOF")
    monkeypatch.setattr("src.ai.filesystem.read.get_pdf_page_count", lambda path: 25)
    tool = build_read_media_file_tool(workspace)
    result = tool.invoke({"path": "large.pdf"})
    assert isinstance(result, str)
    assert "too many to read at once" in result
