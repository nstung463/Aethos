from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from langchain_core.messages import AIMessage
from starlette.testclient import TestClient

from src.app import create_app
from src.app.features.chat.service import ChatService
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
            patch("src.app.features.chat.service.build_chat_model", return_value=object()),
            patch("src.app.features.chat.service.create_aethos_agent", return_value=_FakeAgent()),
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


def test_non_streaming_continuation_nudge_reinvokes_agent(tmp_path: Path) -> None:
    with TestClient(create_app()) as client:
        auth_response = client.post("/auth/guest", json={})
        assert auth_response.status_code == 200
        auth_headers = {"Authorization": f"Bearer {auth_response.json()['access_token']}"}
        calls: list[object] = []

        class _FakeAgent:
            async def ainvoke(self, payload, config=None):
                calls.append(payload)
                if len(calls) == 1:
                    return {"messages": [AIMessage(content="I'll inspect the code now")]}
                return {"messages": [AIMessage(content="done")]}

        client.app.state.daytona_manager = type(
            "Manager",
            (),
            {
                "get_backend": lambda self, _thread_id: LocalBackend(str(tmp_path / "workspace")),
                "shutdown": lambda self: None,
            },
        )()

        with (
            patch("src.app.features.chat.service.build_chat_model", return_value=object()),
            patch("src.app.features.chat.service.create_aethos_agent", return_value=_FakeAgent()),
        ):
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "aethos",
                    "stream": False,
                    "messages": [{"role": "user", "content": "Inspect and continue"}],
                },
                headers=auth_headers,
            )

    assert response.status_code == 200
    assert len(calls) == 2


def test_non_streaming_continuation_nudge_stops_after_cap(tmp_path: Path) -> None:
    with TestClient(create_app()) as client:
        auth_response = client.post("/auth/guest", json={})
        assert auth_response.status_code == 200
        auth_headers = {"Authorization": f"Bearer {auth_response.json()['access_token']}"}
        workspace = tmp_path / "workspace"
        (workspace / ".aethos").mkdir(parents=True)
        (workspace / ".aethos" / "settings.json").write_text(
            json.dumps({"agentLoop": {"continuationNudgeLimit": 1}}),
            encoding="utf-8",
        )

        class _FakeAgent:
            async def ainvoke(self, payload, config=None):
                return {"messages": [AIMessage(content="I'll inspect the code now")]}

        client.app.state.daytona_manager = type(
            "Manager",
            (),
            {
                "get_backend": lambda self, _thread_id: LocalBackend(str(workspace)),
                "shutdown": lambda self: None,
            },
        )()

        with (
            patch("src.app.features.chat.service.build_chat_model", return_value=object()),
            patch("src.app.features.chat.service.create_aethos_agent", return_value=_FakeAgent()),
        ):
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "aethos",
                    "stream": False,
                    "messages": [{"role": "user", "content": "Inspect and continue"}],
                },
                headers=auth_headers,
            )

    assert response.status_code == 200
    payload = response.json()
    assert payload["choices"][0]["stop_reason"] == "continuation_nudge_limit"


def test_streaming_continuation_nudge_reinvokes_agent(tmp_path: Path) -> None:
    with TestClient(create_app()) as client:
        auth_response = client.post("/auth/guest", json={})
        assert auth_response.status_code == 200
        auth_headers = {"Authorization": f"Bearer {auth_response.json()['access_token']}"}
        calls: list[object] = []

        class _FakeAgent:
            async def astream_events(self, payload, config: dict | None = None, version: str | None = None):
                calls.append(payload)
                if len(calls) == 1:
                    yield {
                        "event": "on_chat_model_stream",
                        "data": {"chunk": AIMessage(content="I'll inspect the code now")},
                    }
                else:
                    yield {
                        "event": "on_tool_start",
                        "name": "read_file",
                        "run_id": f"tool-{len(calls)}",
                        "data": {"input": {"path": "src/app.py"}},
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
            patch("src.app.features.chat.service.build_chat_model", return_value=object()),
            patch("src.app.features.chat.service.create_aethos_agent", return_value=_FakeAgent()),
        ):
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "aethos",
                    "stream": True,
                    "messages": [{"role": "user", "content": "Inspect and continue"}],
                },
                headers=auth_headers,
            )

    assert response.status_code == 200
    assert len(calls) == 2


def test_streaming_continuation_nudge_stops_after_cap(tmp_path: Path) -> None:
    with TestClient(create_app()) as client:
        auth_response = client.post("/auth/guest", json={})
        assert auth_response.status_code == 200
        auth_headers = {"Authorization": f"Bearer {auth_response.json()['access_token']}"}
        workspace = tmp_path / "workspace"
        (workspace / ".aethos").mkdir(parents=True)
        (workspace / ".aethos" / "settings.json").write_text(
            json.dumps({"agentLoop": {"continuationNudgeLimit": 1}}),
            encoding="utf-8",
        )

        class _FakeAgent:
            async def astream_events(self, payload, config: dict | None = None, version: str | None = None):
                yield {
                    "event": "on_chat_model_stream",
                    "data": {"chunk": AIMessage(content="I'll inspect the code now")},
                }

            async def aget_state(self, config):
                class _Snap:
                    tasks = []

                return _Snap()

        client.app.state.daytona_manager = type(
            "Manager",
            (),
            {
                "get_backend": lambda self, _thread_id: LocalBackend(str(workspace)),
                "shutdown": lambda self: None,
            },
        )()

        with (
            patch("src.app.features.chat.service.build_chat_model", return_value=object()),
            patch("src.app.features.chat.service.create_aethos_agent", return_value=_FakeAgent()),
        ):
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "aethos",
                    "stream": True,
                    "messages": [{"role": "user", "content": "Inspect and continue"}],
                },
                headers=auth_headers,
            )

    assert response.status_code == 200
    chunks = [
        json.loads(line[len("data: "):])
        for line in response.text.splitlines()
        if line.startswith("data: ") and line != "data: [DONE]"
    ]
    assert chunks[-1]["choices"][0]["delta"]["stop_reason"] == "continuation_nudge_limit"


def test_streaming_continuation_nudge_cap_persists_interrupted_status(tmp_path: Path) -> None:
    with TestClient(create_app()) as client:
        auth_response = client.post("/auth/guest", json={})
        assert auth_response.status_code == 200
        auth_headers = {"Authorization": f"Bearer {auth_response.json()['access_token']}"}
        workspace = tmp_path / "workspace"
        (workspace / ".aethos").mkdir(parents=True)
        (workspace / ".aethos" / "settings.json").write_text(
            json.dumps({"agentLoop": {"continuationNudgeLimit": 1}}),
            encoding="utf-8",
        )
        thread_id = client.post("/v1/threads", headers=auth_headers).json()["id"]

        class _FakeAgent:
            async def astream_events(self, payload, config: dict | None = None, version: str | None = None):
                yield {
                    "event": "on_chat_model_stream",
                    "data": {"chunk": AIMessage(content="I'll inspect the code now")},
                }

            async def aget_state(self, config):
                class _Snap:
                    tasks = []

                return _Snap()

        client.app.state.daytona_manager = type(
            "Manager",
            (),
            {
                "get_backend": lambda self, _thread_id: LocalBackend(str(workspace)),
                "shutdown": lambda self: None,
            },
        )()

        with (
            patch("src.app.features.chat.service.build_chat_model", return_value=object()),
            patch("src.app.features.chat.service.create_aethos_agent", return_value=_FakeAgent()),
        ):
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "aethos",
                    "thread_id": thread_id,
                    "stream": True,
                    "messages": [{"role": "user", "content": "Inspect and continue"}],
                },
                headers=auth_headers,
            )
            assert response.status_code == 200
            thread_response = client.get(f"/v1/threads/{thread_id}", headers=auth_headers)

    payload = thread_response.json()
    assert payload["status"] == "interrupted"
    assert payload["last_stop_reason"] == "continuation_nudge_limit"


from types import SimpleNamespace

from src.app.core.settings import Settings
from src.app.features.chat.schemas import ChatRequest, Message


def test_build_backend_returns_local_backend_for_local_mode(tmp_path, monkeypatch) -> None:
    service = ChatService(
        auth_repo=SimpleNamespace(),
        thread_store=SimpleNamespace(),
        daytona_manager=SimpleNamespace(get_backend=lambda _thread_id: object()),
        checkpointer=SimpleNamespace(),
        settings=Settings(),
    )
    request = ChatRequest(
        messages=[Message(role="user", content="hello")],
        metadata={"backend": {"mode": "local", "root_dir": str(tmp_path)}},
    )

    backend = service.build_backend(request, "thread-1")

    assert isinstance(backend, LocalBackend)
    assert backend.root == tmp_path.resolve()


def test_build_backend_returns_daytona_backend_for_sandbox_mode() -> None:
    sentinel = object()
    service = ChatService(
        auth_repo=SimpleNamespace(),
        thread_store=SimpleNamespace(),
        daytona_manager=SimpleNamespace(get_backend=lambda _thread_id: sentinel),
        checkpointer=SimpleNamespace(),
        settings=Settings(),
    )
    request = ChatRequest(messages=[Message(role="user", content="hello")])

    backend = service.build_backend(request, "thread-1")

    assert backend is sentinel
