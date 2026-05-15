from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage
from langgraph.errors import GraphInterrupt, GraphRecursionError
from langgraph.types import Command
from starlette.testclient import TestClient

from src.ai.permissions import PermissionMode
from src.app import create_app
from src.app.api.dependencies import get_auth_repository, get_thread_store
from src.app.features.chat.service import _resolve_resume_input
from src.app.features.chat.loop_guards import DEFAULT_GRAPH_RECURSION_LIMIT, GRAPH_RECURSION_STOP_REASON
from src.app.services.postgres_checkpointer import PostgresCheckpointSaver
from src.backends.daytona import DaytonaUnavailableError
from src.backends.local import LocalSandbox as LocalBackend


@pytest.fixture()
def client(postgres_database: str) -> TestClient:
    # Must use context manager: TestClient(...) as c triggers app lifespan,
    # which sets app.state.checkpointer (required for interrupt state sharing).
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture()
def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/auth/guest", json={})
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_user_permission_defaults_round_trip(client: TestClient, auth_headers: dict[str, str]) -> None:
    initial = client.get("/auth/me/permissions", headers=auth_headers)
    assert initial.status_code == 200
    assert initial.json() == {"mode": None, "working_directories": [], "rules": []}

    payload = {
        "mode": "accept_edits",
        "working_directories": ["src"],
        "rules": [
            {"subject": "edit", "behavior": "allow", "matcher": "docs/**"},
        ],
    }
    updated = client.put("/auth/me/permissions", json=payload, headers=auth_headers)

    assert updated.status_code == 200
    assert updated.json() == payload


def test_thread_permission_overlay_persists_for_thread(client: TestClient, auth_headers: dict[str, str]) -> None:
    thread = client.post("/v1/threads", headers=auth_headers)
    assert thread.status_code == 200
    thread_id = thread.json()["id"]

    payload = {
        "mode": "bypass_permissions",
        "working_directories": ["sandbox/project"],
        "rules": [
            {"subject": "bash", "behavior": "allow", "matcher": "git status*"},
        ],
    }
    updated = client.patch(f"/v1/threads/{thread_id}/permissions", json=payload, headers=auth_headers)

    assert updated.status_code == 200
    body = updated.json()
    assert body["overlay"] == payload
    assert body["effective"]["mode"] == "bypass_permissions"
    assert "sandbox/project" in body["effective"]["working_directories"]

    fetched = client.get(f"/v1/threads/{thread_id}/permissions", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["overlay"] == payload


def test_promote_thread_permissions_updates_user_defaults(client: TestClient, auth_headers: dict[str, str]) -> None:
    defaults = {
        "mode": "accept_edits",
        "working_directories": ["src"],
        "rules": [
            {"subject": "edit", "behavior": "allow", "matcher": "notes/**"},
        ],
    }
    response = client.put("/auth/me/permissions", json=defaults, headers=auth_headers)
    assert response.status_code == 200

    thread = client.post("/v1/threads", headers=auth_headers)
    assert thread.status_code == 200
    thread_id = thread.json()["id"]

    overlay = {
        "mode": "dont_ask",
        "working_directories": ["sandbox/project"],
        "rules": [
            {"subject": "read", "behavior": "deny", "matcher": "secret/**"},
        ],
    }
    updated = client.patch(f"/v1/threads/{thread_id}/permissions", json=overlay, headers=auth_headers)
    assert updated.status_code == 200

    promoted = client.post(f"/v1/threads/{thread_id}/permissions/promote", headers=auth_headers)

    assert promoted.status_code == 200
    assert promoted.json()["mode"] == "dont_ask"
    assert set(promoted.json()["working_directories"]) == {"src", "sandbox/project"}
    assert promoted.json()["rules"] == [
        {"subject": "edit", "behavior": "allow", "matcher": "notes/**"},
        {"subject": "read", "behavior": "deny", "matcher": "secret/**"},
    ]


def test_chat_completion_uses_effective_thread_permission_context(
    client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    thread = client.post("/v1/threads", headers=auth_headers)
    assert thread.status_code == 200
    thread_id = thread.json()["id"]

    user_defaults = client.put(
        "/auth/me/permissions",
        json={"mode": "accept_edits", "working_directories": ["src"], "rules": []},
        headers=auth_headers,
    )
    assert user_defaults.status_code == 200

    overlay = client.patch(
        f"/v1/threads/{thread_id}/permissions",
        json={
            "mode": "dont_ask",
            "working_directories": ["thread-only"],
            "rules": [{"subject": "bash", "behavior": "allow", "matcher": "git status*"}],
        },
        headers=auth_headers,
    )
    assert overlay.status_code == 200

    class _FakeAgent:
        async def ainvoke(self, payload: dict, config: dict | None = None) -> dict:
            return {"messages": [AIMessage(content="ok")]}

    captured: dict[str, object] = {}
    client.app.state.daytona_manager = type(
        "Manager",
        (),
        {
            "get_backend": lambda self, _thread_id: LocalBackend(str(tmp_path / "workspace")),
            "shutdown": lambda self: None,
        },
    )()

    def _fake_create_aethos_agent(*, model=None, backend=None, permission_context=None, root_dir=None, checkpointer=None, **kwargs):
        captured["model"] = model
        captured["backend"] = backend
        captured["permission_context"] = permission_context
        captured["root_dir"] = root_dir
        return _FakeAgent()

    with (
        patch("src.app.features.chat.service.build_chat_model", return_value=object()),
        patch("src.app.features.chat.service.create_aethos_agent", side_effect=_fake_create_aethos_agent),
    ):
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "aethos",
                "thread_id": thread_id,
                "messages": [{"role": "user", "content": "show status"}],
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    permission_context = captured["permission_context"]
    assert permission_context is not None
    assert permission_context.mode is PermissionMode.DONT_ASK
    assert {str(path) for path in permission_context.working_directories} >= {
        str((tmp_path / "workspace").resolve()),
        str((tmp_path / "workspace" / "src").resolve()),
        str((tmp_path / "workspace" / "thread-only").resolve()),
    }
    assert [rule.matcher for rule in permission_context.rules] == ["git status*"]


def test_chat_completion_drops_empty_assistant_placeholder_from_request_messages(
    client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    class _FakeAgent:
        async def ainvoke(self, payload: dict, config: dict | None = None) -> dict:
            captured["payload"] = payload
            return {"messages": [AIMessage(content="ok")]}

    captured: dict[str, object] = {}
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
                "messages": [
                    {"role": "system", "content": "You are helpful."},
                    {"role": "user", "content": "Hi"},
                    {"role": "assistant", "content": ""},
                ],
                "metadata": {
                    "backend": {
                        "mode": "local",
                    },
                },
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    payload = captured["payload"]
    assert isinstance(payload, dict)
    lc_messages = payload["messages"]
    assert [message.__class__.__name__ for message in lc_messages] == [
        "SystemMessage",
        "HumanMessage",
    ]
    assert [message.content for message in lc_messages] == [
        "You are helpful.",
        "Hi",
    ]


def test_chat_completion_merges_user_project_local_and_session_permissions(
    client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    thread = client.post("/v1/threads", headers=auth_headers)
    assert thread.status_code == 200
    thread_id = thread.json()["id"]

    user_defaults = client.put(
        "/auth/me/permissions",
        json={"mode": "accept_edits", "working_directories": ["user-dir"], "rules": [
            {"subject": "read", "behavior": "allow", "matcher": "user/**"},
        ]},
        headers=auth_headers,
    )
    assert user_defaults.status_code == 200

    overlay = client.patch(
        f"/v1/threads/{thread_id}/permissions",
        json={
            "mode": "dont_ask",
            "working_directories": ["session-dir"],
            "rules": [{"subject": "bash", "behavior": "allow", "matcher": "session-*"}],
        },
        headers=auth_headers,
    )
    assert overlay.status_code == 200

    workspace = tmp_path / "workspace"
    settings_dir = workspace / ".aethos"
    settings_dir.mkdir(parents=True)
    home = tmp_path / "home-aethos"
    home.mkdir(exist_ok=True)
    managed = tmp_path / "managed-settings"
    managed.mkdir()
    with patch.dict("os.environ", {
        "AETHOS_CONFIG_HOME": str(home),
        "AETHOS_MANAGED_SETTINGS_DIR": str(managed),
    }):
        from src.app.core.settings import get_settings

        get_settings.cache_clear()
        (home / "settings.json").write_text(
            '{"permissions":{"mode":"accept_edits","workingDirectories":["user-settings-dir"],"rules":[{"subject":"read","behavior":"allow","matcher":"user-settings/**"}]}}',
            encoding="utf-8",
        )
        (managed / "managed-settings.json").write_text(
            '{"permissions":{"mode":"bypass_permissions","workingDirectories":["managed-dir"],"rules":[{"subject":"read","behavior":"deny","matcher":"managed/**"}]}}',
            encoding="utf-8",
        )
        (settings_dir / "settings.json").write_text(
            '{"permissions":{"mode":"accept_edits","workingDirectories":["project-dir"],"rules":[{"subject":"edit","behavior":"allow","matcher":"project/**"}]}}',
            encoding="utf-8",
        )
        (settings_dir / "settings.local.json").write_text(
            '{"permissions":{"mode":"bypass_permissions","workingDirectories":["local-dir"],"rules":[{"subject":"read","behavior":"deny","matcher":"local/**"}]}}',
            encoding="utf-8",
        )

        class _FakeAgent:
            async def ainvoke(self, payload: dict, config: dict | None = None) -> dict:
                return {"messages": [AIMessage(content="ok")]}

        captured: dict[str, object] = {}
        client.app.state.daytona_manager = type(
            "Manager",
            (),
            {
                "get_backend": lambda self, _thread_id: LocalBackend(str(workspace)),
                "shutdown": lambda self: None,
            },
        )()

        def _fake_create_aethos_agent(*, model=None, backend=None, permission_context=None, root_dir=None, checkpointer=None, **kwargs):
            captured["permission_context"] = permission_context
            return _FakeAgent()

        with (
            patch("src.app.features.chat.service.build_chat_model", return_value=object()),
            patch("src.app.features.chat.service.create_aethos_agent", side_effect=_fake_create_aethos_agent),
        ):
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "aethos",
                    "thread_id": thread_id,
                    "messages": [{"role": "user", "content": "show merged permissions"}],
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        permission_context = captured["permission_context"]
        assert permission_context is not None
        assert permission_context.mode is PermissionMode.DONT_ASK
        assert {str(path) for path in permission_context.working_directories} >= {
            str(workspace.resolve()),
            str((workspace / "user-settings-dir").resolve()),
            str((workspace / "user-dir").resolve()),
            str((workspace / "project-dir").resolve()),
            str((workspace / "local-dir").resolve()),
            str((workspace / "managed-dir").resolve()),
            str((workspace / "session-dir").resolve()),
        }
        assert [(rule.source.value, rule.matcher) for rule in permission_context.rules] == [
            ("user", "user-settings/**"),
            ("user", "user/**"),
            ("project", "project/**"),
            ("local", "local/**"),
            ("policy", "managed/**"),
            ("session", "session-*"),
        ]

        fetched = client.get(f"/v1/threads/{thread_id}/permissions", headers=auth_headers)
        assert fetched.status_code == 200
        effective = fetched.json()["effective"]
        assert effective["mode"] == "dont_ask"
        assert set(effective["working_directories"]) == {
            "user-settings-dir",
            "user-dir",
            "project-dir",
            "local-dir",
            "managed-dir",
            "session-dir",
        }


def test_agent_uses_checkpointer_from_app_state(client, auth_headers, tmp_path: Path):
    """Two requests must receive the same non-None shared checkpointer from app.state."""
    seen: list[object] = []

    def _capturing_create(**kwargs):
        seen.append(kwargs.get("checkpointer"))

        class _FakeAgent:
            async def astream_events(self, input_data, config=None, version=None):
                return
                yield

            async def aget_state(self, config):
                class _Snap:
                    tasks = []
                return _Snap()

            async def ainvoke(self, payload, config=None):
                from langchain_core.messages import AIMessage
                return {"messages": [AIMessage(content="ok")]}

        return _FakeAgent()

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
        patch("src.app.features.chat.service.create_aethos_agent", side_effect=_capturing_create),
    ):
        client.post(
            "/v1/chat/completions",
            json={"model": "aethos", "messages": [{"role": "user", "content": "hi"}]},
            headers=auth_headers,
        )
        client.post(
            "/v1/chat/completions",
            json={"model": "aethos", "messages": [{"role": "user", "content": "hi again"}]},
            headers=auth_headers,
        )

    assert len(seen) == 2
    # Each call must have received a non-None checkpointer
    assert seen[0] is not None, "checkpointer must not be None â€” it should come from app.state"
    assert seen[1] is not None, "checkpointer must not be None â€” it should come from app.state"
    assert seen[0] is seen[1], "Both requests must use the same shared checkpointer instance"


def test_app_state_uses_postgres_checkpointer(client: TestClient) -> None:
    assert isinstance(client.app.state.checkpointer, PostgresCheckpointSaver)


def test_chat_completion_updates_session_metadata(
    client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    thread = client.post("/v1/threads", headers=auth_headers)
    assert thread.status_code == 200
    thread_id = thread.json()["id"]

    class _FakeAgent:
        async def ainvoke(self, payload: dict, config: dict | None = None) -> dict:
            return {"messages": [AIMessage(content="ok")]}

    workspace = tmp_path / "workspace"
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
                "messages": [{"role": "user", "content": "persist session metadata"}],
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    token = auth_headers["Authorization"].split(" ", 1)[1]
    repo = get_auth_repository()
    session = repo.get_session(token)
    assert session is not None

    store = get_thread_store()
    record = store.get_owned_thread(thread_id=thread_id, user_id=session.user_id)
    assert record is not None
    assert record["workspace_root"] == str(workspace.resolve())
    assert record["backend"] == "local"
    assert record["status"] == "idle"
    assert isinstance(record["last_message_at"], int)


def test_streaming_completion_clears_active_run(
    client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    import json

    thread = client.post("/v1/threads", headers=auth_headers)
    assert thread.status_code == 200
    thread_id = thread.json()["id"]

    class _StreamAgent:
        async def astream_events(self, input_data, config=None, version=None):
            yield {"event": "on_chat_model_stream", "data": {"chunk": AIMessage(content="ok")}}

        async def aget_state(self, config):
            class _Snap:
                tasks = []

            return _Snap()

    workspace = tmp_path / "workspace"
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
        patch("src.app.features.chat.service.create_aethos_agent", return_value=_StreamAgent()),
    ):
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "aethos",
                "thread_id": thread_id,
                "stream": True,
                "messages": [{"role": "user", "content": "stream"}],
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    chunks = [
        json.loads(line[len("data: "):])
        for line in response.text.splitlines()
        if line.startswith("data: ") and line != "data: [DONE]"
    ]
    run_chunks = [
        c["choices"][0]["delta"]["run_id"]
        for c in chunks
        if c.get("choices", [{}])[0].get("delta", {}).get("run_id")
    ]
    assert len(run_chunks) == 1

    token = auth_headers["Authorization"].split(" ", 1)[1]
    session = get_auth_repository().get_session(token)
    assert session is not None
    record = get_thread_store().get_owned_thread(thread_id=thread_id, user_id=session.user_id)
    assert record is not None
    assert record["status"] == "idle"
    assert record["active_run_id"] is None
    assert record["run_started_at"] is None


def test_stop_run_endpoint_requires_owner_and_appends_interruption(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    import anyio

    thread = client.post("/v1/threads", headers=auth_headers)
    assert thread.status_code == 200
    thread_id = thread.json()["id"]
    run_id = "run_teststop"

    token = auth_headers["Authorization"].split(" ", 1)[1]
    session = get_auth_repository().get_session(token)
    assert session is not None
    store = get_thread_store()
    store.update_session_metadata(
        thread_id=thread_id,
        user_id=session.user_id,
        status="running",
        active_run_id=run_id,
        run_started_at=123,
    )

    other_auth = client.post("/auth/guest", json={})
    assert other_auth.status_code == 200
    other_headers = {"Authorization": f"Bearer {other_auth.json()['access_token']}"}
    forbidden = client.post(
        f"/v1/threads/{thread_id}/runs/{run_id}/stop",
        json={"reason": "user_cancel"},
        headers=other_headers,
    )
    assert forbidden.status_code == 404

    stopped = client.post(
        f"/v1/threads/{thread_id}/runs/{run_id}/stop",
        json={"reason": "user_cancel"},
        headers=auth_headers,
    )
    stopped_again = client.post(
        f"/v1/threads/{thread_id}/runs/{run_id}/stop",
        json={"reason": "user_cancel"},
        headers=auth_headers,
    )

    assert stopped.status_code == 200
    assert stopped_again.status_code == 200
    record = store.get_owned_thread(thread_id=thread_id, user_id=session.user_id)
    assert record is not None
    assert record["status"] == "interrupted"
    assert record["active_run_id"] is None
    assert record["last_stop_run_id"] == run_id
    assert record["last_stop_reason"] == "user_cancel"

    messages = anyio.run(
        client.app.state.checkpointer.get_full_message_entries,
        {"configurable": {"thread_id": thread_id}},
    )
    interruptions = [entry for entry in messages if entry.get("type") == "interruption"]
    assert len(interruptions) == 1
    assert interruptions[0]["runId"] == run_id
    assert interruptions[0]["message"]["content"][0]["text"] == "[Request interrupted by user]"


def test_stop_run_prefers_user_cancel_over_disconnect_race(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    thread = client.post("/v1/threads", headers=auth_headers)
    assert thread.status_code == 200
    thread_id = thread.json()["id"]
    run_id = "run_reasonrace"

    token = auth_headers["Authorization"].split(" ", 1)[1]
    session = get_auth_repository().get_session(token)
    assert session is not None
    store = get_thread_store()
    store.update_session_metadata(
        thread_id=thread_id,
        user_id=session.user_id,
        status="running",
        active_run_id=run_id,
        run_started_at=123,
    )

    disconnected = store.stop_run(
        thread_id=thread_id,
        user_id=session.user_id,
        run_id=run_id,
        reason="client_disconnect",
    )
    user_cancelled = store.stop_run(
        thread_id=thread_id,
        user_id=session.user_id,
        run_id=run_id,
        reason="user_cancel",
    )

    assert disconnected is not None
    assert user_cancelled is not None
    assert user_cancelled["last_stop_reason"] == "user_cancel"


def test_chat_completion_interrupt_does_not_set_last_message_at(
    client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    thread = client.post("/v1/threads", headers=auth_headers)
    assert thread.status_code == 200
    thread_id = thread.json()["id"]

    class _InterruptAgent:
        async def ainvoke(self, payload: dict, config: dict | None = None) -> dict:
            raise GraphInterrupt()

        async def aget_state(self, config):
            class _Interrupt:
                value = {"behavior": "ask", "reason": "approval required"}

            class _Task:
                interrupts = [_Interrupt()]

            class _Snap:
                tasks = [_Task()]

            return _Snap()

    workspace = tmp_path / "workspace"
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
        patch("src.app.features.chat.service.create_aethos_agent", return_value=_InterruptAgent()),
    ):
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "aethos",
                "thread_id": thread_id,
                "messages": [{"role": "user", "content": "need approval"}],
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    token = auth_headers["Authorization"].split(" ", 1)[1]
    repo = get_auth_repository()
    session = repo.get_session(token)
    assert session is not None

    store = get_thread_store()
    record = store.get_owned_thread(thread_id=thread_id, user_id=session.user_id)
    assert record is not None
    assert record["status"] == "requires_action"
    assert record["last_message_at"] is None


def test_chat_completion_failure_resets_session_status(
    client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    thread = client.post("/v1/threads", headers=auth_headers)
    assert thread.status_code == 200
    thread_id = thread.json()["id"]

    class _FailingAgent:
        async def ainvoke(self, payload: dict, config: dict | None = None) -> dict:
            raise RuntimeError("boom")

    workspace = tmp_path / "workspace"
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
        patch("src.app.features.chat.service.create_aethos_agent", return_value=_FailingAgent()),
    ):
        with pytest.raises(RuntimeError, match="boom"):
            client.post(
                "/v1/chat/completions",
                json={
                    "model": "aethos",
                    "thread_id": thread_id,
                    "messages": [{"role": "user", "content": "fail"}],
                },
                headers=auth_headers,
            )

    token = auth_headers["Authorization"].split(" ", 1)[1]
    repo = get_auth_repository()
    session = repo.get_session(token)
    assert session is not None

    store = get_thread_store()
    record = store.get_owned_thread(thread_id=thread_id, user_id=session.user_id)
    assert record is not None
    assert record["status"] == "idle"


def test_chat_completion_allows_one_shot_permission_override_from_metadata(
    client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    thread = client.post("/v1/threads", headers=auth_headers)
    assert thread.status_code == 200
    thread_id = thread.json()["id"]

    class _FakeAgent:
        async def ainvoke(self, payload: dict, config: dict | None = None) -> dict:
            return {"messages": [AIMessage(content="ok")]}

    captured: dict[str, object] = {}
    client.app.state.daytona_manager = type(
        "Manager",
        (),
        {
            "get_backend": lambda self, _thread_id: LocalBackend(str(tmp_path / "workspace")),
            "shutdown": lambda self: None,
        },
    )()

    def _fake_create_aethos_agent(*, model=None, backend=None, permission_context=None, root_dir=None, checkpointer=None, **kwargs):
        captured["permission_context"] = permission_context
        return _FakeAgent()

    with (
        patch("src.app.features.chat.service.build_chat_model", return_value=object()),
        patch("src.app.features.chat.service.create_aethos_agent", side_effect=_fake_create_aethos_agent),
    ):
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "aethos",
                "thread_id": thread_id,
                "messages": [{"role": "user", "content": "write hello.py"}],
                "metadata": {
                    "permission_override": {"mode": "bypass_permissions"},
                },
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    permission_context = captured["permission_context"]
    assert permission_context is not None
    assert permission_context.mode is PermissionMode.BYPASS_PERMISSIONS


def test_chat_completion_uses_default_workspace_for_local_backend_without_root_dir(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    captured: dict[str, object] = {}

    class _FakeAgent:
        async def ainvoke(self, payload: dict, config: dict | None = None) -> dict:
            return {"messages": [AIMessage(content="ok")]}

    def _fake_create_aethos_agent(*, backend=None, permission_context=None, root_dir=None, **kwargs):
        captured["backend"] = backend
        captured["permission_context"] = permission_context
        return _FakeAgent()

    with (
        patch("src.app.features.chat.service.build_chat_model", return_value=object()),
        patch("src.app.features.chat.service.create_aethos_agent", side_effect=_fake_create_aethos_agent),
    ):
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "aethos",
                "messages": [{"role": "user", "content": "hi"}],
                "metadata": {
                    "backend": {
                        "mode": "local",
                    },
                },
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    backend = captured["backend"]
    assert isinstance(backend, LocalBackend)
    assert backend.root.name == "workspace"
    permission_context = captured["permission_context"]
    assert permission_context is not None
    assert backend.root.resolve() in permission_context.working_directories


def test_chat_completion_streams_permission_request_on_interrupt(
    client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    """When the agent is interrupted, the SSE stream must include a permission_request chunk."""
    import json
    from unittest.mock import patch

    class _InterruptAgent:
        async def astream_events(self, input_data, config=None, version=None):
            return
            yield  # make it an empty async generator

        async def aget_state(self, config):
            # Simulate a pending interrupt in graph state
            class _Interrupt:
                value = {
                    "behavior": "ask",
                    "reason": "Edit requires approval",
                    "subject": "edit",
                    "path": "hello.py",
                    "suggested_mode": "accept_edits",
                }
            class _Task:
                interrupts = [_Interrupt()]
            class _Snap:
                tasks = [_Task()]
            return _Snap()

    with (
        patch("src.app.features.chat.service.build_chat_model", return_value=object()),
        patch("src.app.features.chat.service.create_aethos_agent", return_value=_InterruptAgent()),
    ):
        client.app.state.daytona_manager = type(
            "Manager",
            (),
            {
                "get_backend": lambda self, _thread_id: LocalBackend(str(tmp_path / "workspace")),
                "shutdown": lambda self: None,
            },
        )()
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "aethos",
                "stream": True,
                "messages": [{"role": "user", "content": "write hello.py"}],
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    chunks = [
        json.loads(line[len("data: "):])
        for line in response.text.splitlines()
        if line.startswith("data: ") and line != "data: [DONE]"
    ]
    permission_chunks = [
        c for c in chunks
        if c.get("choices", [{}])[0].get("delta", {}).get("permission_request")
    ]
    assert len(permission_chunks) >= 1
    pr = permission_chunks[0]["choices"][0]["delta"]["permission_request"]
    assert pr["behavior"] == "ask"
    assert pr["reason"] == "Edit requires approval"


def test_chat_completion_streaming_sets_graph_recursion_limit(
    client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    from unittest.mock import patch

    captured: dict[str, object] = {}

    class _Agent:
        async def astream_events(self, input_data, config=None, version=None):
            captured["config"] = config
            if False:
                yield {}

        async def aget_state(self, config):
            class _Snap:
                tasks = []

            return _Snap()

    with (
        patch("src.app.features.chat.service.build_chat_model", return_value=object()),
        patch("src.app.features.chat.service.create_aethos_agent", return_value=_Agent()),
    ):
        client.app.state.daytona_manager = type(
            "Manager",
            (),
            {
                "get_backend": lambda self, _thread_id: LocalBackend(str(tmp_path / "workspace")),
                "shutdown": lambda self: None,
            },
        )()
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "aethos",
                "stream": True,
                "messages": [{"role": "user", "content": "loop a bit"}],
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert captured["config"]["recursion_limit"] == DEFAULT_GRAPH_RECURSION_LIMIT


def test_chat_completion_non_streaming_sets_graph_recursion_limit(
    client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    from unittest.mock import patch

    captured: dict[str, object] = {}

    class _Agent:
        async def ainvoke(self, input_data, config=None):
            captured["config"] = config
            return {"messages": [AIMessage(content="done")]}

    with (
        patch("src.app.features.chat.service.build_chat_model", return_value=object()),
        patch("src.app.features.chat.service.create_aethos_agent", return_value=_Agent()),
    ):
        client.app.state.daytona_manager = type(
            "Manager",
            (),
            {
                "get_backend": lambda self, _thread_id: LocalBackend(str(tmp_path / "workspace")),
                "shutdown": lambda self: None,
            },
        )()
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "aethos",
                "stream": False,
                "messages": [{"role": "user", "content": "loop a bit"}],
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert captured["config"]["recursion_limit"] == DEFAULT_GRAPH_RECURSION_LIMIT

def test_chat_completion_non_streaming_uses_configured_graph_recursion_limit(
    client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    workspace = tmp_path / "workspace"
    (workspace / ".aethos").mkdir(parents=True)
    (workspace / ".aethos" / "settings.json").write_text(
        json.dumps({"agentLoop": {"recursionLimit": 150}}),
        encoding="utf-8",
    )

    class _Agent:
        async def ainvoke(self, input_data, config=None):
            captured["config"] = config
            return {"messages": [AIMessage(content="done")]}

    with (
        patch("src.app.features.chat.service.build_chat_model", return_value=object()),
        patch("src.app.features.chat.service.create_aethos_agent", return_value=_Agent()),
    ):
        client.app.state.daytona_manager = type(
            "Manager",
            (),
            {
                "get_backend": lambda self, _thread_id: LocalBackend(str(workspace)),
                "shutdown": lambda self: None,
            },
        )()
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "aethos",
                "stream": False,
                "messages": [{"role": "user", "content": "loop a bit"}],
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert captured["config"]["recursion_limit"] == 150

def test_chat_completion_non_streaming_graph_recursion_error_returns_length(
    client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    class _Agent:
        async def ainvoke(self, input_data, config=None):
            raise GraphRecursionError("limit")

    with (
        patch("src.app.features.chat.service.build_chat_model", return_value=object()),
        patch("src.app.features.chat.service.create_aethos_agent", return_value=_Agent()),
    ):
        client.app.state.daytona_manager = type(
            "Manager",
            (),
            {
                "get_backend": lambda self, _thread_id: LocalBackend(str(tmp_path / "workspace")),
                "shutdown": lambda self: None,
            },
        )()
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "aethos",
                "stream": False,
                "messages": [{"role": "user", "content": "loop forever"}],
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["choices"][0]["finish_reason"] == "length"
    assert payload["choices"][0]["stop_reason"] == GRAPH_RECURSION_STOP_REASON

def test_chat_completion_streaming_graph_recursion_error_returns_length(
    client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    class _Agent:
        async def astream_events(self, input_data, config=None, version=None):
            raise GraphRecursionError("limit")
            if False:
                yield {}

    with (
        patch("src.app.features.chat.service.build_chat_model", return_value=object()),
        patch("src.app.features.chat.service.create_aethos_agent", return_value=_Agent()),
    ):
        client.app.state.daytona_manager = type(
            "Manager",
            (),
            {
                "get_backend": lambda self, _thread_id: LocalBackend(str(tmp_path / "workspace")),
                "shutdown": lambda self: None,
            },
        )()
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "aethos",
                "stream": True,
                "messages": [{"role": "user", "content": "loop forever"}],
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    chunks = [
        json.loads(line[len("data: "):])
        for line in response.text.splitlines()
        if line.startswith("data: ") and line != "data: [DONE]"
    ]
    assert chunks[-1]["choices"][0]["finish_reason"] == "length"
    assert chunks[-1]["choices"][0]["delta"]["stop_reason"] == GRAPH_RECURSION_STOP_REASON


def test_chat_completion_resumes_agent_with_command(
    client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    """metadata.resume must be converted to Command(resume=...) and passed to the agent."""
    import json
    from unittest.mock import patch
    captured = {}

    class _ResumeAgent:
        async def astream_events(self, input_data, config=None, version=None):
            captured["input"] = input_data
            if False:
                yield {}

        async def ainvoke(self, input_data, config=None):
            raise AssertionError("resume stream path must not use ainvoke")

        async def aget_state(self, config):
            class _Snap:
                tasks = []
            return _Snap()

    with (
        patch("src.app.features.chat.service.build_chat_model", return_value=object()),
        patch("src.app.features.chat.service.create_aethos_agent", return_value=_ResumeAgent()),
    ):
        client.app.state.daytona_manager = type(
            "Manager",
            (),
            {
                "get_backend": lambda self, _thread_id: LocalBackend(str(tmp_path / "workspace")),
                "shutdown": lambda self: None,
            },
        )()
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "aethos",
                "stream": True,
                "messages": [{"role": "user", "content": "approve"}],
                "metadata": {"resume": {"approved": True}},
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert isinstance(captured.get("input"), Command)
    assert captured["input"].resume == {"approved": True}


def test_streaming_resume_uses_astream_events_instead_of_ainvoke(
    client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    """Resume requests should stream LangGraph events and never call ainvoke."""
    import json
    from unittest.mock import patch
    captured: dict[str, object] = {}

    class _ResumeAgent:
        async def astream_events(self, input_data, config=None, version=None):
            captured["input"] = input_data
            captured["version"] = version

            class _Chunk:
                content = "resumed ok"

            yield {"event": "on_chat_model_stream", "data": {"chunk": _Chunk()}}

        async def ainvoke(self, input_data, config=None):
            raise AssertionError("resume stream path must not use ainvoke")

        async def aget_state(self, config):
            class _Snap:
                tasks = []

            return _Snap()

    with (
        patch("src.app.features.chat.service.build_chat_model", return_value=object()),
        patch("src.app.features.chat.service.create_aethos_agent", return_value=_ResumeAgent()),
    ):
        client.app.state.daytona_manager = type(
            "Manager",
            (),
            {
                "get_backend": lambda self, _thread_id: LocalBackend(str(tmp_path / "workspace")),
                "shutdown": lambda self: None,
            },
        )()
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "aethos",
                "stream": True,
                "messages": [{"role": "user", "content": "approve"}],
                "metadata": {"resume": {"approved": True}},
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert isinstance(captured.get("input"), Command)
    assert captured["input"].resume == {"approved": True}
    assert captured["version"] == "v2"
    chunks = [
        json.loads(line[len("data: "):])
        for line in response.text.splitlines()
        if line.startswith("data: ") and line != "data: [DONE]"
    ]
    content_chunks = [
        c["choices"][0]["delta"]["content"]
        for c in chunks
        if c.get("choices", [{}])[0].get("delta", {}).get("content")
    ]
    assert content_chunks == ["resumed ok"]


def test_non_streaming_resume_uses_astream_events_instead_of_ainvoke(
    client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    from unittest.mock import patch

    class _ResumeAgent:
        async def astream_events(self, input_data, config=None, version=None):
            assert isinstance(input_data, Command)
            assert version == "v2"

            class _Chunk:
                content = "resumed ok"

            yield {"event": "on_chat_model_stream", "data": {"chunk": _Chunk()}}

        async def ainvoke(self, input_data, config=None):
            raise AssertionError("resume path must not use ainvoke")

        async def aget_state(self, config):
            class _Snap:
                tasks = []

            return _Snap()

    with (
        patch("src.app.features.chat.service.build_chat_model", return_value=object()),
        patch("src.app.features.chat.service.create_aethos_agent", return_value=_ResumeAgent()),
    ):
        client.app.state.daytona_manager = type(
            "Manager",
            (),
            {
                "get_backend": lambda self, _thread_id: LocalBackend(str(tmp_path / "workspace")),
                "shutdown": lambda self: None,
            },
        )()
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "aethos",
                "stream": False,
                "messages": [{"role": "user", "content": "approve"}],
                "metadata": {"resume": {"approved": True}},
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "resumed ok"


def test_streaming_resume_forwards_live_tool_events(
    client: TestClient,
    auth_headers: dict[str, str],
    tmp_path: Path,
) -> None:
    import json

    class _ResumeAgent:
        async def astream_events(self, input_data, config=None, version=None):
            yield {
                "event": "on_tool_end",
                "name": "write_file",
                "run_id": "run_write",
                "data": {"output": "Written 12 characters to 'report.py'."},
            }
            yield {
                "event": "on_tool_start",
                "name": "powershell",
                "run_id": "run_shell",
                "data": {
                    "input": {
                        "command": "python report.py",
                        "description": "Generate report",
                    }
                },
            }
            yield {
                "event": "on_tool_end",
                "name": "powershell",
                "run_id": "run_shell",
                "data": {"output": "Saved: report.xlsx"},
            }

        async def ainvoke(self, input_data, config=None):
            raise AssertionError("resume stream path must not use ainvoke")

        async def aget_state(self, config):
            class _Snap:
                tasks = []

            return _Snap()

    with (
        patch("src.app.features.chat.service.build_chat_model", return_value=object()),
        patch("src.app.features.chat.service.create_aethos_agent", return_value=_ResumeAgent()),
    ):
        client.app.state.daytona_manager = type(
            "Manager",
            (),
            {
                "get_backend": lambda self, _thread_id: LocalBackend(str(tmp_path / "workspace")),
                "shutdown": lambda self: None,
            },
        )()
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "aethos",
                "stream": True,
                "messages": [{"role": "user", "content": "approve"}],
                "metadata": {"resume": {"approved": True}},
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    chunks = [
        json.loads(line[len("data: "):])
        for line in response.text.splitlines()
        if line.startswith("data: ") and line != "data: [DONE]"
    ]
    tool_events = [
        c["choices"][0]["delta"]["tool_event"]
        for c in chunks
        if c.get("choices", [{}])[0].get("delta", {}).get("tool_event")
    ]

    assert [(event["name"], event["phase"]) for event in tool_events] == [
        ("write_file", "end"),
        ("powershell", "start"),
        ("powershell", "end"),
    ]
    assert tool_events[0]["tool_call_id"] == "run_write"
    assert tool_events[1]["tool_call_id"] == "run_shell"
    assert tool_events[2]["tool_call_id"] == "run_shell"
    assert tool_events[1]["input"]["description"] == "Generate report"


def test_resolve_resume_input_maps_dict_payload_for_multiple_interrupts() -> None:
    class _Interrupt:
        def __init__(self, interrupt_id: str) -> None:
            self.id = interrupt_id

    class _Task:
        interrupts = [_Interrupt("int-1"), _Interrupt("int-2")]

    class _Snapshot:
        tasks = [_Task()]

    class _Agent:
        async def aget_state(self, config):
            return _Snapshot()

    command = Command(resume={"approved": True})
    resolved = asyncio.run(
        _resolve_resume_input(_Agent(), command, {"configurable": {"thread_id": "thread-1"}})
    )

    assert isinstance(resolved, Command)
    assert resolved.resume == {
        "int-1": {"approved": True},
        "int-2": {"approved": True},
    }


def test_resolve_resume_input_preserves_explicit_interrupt_map() -> None:
    class _Interrupt:
        def __init__(self, interrupt_id: str) -> None:
            self.id = interrupt_id

    class _Task:
        interrupts = [_Interrupt("int-1"), _Interrupt("int-2")]

    class _Snapshot:
        tasks = [_Task()]

    class _Agent:
        async def aget_state(self, config):
            return _Snapshot()

    command = Command(resume={"int-1": {"approved": True}, "int-2": {"approved": False}})
    resolved = asyncio.run(
        _resolve_resume_input(_Agent(), command, {"configurable": {"thread_id": "thread-1"}})
    )

    assert resolved is command


def test_build_backend_falls_back_to_local_when_daytona_dependency_is_missing(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    class _FakeAgent:
        async def ainvoke(self, payload: dict, config: dict | None = None) -> dict:
            return {"messages": [AIMessage(content="ok")]}

    captured: dict[str, object] = {}

    client.app.state.daytona_manager = type(
        "Manager",
        (),
        {
            "get_backend": lambda self, _thread_id: (_ for _ in ()).throw(
                DaytonaUnavailableError("daytona package not installed. Run: pip install 'aethos[daytona]'")
            ),
            "shutdown": lambda self: None,
        },
    )()

    thread = client.post("/v1/threads", headers=auth_headers)
    assert thread.status_code == 200
    thread_id = thread.json()["id"]

    def _fake_create_aethos_agent(*, backend=None, **kwargs):
        captured["backend"] = backend
        return _FakeAgent()

    with (
        patch("src.app.features.chat.service.build_chat_model", return_value=object()),
        patch("src.app.features.chat.service.create_aethos_agent", side_effect=_fake_create_aethos_agent),
    ):
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "aethos",
                "thread_id": thread_id,
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
            },
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert isinstance(captured["backend"], LocalBackend)

