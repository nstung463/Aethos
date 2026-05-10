"""Approximate context window status for the chat composer UI."""

from __future__ import annotations

import math
import json
from pathlib import Path
from typing import Any

from src.ai.agents.aethos import build_aethos_tools
from src.ai.agents.subagents import DEFAULT_SUBAGENTS, TASK_DESCRIPTION, TaskInput
from src.ai.middleware.environment import build_environment_section, collect_project_instruction_files
from src.ai.middleware.memory import MEMORY_TEMPLATE
from src.ai.middleware.mcp_instructions import build_mcp_instructions_section
from src.ai.middleware.skills import SKILLS_TEMPLATE
from src.ai.prompts.catalog import BASE_SYSTEM_PROMPT
from src.ai.skills import SkillRegistry
from src.app.services.storage_paths import StoragePathsService
from src.config import MCPServerSpec

TOOL_SCHEMA_FALLBACK_TOKENS = 12_000
GRID_WIDTH = 10
GRID_HEIGHT = 10

def estimate_tokens(text: str) -> int:
    """Cheap provider-agnostic token estimate for UI status."""
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def _stringify_content(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for block in value:
            if isinstance(block, dict):
                block_type = block.get("type")
                if block_type == "text":
                    parts.append(str(block.get("text") or ""))
                elif block_type == "thinking":
                    parts.append(str(block.get("thinking") or ""))
                elif block_type == "tool_use":
                    parts.append(str(block.get("name") or ""))
                    parts.append(str(block.get("input") or ""))
                elif block_type == "tool_result":
                    parts.append(str(block.get("content") or ""))
                else:
                    parts.append(str(block))
            else:
                parts.append(str(block))
        return "\n".join(part for part in parts if part)
    return str(value)


def _extract_input_tokens(usage: Any) -> int | None:
    if not isinstance(usage, dict):
        return None
    for key in ("input_tokens", "prompt_tokens"):
        value = usage.get(key)
        if isinstance(value, int) and value >= 0:
            return value
    token_usage = usage.get("token_usage")
    if isinstance(token_usage, dict):
        return _extract_input_tokens(token_usage)
    return None


def _latest_reported_input_tokens(messages: list[dict[str, Any]]) -> int | None:
    for message in reversed(messages):
        usage_tokens = _extract_input_tokens(message.get("usage"))
        if usage_tokens is not None:
            return usage_tokens
        metadata = message.get("response_metadata")
        if isinstance(metadata, dict):
            usage_tokens = _extract_input_tokens(metadata.get("usage") or metadata.get("token_usage"))
            if usage_tokens is not None:
                return usage_tokens
    return None


def _scale_categories_to_total(categories: list[dict[str, Any]], total_tokens: int, context_window: int) -> None:
    estimated_total = sum(int(category["tokens"]) for category in categories)
    if total_tokens < 0 or estimated_total <= 0 or total_tokens == estimated_total:
        return
    scaled_total = 0
    for category in categories:
        scaled_tokens = round((int(category["tokens"]) / estimated_total) * total_tokens)
        category["tokens"] = max(0, scaled_tokens)
        category["percent"] = round((category["tokens"] / context_window) * 100, 1) if context_window else 0
        category["is_scaled_from_provider"] = True
        scaled_total += int(category["tokens"])
    if categories:
        correction = total_tokens - scaled_total
        categories[-1]["tokens"] = max(0, int(categories[-1]["tokens"]) + correction)
        categories[-1]["percent"] = round((categories[-1]["tokens"] / context_window) * 100, 1) if context_window else 0


def _schema_for_tool(tool: Any) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "name": str(getattr(tool, "name", "")),
        "description": str(getattr(tool, "description", "")),
    }
    args_schema = getattr(tool, "args_schema", None)
    if args_schema is not None:
        if hasattr(args_schema, "model_json_schema"):
            schema["parameters"] = args_schema.model_json_schema()
        elif hasattr(args_schema, "schema"):
            schema["parameters"] = args_schema.schema()
    elif hasattr(tool, "args"):
        schema["parameters"] = getattr(tool, "args")
    return schema


def _task_tool_schema() -> dict[str, Any]:
    agents_desc = "\n".join(f"- {spec['name']}: {spec['description']}" for spec in DEFAULT_SUBAGENTS)
    return {
        "name": "task",
        "description": TASK_DESCRIPTION.format(available_agents=agents_desc),
        "parameters": TaskInput.model_json_schema(),
    }


def estimate_tool_schema_tokens(*, root_dir: str, owner_user_id: str | None = None) -> int:
    try:
        tools = build_aethos_tools(root_dir=root_dir, owner_user_id=owner_user_id, include_task_tool=False)
        schemas = [_schema_for_tool(tool) for tool in tools]
        schemas.append(_task_tool_schema())
        payload = json.dumps(schemas, ensure_ascii=False, sort_keys=True, default=str)
        return estimate_tokens(payload)
    except Exception:
        return TOOL_SCHEMA_FALLBACK_TOKENS


def context_window_for_model(model: str, override: int | None = None) -> int:
    if isinstance(override, int) and override > 0:
        return override
    normalized = model.lower()
    if "gemini" in normalized or "1m" in normalized:
        return 1_000_000
    if "gpt-5" in normalized or "gpt5" in normalized:
        return 256_000
    if "gpt-4.1" in normalized or "o3" in normalized or "o4" in normalized:
        return 1_000_000
    if "claude" in normalized:
        return 200_000
    if "gpt-4o" in normalized or "gpt-4" in normalized:
        return 128_000
    return 128_000


def _safe_root(root_dir: str) -> Path:
    root = Path(root_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Project root_dir is invalid: {root}")
    return root


def _category(
    key: str,
    label: str,
    tokens: int,
    context_window: int,
    *,
    source: str | None = None,
) -> dict[str, Any]:
    safe_tokens = max(0, tokens)
    return {
        "key": key,
        "label": label,
        "tokens": safe_tokens,
        "percent": round((safe_tokens / context_window) * 100, 1) if context_window else 0,
        "source": source,
    }


def _build_grid(categories: list[dict[str, Any]], context_window: int) -> list[list[dict[str, Any]]]:
    squares: list[dict[str, Any]] = []
    total_squares = GRID_WIDTH * GRID_HEIGHT
    non_deferred = [category for category in categories if not category.get("is_deferred")]
    cumulative: list[tuple[int, dict[str, Any]]] = []
    running = 0
    for category in non_deferred:
        running += int(category["tokens"])
        cumulative.append((running, category))

    for index in range(total_squares):
        midpoint = int(((index + 0.5) / total_squares) * context_window)
        selected = non_deferred[-1] if non_deferred else None
        for threshold, category in cumulative:
            if midpoint <= threshold:
                selected = category
                break
        if selected is None:
            squares.append({"category_key": "free", "category_label": "Free space", "tokens": 0})
        else:
            squares.append(
                {
                    "category_key": selected["key"],
                    "category_label": selected["label"],
                    "tokens": selected["tokens"],
                }
            )

    return [squares[i : i + GRID_WIDTH] for i in range(0, len(squares), GRID_WIDTH)]


def _build_suggestions(
    *,
    percent_used: int,
    context_window: int,
    memory_tokens: int,
    message_tokens: int,
    tool_tokens: int,
) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    if percent_used >= 80:
        suggestions.append(
            {
                "severity": "warning",
                "title_key": "context.suggestions.nearCapacity.title",
                "detail_key": "context.suggestions.nearCapacity.detail",
                "tokens": 0,
            }
        )
    if memory_tokens >= 5_000 and (memory_tokens / context_window) >= 0.05:
        suggestions.append(
            {
                "severity": "info",
                "title_key": "context.suggestions.memoryHeavy.title",
                "detail_key": "context.suggestions.memoryHeavy.detail",
                "tokens": memory_tokens,
            }
        )
    if message_tokens >= 10_000 and (message_tokens / context_window) >= 0.15:
        suggestions.append(
            {
                "severity": "info",
                "title_key": "context.suggestions.messagesHeavy.title",
                "detail_key": "context.suggestions.messagesHeavy.detail",
                "tokens": message_tokens,
            }
        )
    if context_window > 0 and (tool_tokens / context_window) >= 0.05:
        suggestions.append(
            {
                "severity": "info",
                "title_key": "context.suggestions.toolsEstimated.title",
                "detail_key": "context.suggestions.toolsEstimated.detail",
                "tokens": tool_tokens,
            }
        )
    return suggestions


def build_context_status(
    *,
    root_dir: str,
    model: str,
    messages: list[dict[str, Any]],
    context_window: int | None = None,
    mcp_servers: list[MCPServerSpec] | None = None,
    owner_user_id: str | None = None,
) -> dict[str, Any]:
    root = _safe_root(root_dir)
    resolved_context_window = context_window_for_model(model, context_window)
    reported_input_tokens = _latest_reported_input_tokens(messages)
    activated_rules: list[dict[str, Any]] = []
    categories: list[dict[str, Any]] = []

    system_prompt_tokens = estimate_tokens(BASE_SYSTEM_PROMPT)
    environment_section = build_environment_section(str(root), model_name=model)
    environment_tokens = estimate_tokens(environment_section)
    for item in collect_project_instruction_files(str(root)):
        token_count = estimate_tokens(item["content"])
        activated_rules.append(
            {
                "path": item["path"],
                "name": item["name"],
                "source": "project_instructions",
                "tokens": token_count,
            }
        )

    categories.append(_category("system_prompt", "System prompt", system_prompt_tokens, resolved_context_window))
    categories.append(_category("environment", "Environment and rules", environment_tokens, resolved_context_window))

    memory_tokens = 0
    memory_chunks: list[tuple[Path, str]] = []
    agents_path = root / "AGENTS.md"
    if agents_path.exists():
        content = agents_path.read_text(encoding="utf-8").strip()
        if content:
            memory_chunks.append((agents_path, f"## Project Instructions ({agents_path.name})\n{content}"))
    auto_memory_path = StoragePathsService().memory_file(root)
    if auto_memory_path.exists():
        content = auto_memory_path.read_text(encoding="utf-8").strip()
        if content:
            memory_chunks.append((auto_memory_path, f"## Auto Memory ({auto_memory_path})\n{content}"))

    if memory_chunks:
        memory_content = "\n\n".join(chunk for _, chunk in memory_chunks)
        memory_tokens = estimate_tokens(MEMORY_TEMPLATE.format(content=memory_content))
        for path, chunk in memory_chunks:
            activated_rules.append(
                {
                    "path": str(path),
                    "name": path.name,
                    "source": "memory",
                    "tokens": estimate_tokens(chunk),
                }
            )
        categories.append(_category("memory", "Memory files", memory_tokens, resolved_context_window))

    mcp_section = build_mcp_instructions_section(mcp_servers or [])
    mcp_tokens = 0
    if mcp_section:
        mcp_tokens = estimate_tokens(mcp_section)
        categories.append(_category("mcp_instructions", "MCP instructions", mcp_tokens, resolved_context_window))

    skills_listing = SkillRegistry(root).render_listing(max_chars=8000)
    skill_tokens = 0
    if skills_listing:
        skill_tokens = estimate_tokens(SKILLS_TEMPLATE.format(skills_list=skills_listing))
        categories.append(_category("skills", "Skills", skill_tokens, resolved_context_window))

    message_tokens = 0
    for message in messages:
        role = str(message.get("role", ""))
        content = _stringify_content(message.get("content"))
        reasoning = str(message.get("reasoning_content") or message.get("reasoning") or "")
        message_tokens += estimate_tokens(f"{role}\n{content}\n{reasoning}") + 4
    if message_tokens:
        categories.append(_category("messages", "Messages", message_tokens, resolved_context_window))

    tool_tokens = estimate_tool_schema_tokens(root_dir=str(root), owner_user_id=owner_user_id)
    categories.append(_category("tools", "System tools", tool_tokens, resolved_context_window, source="runtime_schema"))

    if reported_input_tokens is not None:
        _scale_categories_to_total(categories, reported_input_tokens, resolved_context_window)

    used_tokens = sum(int(category["tokens"]) for category in categories)
    percent_used = min(100, round((used_tokens / resolved_context_window) * 100)) if resolved_context_window else 0
    free_tokens = max(0, resolved_context_window - used_tokens)
    categories.append(_category("free", "Free space", free_tokens, resolved_context_window))

    return {
        "context_window": resolved_context_window,
        "used_tokens": used_tokens,
        "percent_used": percent_used,
        "categories": categories,
        "grid_rows": _build_grid(categories, resolved_context_window),
        "suggestions": _build_suggestions(
            percent_used=percent_used,
            context_window=resolved_context_window,
            memory_tokens=memory_tokens,
            message_tokens=message_tokens,
            tool_tokens=tool_tokens,
        ),
        "activated_rules": activated_rules,
        "is_estimated": reported_input_tokens is None,
    }
