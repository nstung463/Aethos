from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.messages import AIMessageChunk

from src.config import DeepSeekChatOpenAI


def test_deepseek_payload_passes_reasoning_content_for_tool_call_subturn() -> None:
    model = DeepSeekChatOpenAI(
        model="deepseek-v4-pro",
        api_key="test-key",
        base_url="https://api.deepseek.com",
    )
    messages = [
        HumanMessage(content="Check the date"),
        AIMessage(
            content="",
            additional_kwargs={"reasoning_content": "I need the current date first."},
            tool_calls=[{"id": "call-1", "name": "get_date", "args": {}}],
        ),
        ToolMessage(content="2026-04-29", tool_call_id="call-1"),
    ]

    payload = model._get_request_payload(messages)

    assistant_payload = payload["messages"][1]
    assert assistant_payload["role"] == "assistant"
    assert assistant_payload["reasoning_content"] == "I need the current date first."
    assert assistant_payload["tool_calls"][0]["function"]["name"] == "get_date"


def test_deepseek_payload_passes_reasoning_content_without_tool_calls() -> None:
    model = DeepSeekChatOpenAI(
        model="deepseek-v4-pro",
        api_key="test-key",
        base_url="https://api.deepseek.com",
    )
    messages = [
        HumanMessage(content="Hi"),
        AIMessage(
            content="Hello",
            additional_kwargs={"reasoning_content": "No tool call in this turn."},
        ),
    ]

    payload = model._get_request_payload(messages)

    assert payload["messages"][1]["reasoning_content"] == "No tool call in this turn."


def test_deepseek_non_streaming_result_preserves_reasoning_content() -> None:
    model = DeepSeekChatOpenAI(
        model="deepseek-v4-pro",
        api_key="test-key",
        base_url="https://api.deepseek.com",
    )

    result = model._create_chat_result(
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "I can help.",
                        "reasoning_content": "User wants help.",
                    },
                    "finish_reason": "stop",
                }
            ]
        }
    )

    message = result.generations[0].message
    assert isinstance(message, AIMessage)
    assert message.additional_kwargs["reasoning_content"] == "User wants help."


def test_deepseek_stream_chunk_preserves_reasoning_content() -> None:
    model = DeepSeekChatOpenAI(
        model="deepseek-v4-pro",
        api_key="test-key",
        base_url="https://api.deepseek.com",
    )

    chunk = model._convert_chunk_to_generation_chunk(
        {
            "choices": [
                {
                    "delta": {"role": "assistant", "reasoning_content": "Need a tool."},
                    "finish_reason": None,
                }
            ]
        },
        AIMessageChunk,
        None,
    )

    assert chunk is not None
    assert chunk.message.additional_kwargs["reasoning_content"] == "Need a tool."


def test_deepseek_stream_chunk_accumulates_reasoning_content() -> None:
    model = DeepSeekChatOpenAI(
        model="deepseek-v4-pro",
        api_key="test-key",
        base_url="https://api.deepseek.com",
    )

    first = model._convert_chunk_to_generation_chunk(
        {
            "choices": [
                {
                    "delta": {"role": "assistant", "reasoning_content": "Need "},
                    "finish_reason": None,
                }
            ]
        },
        AIMessageChunk,
        None,
    )
    second = model._convert_chunk_to_generation_chunk(
        {
            "choices": [
                {
                    "delta": {"reasoning_content": "a tool."},
                    "finish_reason": None,
                }
            ]
        },
        AIMessageChunk,
        None,
    )

    assert first is not None
    assert second is not None
    merged = first + second
    assert merged.message.additional_kwargs["reasoning_content"] == "Need a tool."
