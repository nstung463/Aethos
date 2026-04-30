from __future__ import annotations

from src.app.modules.chat.service import ChatService


def test_thread_message_loader_reads_direct_reasoning_content() -> None:
    text, reasoning, tool_events = ChatService._message_text_and_reasoning(
        {
            "message": {
                "role": "assistant",
                "reasoning_content": "Need to inspect the workbook first.",
                "content": [{"type": "text", "text": "Using a tool."}],
            }
        }
    )

    assert text == "Using a tool."
    assert reasoning == "Need to inspect the workbook first."
    assert tool_events == []


def test_thread_message_loader_deduplicates_reasoning_blocks() -> None:
    text, reasoning, _ = ChatService._message_text_and_reasoning(
        {
            "message": {
                "role": "assistant",
                "reasoning_content": "Need to inspect the workbook first.",
                "content": [
                    {"type": "text", "text": "Using a tool."},
                    {"type": "thinking", "thinking": "Need to inspect the workbook first."},
                ],
            }
        }
    )

    assert text == "Using a tool."
    assert reasoning == "Need to inspect the workbook first."


def test_thread_message_loader_keeps_tool_use_rows_visible() -> None:
    text, reasoning, tool_events = ChatService._message_text_and_reasoning(
        {
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "call-1",
                        "name": "list_files",
                        "input": {"path": "."},
                    }
                ],
            }
        }
    )

    assert text == ""
    assert reasoning is None
    assert tool_events == ["Using tool `list_files`"]
