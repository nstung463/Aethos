from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient

from src.app import create_app
from src.backends.local import LocalSandbox as LocalBackend


def test_resume_can_persist_exact_file_edit_permission_to_thread(tmp_path: Path) -> None:
    with TestClient(create_app()) as client:
        auth_response = client.post("/auth/guest", json={})
        assert auth_response.status_code == 200
        auth_headers = {"Authorization": f"Bearer {auth_response.json()['access_token']}"}

        thread = client.post("/v1/threads", headers=auth_headers)
        assert thread.status_code == 200
        thread_id = thread.json()["id"]

        captured: dict[str, object] = {}

        class _FakeAgent:
            async def astream_events(self, payload, config: dict | None = None, version: str | None = None):
                class _Chunk:
                    content = "ok"

                yield {"event": "on_chat_model_stream", "data": {"chunk": _Chunk()}}

            async def ainvoke(self, payload, config: dict | None = None) -> dict:
                raise AssertionError("resume path must not use ainvoke")

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

        def _fake_create_aethos_agent(*, model=None, backend=None, permission_context=None, root_dir=None, checkpointer=None, **kwargs):
            captured["permission_context"] = permission_context
            return _FakeAgent()

        with (
            patch("src.app.modules.chat.service.build_chat_model", return_value=object()),
            patch("src.app.modules.chat.service.create_aethos_agent", side_effect=_fake_create_aethos_agent),
        ):
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "aethos",
                    "thread_id": thread_id,
                    "messages": [{"role": "user", "content": "approve"}],
                    "metadata": {
                        "resume": {
                            "approved": True,
                            "grant": {
                                "scope": "thread",
                                "subject": "edit",
                                "path": "src/app.py",
                            },
                        },
                    },
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        permission_context = captured["permission_context"]
        assert permission_context is not None
        assert any(
            rule.subject.value == "edit"
            and rule.behavior.value == "allow"
            and rule.matcher == "src/app.py"
            for rule in permission_context.rules
        )

        thread_permissions = client.get(f"/v1/threads/{thread_id}/permissions", headers=auth_headers)
        assert thread_permissions.status_code == 200
        assert thread_permissions.json()["overlay"]["rules"] == [
            {"subject": "edit", "behavior": "allow", "matcher": "src/app.py"}
        ]
