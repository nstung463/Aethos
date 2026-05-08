from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient

from src.app import create_app
from src.app.modules.chat.service import ChatService
from src.backends.local import LocalSandbox as LocalBackend


def test_thread_message_loader_reads_direct_reasoning_content() -> None:
    text, reasoning = ChatService._message_text_and_reasoning(
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


def test_thread_message_loader_deduplicates_reasoning_blocks() -> None:
    text, reasoning = ChatService._message_text_and_reasoning(
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


def test_thread_message_loader_ignores_tool_narration_in_reasoning_field() -> None:
    text, reasoning = ChatService._message_text_and_reasoning(
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


def test_streaming_tool_events_use_tool_event_channel_without_reasoning_narration(tmp_path: Path) -> None:
    with TestClient(create_app()) as client:
        auth_response = client.post("/auth/guest", json={})
        assert auth_response.status_code == 200
        auth_headers = {"Authorization": f"Bearer {auth_response.json()['access_token']}"}
        thread_id = client.post("/v1/threads", headers=auth_headers).json()["id"]

        class _FakeAgent:
            async def astream_events(self, payload, config: dict | None = None, version: str | None = None):
                yield {
                    "event": "on_tool_start",
                    "name": "powershell",
                    "run_id": "call-shell",
                    "data": {"input": {"command": "Get-Location"}},
                }
                yield {
                    "event": "on_tool_end",
                    "name": "powershell",
                    "run_id": "call-shell",
                    "data": {"output": "Exit code: 0\nW:/panus/aethos"},
                }

            async def aget_state(self, config):
                class _Snap:
                    tasks = []

                return _Snap()

        client.app.state.daytona_manager = type(
            "Manager",
            (),
            {
                "get_backend": lambda self, _thread_id: LocalBackend(str(tmp_path / "workspace")),
                "shutdown": lambda self: None,
            },
        )()

        with (
            patch("src.app.modules.chat.service.build_chat_model", return_value=object()),
            patch("src.app.modules.chat.service.create_aethos_agent", return_value=_FakeAgent()),
        ):
            with client.stream(
                "POST",
                "/v1/chat/completions",
                json={
                    "model": "aethos",
                    "thread_id": thread_id,
                    "stream": True,
                    "messages": [{"role": "user", "content": "Run a command"}],
                },
                headers=auth_headers,
                ) as response:
                    assert response.status_code == 200
                    body = "".join(response.iter_text())

    payloads = [
        json.loads(line[len("data: "):])
        for line in body.splitlines()
        if line.startswith("data: ") and line != "data: [DONE]"
    ]
    tool_deltas = [
        payload["choices"][0]["delta"]["tool_event"]
        for payload in payloads
        if payload["choices"][0]["delta"].get("tool_event")
    ]

    assert tool_deltas[0]["step_id"] == "step_tool_call-shell"
    assert "Get-Location" in tool_deltas[0]["summary"]
    assert 'Using tool `powershell`' not in body
