"""web_search tool — web search with Google-first fallback."""

import os
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


class WebSearchInput(BaseModel):
    query: str = Field(description="The search query.")
    max_results: int = Field(
        default=5,
        description="Maximum number of results to return (1-10).",
    )


def _format_results(query: str, results: list[dict[str, str]]) -> str:
    if not results:
        return f"No results found for '{query}'."

    parts = []
    for index, result in enumerate(results, 1):
        title = result.get("title", "No title")
        url = result.get("url", "")
        content = result.get("content", "").strip()[:600]
        parts.append(f"[{index}] {title}\n    URL: {url}\n    {content}")

    return "\n\n".join(parts)


def _google_search(query: str, max_results: int) -> list[dict[str, str]]:
    try:
        import httpx
    except ImportError as exc:
        raise RuntimeError("httpx is not installed") from exc

    api_key = os.getenv("GOOGLE-SUBSCRIPTION-KEY")
    search_url = os.getenv("GOOGLE-SEARCH-URL")
    search_engine_id = os.getenv("GOOGLE-SEARCHENGINE-ID")
    if not api_key or not search_url or not search_engine_id:
        raise RuntimeError(
            "GOOGLE-SUBSCRIPTION-KEY, GOOGLE-SEARCH-URL, and GOOGLE-SEARCHENGINE-ID environment variables are required"
        )

    response = httpx.get(
        search_url,
        params={"key": api_key, "cx": search_engine_id, "q": query, "num": max_results},
        timeout=15.0,
    )
    response.raise_for_status()
    payload: dict[str, Any] = response.json()

    results = []
    for item in payload.get("items", []):
        results.append(
            {
                "title": str(item.get("title") or "No title"),
                "url": str(item.get("link") or ""),
                "content": str(item.get("snippet") or ""),
            }
        )
    return results


def _tavily_search(query: str, max_results: int) -> list[dict[str, str]]:
    try:
        from tavily import TavilyClient
    except ImportError as exc:
        raise RuntimeError("tavily-python is not installed") from exc

    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY environment variable is not set")

    client = TavilyClient(api_key=api_key)
    response = client.search(query, max_results=max_results)

    results = []
    for item in response.get("results", []):
        results.append(
            {
                "title": str(item.get("title") or "No title"),
                "url": str(item.get("url") or ""),
                "content": str(item.get("content") or ""),
            }
        )
    return results


def _search(query: str, max_results: int = 5) -> str:
    max_results = max(1, min(10, max_results))

    try:
        return _format_results(query, _google_search(query, max_results))
    except Exception as google_error:
        try:
            return _format_results(query, _tavily_search(query, max_results))
        except Exception as tavily_error:
            return f"Search error: Google failed ({google_error}); Tavily fallback failed ({tavily_error})"


web_search_tool = StructuredTool.from_function(
    name="web_search",
    func=_search,
    description=(
        "Search the web for current information using Google first, with Tavily fallback. "
        "Returns titles, URLs, and content snippets. "
        "Use for facts, documentation, news, or anything not in the codebase."
    ),
    args_schema=WebSearchInput,
)

tavily_search = web_search_tool
