"""Test tool input formatting for streaming."""

from src.app.modules.chat.adapters import format_tool_input as _format_tool_input


def test_format_tool_input_with_dict() -> None:
    """Test formatting dict input with single key."""
    result = _format_tool_input({"query": "hello world"})
    assert result == 'query=hello world'


def test_format_tool_input_with_multiple_keys() -> None:
    """Test formatting dict input with multiple keys."""
    result = _format_tool_input({"query": "hello", "max": 5})
    assert "query" in result and "hello" in result and "max" in result


def test_format_tool_input_with_complex_value() -> None:
    """Test formatting dict with complex value."""
    result = _format_tool_input({"path": "/home/user", "mode": "read"})
    assert "path" in result or "mode" in result


def test_format_tool_input_empty() -> None:
    """Test formatting empty input."""
    assert _format_tool_input({}) == ""
    assert _format_tool_input(None) == ""


def test_format_tool_input_string() -> None:
    """Test formatting string input."""
    result = _format_tool_input("test query")
    assert result == "test query"
