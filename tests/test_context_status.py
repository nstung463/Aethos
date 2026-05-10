from __future__ import annotations

from src.app.services.context_status import TOOL_SCHEMA_FALLBACK_TOKENS, build_context_status, estimate_tokens


def test_context_status_uses_latest_provider_reported_input_tokens(workspace):
    (workspace / "AGENTS.md").write_text("Project rule", encoding="utf-8")

    status = build_context_status(
        root_dir=str(workspace),
        model="gpt-5",
        messages=[
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "older", "usage": {"prompt_tokens": 111}},
            {"role": "assistant", "content": "newer", "usage": {"input_tokens": 12345}},
        ],
        context_window=100_000,
    )

    assert status["used_tokens"] == 12345
    assert status["percent_used"] == 12
    assert status["is_estimated"] is False
    assert all(category.get("is_scaled_from_provider") is True for category in status["categories"] if category["key"] != "free")


def test_context_status_estimates_structured_content_blocks(workspace):
    plain_status = build_context_status(
        root_dir=str(workspace),
        model="claude-3-5-sonnet",
        messages=[{"role": "user", "content": "short"}],
        context_window=100_000,
    )
    structured_status = build_context_status(
        root_dir=str(workspace),
        model="claude-3-5-sonnet",
        messages=[
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "hidden reasoning" * 100},
                    {"type": "text", "text": "visible answer" * 100},
                    {"type": "tool_use", "name": "read_file", "input": {"path": "src/app.py"}},
                ],
            }
        ],
        context_window=100_000,
    )

    plain_messages = next(category for category in plain_status["categories"] if category["key"] == "messages")
    structured_messages = next(category for category in structured_status["categories"] if category["key"] == "messages")
    expected_minimum = estimate_tokens(("hidden reasoning" * 100) + ("visible answer" * 100))

    assert structured_status["is_estimated"] is True
    assert structured_messages["tokens"] > plain_messages["tokens"]
    assert structured_messages["tokens"] >= expected_minimum


def test_context_status_uses_runtime_tool_schema_tokens(workspace):
    status = build_context_status(
        root_dir=str(workspace),
        model="gpt-5",
        messages=[],
        context_window=100_000,
    )

    tools = next(category for category in status["categories"] if category["key"] == "tools")

    assert tools["source"] == "runtime_schema"
    assert tools["tokens"] > 0
    assert tools["tokens"] != TOOL_SCHEMA_FALLBACK_TOKENS
