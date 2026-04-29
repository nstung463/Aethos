"""Schema adapters and converter utilities for chat messages and paths."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.app.modules.chat.schemas import Message


def to_lc_messages(messages: list[Message]) -> list[Any]:
    """Convert Message schema objects to LangChain message types."""
    result = []
    for message in messages:
        if message.role == "assistant" and not message.content.strip() and not (message.reasoning_content or "").strip():
            continue
        if message.role == "system":
            result.append(SystemMessage(content=message.content))
        elif message.role == "assistant":
            reasoning = (message.reasoning_content or "").strip()
            additional_kwargs = {"reasoning_content": reasoning} if reasoning else {}
            result.append(AIMessage(content=message.content, additional_kwargs=additional_kwargs))
        elif message.role == "tool":
            if not message.tool_call_id:
                continue
            result.append(ToolMessage(content=message.content, tool_call_id=message.tool_call_id))
        else:
            result.append(HumanMessage(content=message.content))
    return result


def parse_content(content: Any) -> tuple[str, str]:
    """Split content into plain text and thinking parts.

    Returns:
        (text, thinking) tuple
    """
    if isinstance(content, str):
        return content, ""
    if not isinstance(content, list):
        return str(content), ""

    text_parts: list[str] = []
    thinking_parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            text_parts.append(str(block))
            continue
        block_type = block.get("type", "")
        if block_type == "thinking":
            thinking_parts.append(block.get("thinking", ""))
        elif block_type == "text":
            text_parts.append(block.get("text", ""))

    return "".join(text_parts), "".join(thinking_parts)


def extract_text(content: Any) -> str:
    """Extract only the plain text part from content."""
    text, _ = parse_content(content)
    return text


def extract_reasoning_from_chunk(chunk: Any) -> str:
    """Extract provider-specific reasoning content from a LangChain chunk."""
    additional_kwargs = getattr(chunk, "additional_kwargs", None)
    if isinstance(additional_kwargs, dict):
        reasoning_content = additional_kwargs.get("reasoning_content")
        if isinstance(reasoning_content, str):
            return reasoning_content
    return ""


def format_tool_input(input_data: Any) -> str:
    """Format tool input parameters for human-readable streaming annotations."""
    if not input_data:
        return ""
    if isinstance(input_data, dict):
        if len(input_data) == 1:
            key, value = next(iter(input_data.items()))
            return f"{key}={json.dumps(value) if not isinstance(value, str) else value}"
        return json.dumps(input_data)
    return str(input_data)


def sandbox_attachment_path(file_id: str, filename: str, attachments_root: str = "/tmp/ethos/attachments") -> str:
    """Build sandbox staging path for an attachment."""
    safe_name = Path(filename).name or file_id
    return f"{attachments_root}/{file_id}/{safe_name}"


def workspace_root_for_backend(backend: Any) -> Path:
    """Extract workspace root from backend object or return root path."""
    root = getattr(backend, "root", None)
    if isinstance(root, Path):
        return root.resolve()
    return Path("/").resolve()
