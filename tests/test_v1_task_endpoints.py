"""Tests for POST /v1/tasks/title and POST /v1/tasks/follow-ups."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

from src.app import create_app
from src.app.services.chat_tasks import FollowUpsTaskResult, TitleTaskResult


@pytest.fixture()
def client() -> TestClient:
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture()
def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/auth/guest", json={})
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _chat_body(*, model: str = "aethos") -> dict:
    return {
        "model": model,
        "messages": [
            {"role": "user", "content": "How do I reset my password?"},
        ],
    }


def test_tasks_title_returns_model_title(client: TestClient, auth_headers: dict[str, str]) -> None:
    with patch(
        "src.app.modules.chat.router.generate_title_task",
        new_callable=AsyncMock,
        return_value=TitleTaskResult(title="Password reset help"),
    ):
        r = client.post("/v1/tasks/title", json=_chat_body(), headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"title": "Password reset help"}


def test_tasks_title_strips_whitespace(client: TestClient, auth_headers: dict[str, str]) -> None:
    with patch(
        "src.app.modules.chat.router.generate_title_task",
        new_callable=AsyncMock,
        return_value=TitleTaskResult(title="  Trimmed title  "),
    ):
        r = client.post("/v1/tasks/title", json=_chat_body(), headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"title": "Trimmed title"}


def test_tasks_title_fallback_on_empty_title(client: TestClient, auth_headers: dict[str, str]) -> None:
    with patch(
        "src.app.modules.chat.router.generate_title_task",
        new_callable=AsyncMock,
        return_value=TitleTaskResult(title="   "),
    ):
        r = client.post("/v1/tasks/title", json=_chat_body(), headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert "title" in body
    assert body["title"] == "How do I reset my password?"


def test_tasks_title_fallback_on_exception(client: TestClient, auth_headers: dict[str, str]) -> None:
    with patch(
        "src.app.modules.chat.router.generate_title_task",
        new_callable=AsyncMock,
        side_effect=RuntimeError("LLM unavailable"),
    ):
        r = client.post("/v1/tasks/title", json=_chat_body(), headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"title": "How do I reset my password?"}


def test_tasks_title_fallback_on_none_result(client: TestClient, auth_headers: dict[str, str]) -> None:
    with patch(
        "src.app.modules.chat.router.generate_title_task",
        new_callable=AsyncMock,
        return_value=None,
    ):
        r = client.post("/v1/tasks/title", json=_chat_body(), headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"title": "How do I reset my password?"}


def test_tasks_follow_ups_returns_list(client: TestClient, auth_headers: dict[str, str]) -> None:
    follow_ups = ["What about 2FA?", "Can I use SSO?", "Where are logs?"]
    with patch(
        "src.app.modules.chat.router.generate_follow_ups_task",
        new_callable=AsyncMock,
        return_value=FollowUpsTaskResult(follow_ups=follow_ups),
    ):
        r = client.post("/v1/tasks/follow-ups", json=_chat_body(), headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"follow_ups": follow_ups}


def test_tasks_follow_ups_disable_reasoning_for_profile_task(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    body = _chat_body()
    body["metadata"] = {
        "profile": {
            "provider": "openrouter",
            "model": "openai/gpt-5",
            "api_key": "sk-test",
            "reasoning_enabled": True,
            "reasoning_effort": "high",
            "thinking_budget_tokens": 2048,
        }
    }

    with patch(
        "src.app.modules.chat.router.generate_follow_ups_task",
        new_callable=AsyncMock,
        return_value=FollowUpsTaskResult(follow_ups=[]),
    ) as mocked_task:
        r = client.post("/v1/tasks/follow-ups", json=body, headers=auth_headers)

    assert r.status_code == 200
    _, kwargs = mocked_task.await_args
    assert kwargs["profile_reasoning_enabled"] is False
    assert kwargs["profile_reasoning_effort"] == "none"
    assert kwargs["profile_thinking_budget_tokens"] is None

def test_tasks_follow_ups_empty_on_exception(client: TestClient, auth_headers: dict[str, str]) -> None:
    with patch(
        "src.app.modules.chat.router.generate_follow_ups_task",
        new_callable=AsyncMock,
        side_effect=RuntimeError("LLM unavailable"),
    ):
        r = client.post("/v1/tasks/follow-ups", json=_chat_body(), headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"follow_ups": []}


def test_tasks_follow_ups_empty_on_none_result(client: TestClient, auth_headers: dict[str, str]) -> None:
    with patch(
        "src.app.modules.chat.router.generate_follow_ups_task",
        new_callable=AsyncMock,
        return_value=None,
    ):
        r = client.post("/v1/tasks/follow-ups", json=_chat_body(), headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"follow_ups": []}


def test_tasks_unknown_model_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    body = _chat_body(model="nonexistent-model-xyz")
    r = client.post("/v1/tasks/title", json=body, headers=auth_headers)
    assert r.status_code == 404


def test_tasks_forward_user_api_keys_from_metadata(client: TestClient, auth_headers: dict[str, str]) -> None:
    body = _chat_body()
    body["metadata"] = {
        "user_api_keys": {
            "openrouter": "sk-or-v1-test",
            "anthropic": "sk-ant-test",
            "openai": "sk-openai-test",
        }
    }

    with patch(
        "src.app.modules.chat.router.generate_title_task",
        new_callable=AsyncMock,
        return_value=TitleTaskResult(title="Password reset help"),
    ) as mocked_task:
        r = client.post("/v1/tasks/title", json=body, headers=auth_headers)

    assert r.status_code == 200
    _, kwargs = mocked_task.await_args
    assert kwargs["model_id"] == "aethos"
    # Compare messages with exclude_none to handle the new tool_call_id field
    received_messages = [message.model_dump(exclude_none=True) for message in kwargs["messages"]]
    assert received_messages == body["messages"]
    assert kwargs["api_keys"] == {
        "openrouter": "sk-or-v1-test",
        "anthropic": "sk-ant-test",
        "openai": "sk-openai-test",
    }


def test_tasks_require_authentication(client: TestClient) -> None:
    r = client.post("/v1/tasks/title", json=_chat_body())
    assert r.status_code == 401


def test_tasks_reject_custom_openai_compatible_endpoint_in_public_mode(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    body = _chat_body()
    body["metadata"] = {
        "profile": {
            "provider": "openai_compatible",
            "model": "custom-model",
            "api_key": "sk-test",
            "base_url": "https://example.internal/v1",
        }
    }

    r = client.post("/v1/tasks/title", json=body, headers=auth_headers)
    assert r.status_code == 403
