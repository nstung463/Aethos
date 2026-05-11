"""Runtime loop guard helpers for chat execution paths."""

from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage

from src.app.services.settings import SettingsService
from src.logger import get_logger

logger = get_logger(__name__)

DEFAULT_GRAPH_RECURSION_LIMIT = 100
MIN_GRAPH_RECURSION_LIMIT = 25
MAX_GRAPH_RECURSION_LIMIT = 500

DEFAULT_CONTINUATION_NUDGE_LIMIT = 3
MAX_CONTINUATION_NUDGE_LIMIT = 10

GRAPH_RECURSION_STOP_REASON = "graph_recursion_limit"
CONTINUATION_NUDGE_STOP_REASON = "continuation_nudge_limit"
CONTINUATION_NUDGE_MESSAGE = "Continue with the task. Use the appropriate tools to proceed."

_COMPLETION_MARKERS = re.compile(
    r"\b(done|finished|completed|complete|summary|that's all|that is all|all set|hope this helps|let me know if|"
    r"xong|hoan thanh|hoan tat|da xong|da hoan thanh|da hoan tat|tong ket)\b"
)
_ACTION_VERBS = "do|create|write|edit|update|fix|implement|add|run|check|make|build|set up"
_VIETNAMESE_ACTION_VERBS = (
    "lam|tao|viet|sua|cap nhat|khac phuc|fix|trien khai|them|chay|kiem tra|"
    "xay dung|cai dat|xem|doc|review|ra soat|dieu tra|phan tich|mo"
)


def _normalize_guard_text(text: str) -> str:
    lowered = " ".join(text.lower().split())
    # Normalize Vietnamese d-stroke and common mojibake so accent stripping
    # can map both Unicode and legacy-broken text to the same ASCII form.
    lowered = lowered.replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", lowered)
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


@dataclass(frozen=True)
class LoopGuardSettings:
    graph_recursion_limit: int = DEFAULT_GRAPH_RECURSION_LIMIT
    continuation_nudge_limit: int = DEFAULT_CONTINUATION_NUDGE_LIMIT
    continuation_nudge_enabled: bool = True


@dataclass(frozen=True)
class ContinuationDecision:
    should_nudge: bool
    stop_after_cap: bool = False
    matched_text: str = ""


def _parse_int_env(name: str) -> int | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        logger.warning("Ignoring invalid integer env override %s=%r", name, raw)
        return None


def _parse_bool_env(name: str) -> bool | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    logger.warning("Ignoring invalid boolean env override %s=%r", name, raw)
    return None


def _coerce_bool(value: Any, *, default: bool, source: str) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    logger.warning("Ignoring invalid %s value %r; using default=%s", source, value, default)
    return default


def _coerce_int(
    value: Any,
    *,
    default: int,
    minimum: int,
    maximum: int,
    source: str,
) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        logger.warning("Ignoring invalid %s value %r; using default=%s", source, value, default)
        return default
    if parsed < minimum or parsed > maximum:
        logger.warning(
            "Ignoring out-of-range %s value %r; expected between %s and %s, using default=%s",
            source,
            value,
            minimum,
            maximum,
            default,
        )
        return default
    return parsed


def resolve_loop_guard_settings(*, workspace_root: str | Path | None = None) -> LoopGuardSettings:
    settings_data = SettingsService().get_effective_settings(workspace_root=workspace_root)
    agent_loop = settings_data.get("agentLoop") if isinstance(settings_data, dict) else None
    if not isinstance(agent_loop, dict):
        agent_loop = {}

    recursion_env = _parse_int_env("AETHOS_GRAPH_RECURSION_LIMIT")
    continuation_limit_env = _parse_int_env("AETHOS_CONTINUATION_NUDGE_LIMIT")
    recursion_limit = _coerce_int(
        recursion_env if recursion_env is not None else agent_loop.get("recursionLimit"),
        default=DEFAULT_GRAPH_RECURSION_LIMIT,
        minimum=MIN_GRAPH_RECURSION_LIMIT,
        maximum=MAX_GRAPH_RECURSION_LIMIT,
        source="agentLoop.recursionLimit",
    )
    continuation_limit = _coerce_int(
        continuation_limit_env if continuation_limit_env is not None else agent_loop.get("continuationNudgeLimit"),
        default=DEFAULT_CONTINUATION_NUDGE_LIMIT,
        minimum=0,
        maximum=MAX_CONTINUATION_NUDGE_LIMIT,
        source="agentLoop.continuationNudgeLimit",
    )

    continuation_enabled_env = _parse_bool_env("AETHOS_CONTINUATION_NUDGE_ENABLED")
    continuation_enabled_raw = (
        continuation_enabled_env
        if continuation_enabled_env is not None
        else agent_loop.get("continuationNudgeEnabled", True)
    )
    continuation_enabled = _coerce_bool(
        continuation_enabled_raw,
        default=True,
        source="agentLoop.continuationNudgeEnabled",
    )

    return LoopGuardSettings(
        graph_recursion_limit=recursion_limit,
        continuation_nudge_limit=continuation_limit,
        continuation_nudge_enabled=continuation_enabled,
    )


def with_loop_guard_config(
    config: dict[str, Any] | None,
    *,
    thread_id: str,
    settings: LoopGuardSettings,
    continuation_nudge_count: int = 0,
) -> dict[str, Any]:
    merged_config: dict[str, Any] = dict(config or {})
    configurable = dict(merged_config.get("configurable") or {})
    configurable.setdefault("thread_id", thread_id)
    configurable["agent_loop"] = {
        "recursion_limit": settings.graph_recursion_limit,
        "continuation_nudge_limit": settings.continuation_nudge_limit,
        "continuation_nudge_enabled": settings.continuation_nudge_enabled,
        "continuation_nudge_count": continuation_nudge_count,
    }
    merged_config["configurable"] = configurable
    merged_config["recursion_limit"] = settings.graph_recursion_limit
    return merged_config


class ContinuationNudgeGuard:
    """Detect short assistant replies that signal intent to continue without acting."""

    _patterns: tuple[re.Pattern[str], ...] = (
        re.compile(
            r"\bso now (i|let me|we) (need to|have to|should|must|will) "
            rf"({_ACTION_VERBS})\b"
        ),
        re.compile(
            r"\bnow i('ll| will) "
            rf"({_ACTION_VERBS}|go|proceed)\b"
        ),
        re.compile(
            r"\blet me (go ahead and |now )?"
            rf"({_ACTION_VERBS}|proceed)\b"
        ),
        re.compile(
            r"\btime to "
            rf"({_ACTION_VERBS}|get started|begin)\b"
        ),
        re.compile(
            r"\b(gio|bay gio) (toi|minh|ta) se "
            rf"({_VIETNAMESE_ACTION_VERBS})\b"
        ),
        re.compile(
            r"\b(de|de cho) (toi|minh) "
            rf"({_VIETNAMESE_ACTION_VERBS})\b"
        ),
        re.compile(
            r"\b(vay gio|gio thi) (toi|minh) (can|se) "
            rf"({_VIETNAMESE_ACTION_VERBS})\b"
        ),
    )
    _short_patterns: tuple[re.Pattern[str], ...] = (
        re.compile(
            r"\b(i('ll| will| need to| have to| must) (now )?"
            rf"({_ACTION_VERBS}))\b"
        ),
        re.compile(
            r"\bnext,?\s+(i('ll| will)|let me|i need to) "
            rf"({_ACTION_VERBS})\b"
        ),
        re.compile(
            r"\b(toi|minh) (se|can|phai) "
            rf"({_VIETNAMESE_ACTION_VERBS})\b"
        ),
    )

    def evaluate(
        self,
        *,
        assistant_text: str,
        saw_tool_event: bool,
        saw_interrupt: bool,
        nudge_count: int,
        settings: LoopGuardSettings,
    ) -> ContinuationDecision:
        normalized = _normalize_guard_text(assistant_text)
        if not settings.continuation_nudge_enabled or settings.continuation_nudge_limit <= 0:
            return ContinuationDecision(should_nudge=False)
        if not normalized or saw_tool_event or saw_interrupt:
            return ContinuationDecision(should_nudge=False)
        if _COMPLETION_MARKERS.search(normalized):
            return ContinuationDecision(should_nudge=False)

        matched = any(pattern.search(normalized) for pattern in self._patterns)
        if not matched and len(normalized) < 80:
            matched = any(pattern.search(normalized) for pattern in self._short_patterns)
        if not matched:
            return ContinuationDecision(should_nudge=False)
        if nudge_count >= settings.continuation_nudge_limit:
            return ContinuationDecision(
                should_nudge=False,
                stop_after_cap=True,
                matched_text=normalized,
            )
        return ContinuationDecision(should_nudge=True, matched_text=normalized)


def build_continuation_nudge_input() -> dict[str, list[HumanMessage]]:
    return {"messages": [HumanMessage(content=CONTINUATION_NUDGE_MESSAGE)]}
