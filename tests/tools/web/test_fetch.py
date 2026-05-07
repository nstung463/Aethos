"""Tests for web_fetch tool â€” uses httpx mock."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


def _make_response(status=200, text="<html><body><p>Hello world</p></body></html>", headers=None):
    resp = MagicMock()
    resp.status_code = status
    resp.reason_phrase = "OK" if status == 200 else "Not Found"
    resp.text = text
    resp.content = text.encode()
    resp.headers = headers or {"content-type": "text/html"}
    return resp


def test_fetch_returns_content() -> None:
    with patch("src.ai.tools.web.fetch.httpx") as mock_httpx:
        mock_httpx.get.return_value = _make_response()
        from src.ai.tools.web.fetch import web_fetch_tool
        result = web_fetch_tool.invoke({"url": "https://example.com", "prompt": "what is this?"})
        assert "Hello world" in result
        mock_httpx.get.assert_called_once()


def test_fetch_http_error() -> None:
    with patch("src.ai.tools.web.fetch.httpx") as mock_httpx:
        mock_httpx.get.return_value = _make_response(status=404, text="Not Found")
        from src.ai.tools.web.fetch import web_fetch_tool
        result = web_fetch_tool.invoke({"url": "https://example.com/missing", "prompt": "content"})
        assert "404" in result


def test_fetch_network_error() -> None:
    import httpx as real_httpx
    with patch("src.ai.tools.web.fetch.httpx") as mock_httpx:
        mock_httpx.get.side_effect = Exception("refused")
        from src.ai.tools.web.fetch import web_fetch_tool
        result = web_fetch_tool.invoke({"url": "https://example.com", "prompt": "x"})
        assert "error" in result.lower() or "failed" in result.lower() or "refused" in result.lower()


def test_fetch_includes_prompt_hint() -> None:
    with patch("src.ai.tools.web.fetch.httpx") as mock_httpx:
        mock_httpx.get.return_value = _make_response(text="<html><body>Content</body></html>")
        from src.ai.tools.web.fetch import web_fetch_tool
        result = web_fetch_tool.invoke({"url": "https://example.com", "prompt": "find the title"})
        assert "find the title" in result


def test_fetch_extracts_pdf_text_instead_of_returning_binary() -> None:
    pdf_bytes = b"%PDF-1.4\nfake pdf bytes"
    response = _make_response(
        text="%PDF-1.4",
        headers={"content-type": "application/pdf"},
    )
    response.content = pdf_bytes
    with (
        patch("src.ai.tools.web.fetch.httpx") as mock_httpx,
        patch("src.ai.tools.web.fetch.get_pdf_page_count", return_value=9),
        patch("src.ai.tools.web.fetch.extract_pdf_text_content", return_value="Alphabet revenue grew 12%."),
    ):
        mock_httpx.get.return_value = response
        from src.ai.tools.web.fetch import web_fetch_tool
        result = web_fetch_tool.invoke({"url": "https://example.com/report.pdf", "prompt": "summarize"})
        assert "application/pdf" in result
        assert "Pages: 9" in result
        assert "Alphabet revenue grew 12%." in result
        assert "fake pdf bytes" not in result


def test_fetch_returns_binary_notice_for_non_pdf_binary_content() -> None:
    response = _make_response(
        text="",
        headers={"content-type": "application/octet-stream"},
    )
    response.content = b"\x00\x01\x02binary"
    response.text = "\x00\x01\x02binary"
    with patch("src.ai.tools.web.fetch.httpx") as mock_httpx:
        mock_httpx.get.return_value = response
        from src.ai.tools.web.fetch import web_fetch_tool
        result = web_fetch_tool.invoke({"url": "https://example.com/blob.bin", "prompt": "inspect"})
        assert "binary content" in result.lower()
        assert "did not inline raw bytes" in result


def test_strip_html_removes_tags() -> None:
    from src.ai.tools.web.fetch import _strip_html
    result = _strip_html("<h1>Title</h1><p>Body text</p>")
    assert "Title" in result
    assert "Body text" in result
    assert "<h1>" not in result
    assert "<p>" not in result


def test_strip_html_removes_scripts() -> None:
    from src.ai.tools.web.fetch import _strip_html
    result = _strip_html("<script>alert('x')</script><p>Hello</p>")
    assert "alert" not in result
    assert "Hello" in result


def test_strip_html_decodes_entities() -> None:
    from src.ai.tools.web.fetch import _strip_html
    result = _strip_html("&amp; &lt; &gt; &nbsp;")
    assert "&" in result
    assert "<" in result
    assert ">" in result

