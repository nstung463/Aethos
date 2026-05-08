"""Tests for web_search tool with stubbed providers."""
from __future__ import annotations

from unittest.mock import MagicMock


def test_search_missing_api_keys(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE-SUBSCRIPTION-KEY", raising=False)
    monkeypatch.delenv("GOOGLE-SEARCH-URL", raising=False)
    monkeypatch.delenv("GOOGLE-SEARCHENGINE-ID", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    from src.ai.tools.web.search import web_search_tool

    result = web_search_tool.invoke({"query": "test"})

    assert "Google failed" in result
    assert "Tavily fallback failed" in result


def test_search_uses_google_first(monkeypatch) -> None:
    from src.ai.tools.web import search

    tavily_search = MagicMock(return_value=[])
    monkeypatch.setattr(
        search,
        "_google_search",
        lambda query, max_results: [
            {"title": "Google", "url": "https://example.com", "content": "Snippet"}
        ],
    )
    monkeypatch.setattr(search, "_tavily_search", tavily_search)

    result = search.web_search_tool.invoke({"query": "test"})

    assert "Google" in result
    assert "https://example.com" in result
    tavily_search.assert_not_called()


def test_search_falls_back_to_tavily_when_google_fails(monkeypatch) -> None:
    from src.ai.tools.web import search

    def fail_google(query: str, max_results: int) -> list[dict[str, str]]:
        raise RuntimeError("google unavailable")

    monkeypatch.setattr(search, "_google_search", fail_google)
    monkeypatch.setattr(
        search,
        "_tavily_search",
        lambda query, max_results: [
            {"title": "Tavily", "url": "https://fallback.test", "content": "Fallback"}
        ],
    )

    result = search.web_search_tool.invoke({"query": "test"})

    assert "Tavily" in result
    assert "https://fallback.test" in result
