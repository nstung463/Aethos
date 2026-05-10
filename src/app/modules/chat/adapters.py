"""Schema adapters and converter utilities for chat messages and paths."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.app.modules.chat.schemas import Message
from src.ai.tools.session import PRESENT_OUTPUT_FILE_MARKER


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


def sanitize_tool_input(input_data: Any) -> Any:
    """Recursively strip non-JSON-serializable values (e.g. injected ToolRuntime) from tool inputs."""
    if isinstance(input_data, dict):
        result: dict[str, Any] = {}
        for k, v in input_data.items():
            try:
                json.dumps(v)
                result[k] = v
            except (TypeError, ValueError):
                sanitized = sanitize_tool_input(v)
                try:
                    json.dumps(sanitized)
                    result[k] = sanitized
                except (TypeError, ValueError):
                    pass
        return result
    if isinstance(input_data, (list, tuple)):
        clean = []
        for item in input_data:
            try:
                json.dumps(item)
                clean.append(item)
            except (TypeError, ValueError):
                pass
        return clean
    return input_data


def format_tool_input(input_data: Any) -> str:
    """Format tool input parameters for human-readable streaming annotations."""
    if not input_data:
        return ""
    clean = sanitize_tool_input(input_data)
    if isinstance(clean, dict):
        if len(clean) == 1:
            key, value = next(iter(clean.items()))
            return f"{key}={json.dumps(value) if not isinstance(value, str) else value}"
        return json.dumps(clean)
    return str(clean)


def extract_tool_output(output: Any) -> str:
    """Extract string content from a tool output, handling LangChain ToolMessage objects.

    ``str(ToolMessage)`` yields ``content='...' name='...' tool_call_id='...'`` which
    is the Python repr — not useful for display.  This helper extracts only the
    human-readable content field instead.
    """
    if hasattr(output, "content"):
        return extract_text(output.content)
    return str(output)


_SHELL_TOOLS: frozenset[str] = frozenset({"bash", "powershell"})


def get_tool_display_label(tool_name: str, tool_input: Any) -> str | None:
    """Return the 'description' field from bash/powershell input as a display label."""
    if tool_name not in _SHELL_TOOLS:
        return None
    if not isinstance(tool_input, dict):
        return None
    description = tool_input.get("description")
    if description and isinstance(description, str):
        return description.strip() or None
    return None


def summarize_tool_input(tool_name: str, tool_input: Any) -> str:
    """Return a concise UI label for a tool invocation."""
    display_label = get_tool_display_label(tool_name, tool_input)
    if display_label:
        return display_label
    if isinstance(tool_input, dict):
        for key in ("command", "path", "pattern", "query", "url"):
            value = tool_input.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return format_tool_input(tool_input)


def classify_shell_output(tool_name: str, tool_input: Any, output_text: str) -> dict[str, Any]:
    """Enrich bash/powershell output with collapse/expand metadata for the UI.

    Returns a dict with at minimum: output, collapsed, line_count, classification.
    When collapsed=True, also includes summary and raw_output.
    Non-shell tools receive only: output.
    """
    base: dict[str, Any] = {"output": output_text}
    if tool_name not in _SHELL_TOOLS:
        return base
    try:
        from src.ai.tools.shell.command_classifier import classify_bash_command
        from src.ai.tools.shell.output_formatter import format_bash_output

        command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
        cls = classify_bash_command(command)
        formatted = format_bash_output(output_text, cls)
    except Exception:
        return base
    if cls.is_search:
        kind = "search"
    elif cls.is_list:
        kind = "list"
    elif cls.is_read:
        kind = "read"
    elif cls.is_write:
        kind = "write"
    else:
        kind = "run"
    base["line_count"] = formatted.line_count
    base["classification"] = kind
    if formatted.collapsed:
        base["collapsed"] = True
        base["summary"] = formatted.summary
        base["raw_output"] = output_text
        base["output"] = formatted.summary or output_text
    else:
        base["collapsed"] = False
    return base


def enrich_tool_output(tool_name: str, tool_input: Any, output_text: str) -> dict[str, Any]:
    """Return UI metadata for a completed tool invocation."""
    if tool_name == "present_output_file":
        try:
            payload = json.loads(output_text)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict) and payload.get(PRESENT_OUTPUT_FILE_MARKER) is True:
            message = payload.get("message") if isinstance(payload.get("message"), str) else output_text
            artifact = payload.get("artifact") if isinstance(payload.get("artifact"), dict) else None
            result: dict[str, Any] = {
                "output": message,
                "raw_output": output_text,
                "collapsed": True,
                "classification": "write",
                "summary": message,
            }
            if artifact is not None:
                result["artifact"] = artifact
            return result
    return classify_shell_output(tool_name, tool_input, output_text)


def sandbox_attachment_path(file_id: str, filename: str, attachments_root: str = "/tmp/aethos/attachments") -> str:
    """Build sandbox staging path for an attachment."""
    safe_name = Path(filename).name or file_id
    return f"{attachments_root}/{file_id}/{safe_name}"


def workspace_root_for_backend(backend: Any) -> Path:
    """Extract workspace root from backend object or return root path."""
    root = getattr(backend, "root", None)
    if isinstance(root, Path):
        return root.resolve()
    return Path("/").resolve()
