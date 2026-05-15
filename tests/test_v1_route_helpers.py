from __future__ import annotations

from src.app.features.chat.request_parser import (
    extract_file_ids as _extract_file_ids,
    extract_requested_thread_id as _extract_requested_thread_id,
    extract_user_api_keys as _extract_user_api_keys,
)
from src.app.features.chat.schemas import ChatRequest, Message


def test_extract_file_ids_supports_openwebui_files_shape() -> None:
    request = ChatRequest(
        model="aethos",
        messages=[Message(role="user", content="hi")],
        file_ids=["a"],
        files=[
            {"id": "b"},
            {"file": {"id": "c"}},
            {"id": "a"},
        ],
        metadata={"file_ids": ["d", "c"]},
    )

    assert _extract_file_ids(request) == ["a", "b", "c", "d"]


def test_extract_requested_thread_id_prefers_thread_id_then_chat_id_then_session_id_then_metadata() -> None:
    request = ChatRequest(
        model="aethos",
        messages=[Message(role="user", content="hi")],
        thread_id="thread-1",
        session_id="session-1",
        chat_id="chat-1",
        metadata={"conversation_id": "conv-1"},
    )
    assert _extract_requested_thread_id(request) == "thread-1"

    request = ChatRequest(
        model="aethos",
        messages=[Message(role="user", content="hi")],
        chat_id="chat-2",
    )
    assert _extract_requested_thread_id(request) == "chat-2"

    request = ChatRequest(
        model="aethos",
        messages=[Message(role="user", content="hi")],
        session_id="session-3",
    )
    assert _extract_requested_thread_id(request) == "session-3"

    request = ChatRequest(
        model="aethos",
        messages=[Message(role="user", content="hi")],
        metadata={"conversation_id": "conv-3"},
    )
    assert _extract_requested_thread_id(request) == "conv-3"


def test_extract_user_api_keys_reads_only_expected_string_values() -> None:
    request = ChatRequest(
        model="aethos",
        messages=[Message(role="user", content="hi")],
        metadata={
            "user_api_keys": {
                "openrouter": " sk-or-v1-test ",
                "anthropic": "sk-ant-test",
                "openai": 123,
                "ignored": "value",
            }
        },
    )

    assert _extract_user_api_keys(request) == {
        "openrouter": "sk-or-v1-test",
        "anthropic": "sk-ant-test",
    }
