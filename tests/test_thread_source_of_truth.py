from __future__ import annotations

import asyncio
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.base import empty_checkpoint
from starlette.testclient import TestClient

from src.app import create_app
from src.app.core.settings import get_settings


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/auth/guest", json={})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_threads_endpoint_reads_messages_from_backend_checkpoints(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ETHOS_CHECKPOINTS_DIR", str(tmp_path / "checkpoints"))
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        headers = _auth_headers(client)
        thread = client.post("/v1/threads", headers=headers).json()
        thread_id = thread["id"]

        checkpoint = empty_checkpoint()
        checkpoint["id"] = "cp-1"
        checkpoint["channel_values"] = {
            "messages": [
                HumanMessage(content="hello from backend"),
                AIMessage(content="stored answer"),
            ]
        }
        asyncio.run(
            client.app.state.checkpointer.aput(
                {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}},
                checkpoint,
                {"step": 1},
                {},
            )
        )

        response = client.get(f"/v1/threads/{thread_id}", headers=headers)
        listed = client.get("/v1/threads", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == thread_id
    assert [message["role"] for message in body["messages"]] == ["user", "assistant"]
    assert body["messages"][0]["content"] == "hello from backend"
    assert body["messages"][1]["content"] == "stored answer"
    assert listed.status_code == 200
    assert listed.json()["threads"][0]["messages"] == []


def test_thread_metadata_update_and_delete_are_server_backed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ETHOS_CHECKPOINTS_DIR", str(tmp_path / "checkpoints"))
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        headers = _auth_headers(client)
        thread_id = client.post("/v1/threads", headers=headers).json()["id"]

        updated = client.patch(
            f"/v1/threads/{thread_id}",
            headers=headers,
            json={"title": "Backend-owned thread"},
        )
        listed = client.get("/v1/threads", headers=headers)
        deleted = client.delete(f"/v1/threads/{thread_id}", headers=headers)
        missing = client.get(f"/v1/threads/{thread_id}", headers=headers)

    assert updated.status_code == 200
    assert updated.json()["title"] == "Backend-owned thread"
    assert listed.status_code == 200
    assert listed.json()["threads"][0]["id"] == thread_id
    assert listed.json()["threads"][0]["title"] == "Backend-owned thread"
    assert deleted.status_code == 200
    assert missing.status_code == 404


def test_thread_detail_skips_tool_result_only_messages(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ETHOS_CHECKPOINTS_DIR", str(tmp_path / "checkpoints"))
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        headers = _auth_headers(client)
        thread_id = client.post("/v1/threads", headers=headers).json()["id"]

        checkpoint = empty_checkpoint()
        checkpoint["id"] = "cp-tool"
        checkpoint["channel_values"] = {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[{"id": "call-1", "name": "list_files", "args": {"path": "."}}],
                ),
                ToolMessage(content="README.md", tool_call_id="call-1"),
                AIMessage(content="done"),
            ]
        }
        asyncio.run(
            client.app.state.checkpointer.aput(
                {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}},
                checkpoint,
                {"step": 1},
                {},
            )
        )

        response = client.get(f"/v1/threads/{thread_id}", headers=headers)

    assert response.status_code == 200
    messages = response.json()["messages"]
    assert [message["role"] for message in messages] == ["assistant", "assistant"]
    assert all(message["content"] or message["tool_events"] for message in messages)


def test_thread_ui_metadata_persists_on_backend(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ETHOS_CHECKPOINTS_DIR", str(tmp_path / "checkpoints"))
    get_settings.cache_clear()

    with TestClient(create_app()) as client:
        headers = _auth_headers(client)
        thread_id = client.post("/v1/threads", headers=headers).json()["id"]
        response = client.patch(
            f"/v1/threads/{thread_id}",
            headers=headers,
            json={
                "title": "Review session",
                "model": "claude-test",
                "mode": "review",
                "profile_id": "profile-1",
                "project": "Ethos",
                "is_favorite": True,
            },
        )
        detail = client.get(f"/v1/threads/{thread_id}", headers=headers)

    assert response.status_code == 200
    assert detail.status_code == 200
    body = detail.json()
    assert body["title"] == "Review session"
    assert body["model"] == "claude-test"
    assert body["mode"] == "review"
    assert body["profile_id"] == "profile-1"
    assert body["project"] == "Ethos"
    assert body["is_favorite"] is True
