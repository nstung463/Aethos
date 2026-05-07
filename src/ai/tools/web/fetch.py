"""web_fetch tool — fetch URL content and return as plain text.

Mirrors WebFetchTool from claude-code-source:
  - Input: url (validated URL), prompt (extraction hint shown to agent)
  - Output: plain-text content (HTML stripped) or error message

Unlike the TypeScript version, we return raw extracted text directly.
The calling agent applies its own reasoning rather than a second LLM call.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from src.ai.filesystem.read import extract_pdf_text_content, get_pdf_page_count

MAX_CONTENT_LENGTH = 100_000  # chars — mirrors TS maxResultSizeChars


class WebFetchInput(BaseModel):
    url: str = Field(description="The URL to fetch content from.")
    prompt: str = Field(
        description=(
            "Describe what information you want to extract from this page. "
            "Example: 'List all API endpoints', 'Summarize the main points'."
        )
    )


def _strip_html(html: str) -> str:
    """Remove HTML tags and decode common entities."""
    # Remove script and style blocks
    html = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove all tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Decode common entities
    for entity, char in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                          ("&nbsp;", " "), ("&quot;", '"'), ("&#39;", "'")]:
        text = text.replace(entity, char)
    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _looks_binary(content: bytes) -> bool:
    if not content:
        return False
    if b"\x00" in content:
        return True
    sample = content[:2048]
    non_text = sum(
        1
        for byte in sample
        if byte not in b"\t\n\r\f\b" and not 32 <= byte <= 126
    )
    return (non_text / max(len(sample), 1)) > 0.30


def _truncate_text(text: str) -> str:
    if len(text) <= MAX_CONTENT_LENGTH:
        return text
    return text[:MAX_CONTENT_LENGTH] + f"\n\n[Truncated: content exceeded {MAX_CONTENT_LENGTH} chars]"


def _render_pdf(url: str, prompt: str, response: httpx.Response, elapsed_ms: int) -> str:
    with TemporaryDirectory(prefix="ethos-web-fetch-pdf-") as tmp_dir:
        pdf_path = Path(tmp_dir) / "document.pdf"
        pdf_path.write_bytes(response.content)
        page_count = get_pdf_page_count(pdf_path)
        text = extract_pdf_text_content(pdf_path)

    text = text.strip()
    if not text:
        text = (
            "This URL returned a PDF document, but no extractable text was found. "
            "Download the file locally and use read_file/read_media_file for page-aware inspection."
        )

    page_line = f"Pages: {page_count}\n" if page_count is not None else ""
    return (
        f"URL: {url}\n"
        f"Status: {response.status_code} {response.reason_phrase}\n"
        f"Content-Type: {response.headers.get('content-type', 'application/pdf')}\n"
        f"Size: {len(response.content)} bytes\n"
        f"{page_line}"
        f"Elapsed: {elapsed_ms}ms\n"
        f"Prompt hint: {prompt}\n\n"
        f"{_truncate_text(text)}"
    )


def _fetch(url: str, prompt: str) -> str:
    if httpx is None:
        return "Error: httpx not installed. Run: pip install httpx"

    start = time.monotonic()
    try:
        response = httpx.get(
            url,
            follow_redirects=True,
            timeout=30.0,
            headers={"User-Agent": "Mozilla/5.0 (compatible; EthosAgent/1.0)"},
        )
    except Exception as exc:
        return f"Fetch error: {exc}"

    elapsed_ms = int((time.monotonic() - start) * 1000)
    code = response.status_code

    if code >= 400:
        return (
            f"HTTP {code} {response.reason_phrase} fetching {url}\n"
            f"(elapsed: {elapsed_ms}ms)"
        )

    content_type = response.headers.get("content-type", "").lower()
    if "application/pdf" in content_type or response.content.startswith(b"%PDF-"):
        return _render_pdf(url, prompt, response, elapsed_ms)

    if _looks_binary(response.content):
        return (
            f"URL: {url}\n"
            f"Status: {code} {response.reason_phrase}\n"
            f"Content-Type: {content_type or 'application/octet-stream'}\n"
            f"Size: {len(response.content)} bytes\n"
            f"Elapsed: {elapsed_ms}ms\n"
            f"Prompt hint: {prompt}\n\n"
            "This URL returned binary content, so web_fetch did not inline raw bytes into the context. "
            "Download it locally and inspect it with a file-aware tool instead."
        )

    raw = response.text
    if "html" in content_type or raw.lstrip().startswith("<"):
        text = _strip_html(raw)
    else:
        text = raw  # JSON, plain text, etc.

    text = _truncate_text(text)

    return (
        f"URL: {url}\n"
        f"Status: {code} {response.reason_phrase}\n"
        f"Content-Type: {content_type or 'text/plain'}\n"
        f"Size: {len(response.content)} bytes\n"
        f"Elapsed: {elapsed_ms}ms\n"
        f"Prompt hint: {prompt}\n\n"
        f"{text}"
    )


web_fetch_tool = StructuredTool.from_function(
    name="web_fetch",
    func=_fetch,
    description=(
        "Fetch and extract text content from a URL. "
        "Use for reading documentation, web pages, or any URL the agent needs to inspect. "
        "HTML is stripped to plain text. Content is truncated at 100K chars."
    ),
    args_schema=WebFetchInput,
)
