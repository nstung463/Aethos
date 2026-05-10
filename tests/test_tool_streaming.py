"""Test tool parameter streaming in chat responses."""

import json
import uuid
from src.app.modules.chat.streaming import sse as _sse
from src.app.modules.chat.adapters import enrich_tool_output, format_tool_input as _format_tool_input
from src.ai.tools.session import PRESENT_OUTPUT_FILE_MARKER


def test_sse_format_with_tool_params() -> None:
    """Test that SSE format correctly includes tool parameters."""
    params = _format_tool_input({"query": "search results", "limit": 10})
    reasoning = f"Using tool `search_web` with params: {params}\n"

    result = _sse({"reasoning_content": reasoning}, model="test-model")

    # Verify SSE format
    assert result.startswith("data: ")
    assert "[DONE]" not in result

    # Parse JSON payload
    json_str = result.replace("data: ", "").strip()
    payload = json.loads(json_str)

    # Verify structure
    assert payload["object"] == "chat.completion.chunk"
    assert payload["model"] == "test-model"
    assert payload["choices"][0]["delta"]["reasoning_content"] == reasoning
    assert "search_web" in payload["choices"][0]["delta"]["reasoning_content"]
    assert "query" in payload["choices"][0]["delta"]["reasoning_content"]


def test_sse_format_without_params() -> None:
    """Test SSE format when tool has no parameters."""
    reasoning = "Using tool `no_args_tool`\n"
    result = _sse({"reasoning_content": reasoning}, model="test-model")

    json_str = result.replace("data: ", "").strip()
    payload = json.loads(json_str)

    assert "no_args_tool" in payload["choices"][0]["delta"]["reasoning_content"]
    assert "params:" not in payload["choices"][0]["delta"]["reasoning_content"]


def test_tool_event_simulation() -> None:
    """Simulate what happens with a real on_tool_start event."""
    # Simulate LangGraph event structure
    event = {
        "event": "on_tool_start",
        "data": {
            "input": {
                "query": "python tutorial",
                "max_results": 5
            }
        },
        "name": "web_search",
        "run_id": str(uuid.uuid4())
    }

    # Extract and format like the router does
    tool_name = event.get("name", "tool")
    tool_input = event.get("data", {}).get("input", {})
    input_str = _format_tool_input(tool_input)

    assert tool_name == "web_search"
    assert "query" in input_str
    assert "python tutorial" in input_str
    assert "max_results" in input_str or "5" in input_str


def test_present_output_file_tool_output_adds_artifact_metadata() -> None:
    output = json.dumps(
        {
            PRESENT_OUTPUT_FILE_MARKER: True,
            "message": "Presented output file: report.xlsx",
            "artifact": {
                "file_id": "file_1",
                "filename": "report.xlsx",
                "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "size": 123,
                "artifact_type": "spreadsheet",
                "title": "Q1 report",
                "description": "Final workbook",
                "content_url": "/api/files/file_1/content",
            },
        }
    )

    meta = enrich_tool_output("present_output_file", {"path": "report.xlsx"}, output)

    assert meta["output"] == "Presented output file: report.xlsx"
    assert meta["summary"] == "Presented output file: report.xlsx"
    assert meta["classification"] == "write"
    assert meta["artifact"]["file_id"] == "file_1"
