from __future__ import annotations

from unittest.mock import patch

from fastapi import HTTPException
from langchain_core.messages import AIMessage
from starlette.testclient import TestClient

from src.app import create_app
from src.ai.reasoning import build_reasoning_model_kwargs, resolve_reasoning_capabilities
from src.app.core.settings import Settings, get_settings
from src.app.modules.chat.request_parser import extract_profile
from src.app.modules.chat.schemas import ChatRequest
from src.config import build_chat_model


def test_resolve_reasoning_capabilities_for_openai_reasoning_model() -> None:
    caps = resolve_reasoning_capabilities("openai", "gpt-5")
    assert caps.supports_reasoning_effort is True
    assert caps.supports_reasoning_output is True
    assert caps.supports_thinking_budget is False
    assert caps.effort_options == ("none", "low", "medium", "high")


def test_resolve_reasoning_capabilities_for_deepseek_v4_flash() -> None:
    caps = resolve_reasoning_capabilities("deepseek", "deepseek-v4-flash")
    assert caps.supports_reasoning_effort is True
    assert caps.supports_reasoning_output is True
    assert caps.effort_options == ("none", "high", "max")


def test_build_reasoning_model_kwargs_skips_non_reasoning_openai_model() -> None:
    kwargs = build_reasoning_model_kwargs(
        provider="openai",
        model_name="gpt-4o",
        reasoning_enabled=True,
        reasoning_effort="high",
        thinking_budget_tokens=None,
    )
    assert kwargs == {}


def test_build_reasoning_model_kwargs_for_anthropic() -> None:
    kwargs = build_reasoning_model_kwargs(
        provider="anthropic",
        model_name="claude-opus-4-5",
        reasoning_enabled=True,
        reasoning_effort="high",
        thinking_budget_tokens=2048,
    )
    assert kwargs == {"thinking": {"type": "enabled", "budget_tokens": 2048}}


def test_build_reasoning_model_kwargs_for_deepseek_v4_max() -> None:
    kwargs = build_reasoning_model_kwargs(
        provider="deepseek",
        model_name="deepseek-v4-flash",
        reasoning_enabled=True,
        reasoning_effort="max",
        thinking_budget_tokens=None,
    )
    assert kwargs == {
        "reasoning_effort": "max",
        "extra_body": {"thinking": {"type": "enabled"}},
    }


def test_build_reasoning_model_kwargs_for_deepseek_v4_none_disables_thinking() -> None:
    kwargs = build_reasoning_model_kwargs(
        provider="deepseek",
        model_name="deepseek-v4-flash",
        reasoning_enabled=False,
        reasoning_effort="none",
        thinking_budget_tokens=None,
    )
    assert kwargs == {"extra_body": {"thinking": {"type": "disabled"}}}


def test_build_reasoning_model_kwargs_for_openrouter_uses_reasoning_body() -> None:
    kwargs = build_reasoning_model_kwargs(
        provider="openrouter",
        model_name="openai/gpt-5.1",
        reasoning_enabled=True,
        reasoning_effort="xhigh",
        thinking_budget_tokens=None,
    )
    assert kwargs == {"extra_body": {"reasoning": {"effort": "xhigh"}}}


def test_build_reasoning_model_kwargs_for_openrouter_gemini_uses_reasoning_body() -> None:
    kwargs = build_reasoning_model_kwargs(
        provider="openrouter",
        model_name="google/gemini-3.1-pro-preview",
        reasoning_enabled=True,
        reasoning_effort="xhigh",
        thinking_budget_tokens=None,
    )
    assert kwargs == {"extra_body": {"reasoning": {"effort": "xhigh"}}}


def test_extract_profile_parses_reasoning_fields() -> None:
    request = ChatRequest.model_validate(
        {
            "model": "ethos",
            "messages": [{"role": "user", "content": "hi"}],
            "metadata": {
                "profile": {
                    "provider": "deepseek",
                    "model": "deepseek-v4-flash",
                    "api_key": "sk-test",
                    "reasoning_enabled": True,
                    "reasoning_effort": "max",
                    "thinking_budget_tokens": 1234,
                    "model_kwargs": {"verbosity": "low"},
                }
            },
        }
    )

    profile = extract_profile(request, Settings())

    assert profile is not None
    assert profile["reasoning_enabled"] is True
    assert profile["reasoning_effort"] == "max"
    assert profile["thinking_budget_tokens"] == 1234
    assert profile["model_kwargs"] == {"verbosity": "low"}


def test_extract_profile_rejects_custom_endpoint_when_disabled() -> None:
    request = ChatRequest.model_validate(
        {
            "model": "ethos",
            "messages": [{"role": "user", "content": "hi"}],
            "metadata": {
                "profile": {
                    "provider": "openai_compatible",
                    "model": "custom-model",
                    "base_url": "https://example.internal/v1",
                }
            },
        }
    )

    try:
        extract_profile(request, Settings(allow_custom_provider_endpoints=False))
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Expected HTTPException for disabled custom endpoint")


def test_get_settings_disables_custom_provider_endpoints_by_default(monkeypatch) -> None:
    monkeypatch.delenv("ETHOS_ALLOW_CUSTOM_PROVIDER_ENDPOINTS", raising=False)
    get_settings.cache_clear()
    try:
        assert get_settings().allow_custom_provider_endpoints is False
    finally:
        get_settings.cache_clear()


def test_build_chat_model_merges_reasoning_and_model_kwargs() -> None:
    with patch("src.config.init_chat_model", return_value=object()) as mocked_init:
        build_chat_model(
            "openai",
            "gpt-5",
            api_keys={"api_key": "sk-test"},
            reasoning_enabled=True,
            reasoning_effort="medium",
            model_kwargs={"verbosity": "low"},
        )

    args, kwargs = mocked_init.call_args
    assert args == ("openai:gpt-5",)
    assert kwargs["api_key"] == "sk-test"
    assert kwargs["temperature"] == 0.0
    assert kwargs["verbosity"] == "low"
    assert kwargs["reasoning_effort"] == "medium"


def test_chat_completion_forwards_reasoning_profile_to_model_builder(tmp_path) -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.post("/auth/guest", json={})
        token = response.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}
        app.state.daytona_manager = type(
            "Manager",
            (),
            {
                "get_backend": lambda self, _thread_id: type("Backend", (), {"root": tmp_path / "workspace"})(),
                "shutdown": lambda self: None,
            },
        )()

        class _FakeAgent:
            async def ainvoke(self, payload: dict, config: dict | None = None) -> dict:
                return {"messages": [AIMessage(content="ok")]}

        with (
            patch("src.app.modules.chat.service.build_chat_model", return_value=object()) as mocked_build,
            patch("src.app.modules.chat.service.create_ethos_agent", return_value=_FakeAgent()),
        ):
            response = client.post(
                "/v1/chat/completions",
                json={
                    "model": "ethos",
                    "messages": [{"role": "user", "content": "hi"}],
                    "metadata": {
                        "profile": {
                            "provider": "openai",
                            "model": "gpt-5",
                            "api_key": "sk-test",
                            "reasoning_enabled": True,
                            "reasoning_effort": "high",
                            "model_kwargs": {"verbosity": "low"},
                        },
                        "backend": {"mode": "local"},
                    },
                },
                headers=auth_headers,
            )

    assert response.status_code == 200
    _, kwargs = mocked_build.call_args
    assert kwargs["reasoning_enabled"] is True
    assert kwargs["reasoning_effort"] == "high"
    assert kwargs["model_kwargs"] == {"verbosity": "low"}
