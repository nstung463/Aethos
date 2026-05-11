from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.app.modules.chat.loop_guards import (
    CONTINUATION_NUDGE_STOP_REASON,
    DEFAULT_GRAPH_RECURSION_LIMIT,
    ContinuationNudgeGuard,
    resolve_loop_guard_settings,
)
from src.app.modules.chat.service import ChatService


def test_continuation_guard_matches_short_action_intent() -> None:
    guard = ContinuationNudgeGuard()
    settings = resolve_loop_guard_settings()

    decision = guard.evaluate(
        assistant_text="I'll update the file now",
        saw_tool_event=False,
        saw_interrupt=False,
        nudge_count=0,
        settings=settings,
    )

    assert decision.should_nudge is True


def test_continuation_guard_matches_short_action_intent_vietnamese() -> None:
    guard = ContinuationNudgeGuard()
    settings = resolve_loop_guard_settings()

    decision = guard.evaluate(
        assistant_text="minh se cap nhat file ngay",
        saw_tool_event=False,
        saw_interrupt=False,
        nudge_count=0,
        settings=settings,
    )

    assert decision.should_nudge is True


def test_continuation_guard_matches_short_action_intent_vietnamese_with_diacritics() -> None:
    guard = ContinuationNudgeGuard()
    settings = resolve_loop_guard_settings()

    decision = guard.evaluate(
        assistant_text="mình sẽ cập nhật file ngay",
        saw_tool_event=False,
        saw_interrupt=False,
        nudge_count=0,
        settings=settings,
    )

    assert decision.should_nudge is True


def test_continuation_guard_matches_vietnamese_phrase_with_de_toi() -> None:
    guard = ContinuationNudgeGuard()
    settings = resolve_loop_guard_settings()

    decision = guard.evaluate(
        assistant_text="để tôi cập nhật file",
        saw_tool_event=False,
        saw_interrupt=False,
        nudge_count=0,
        settings=settings,
    )

    assert decision.should_nudge is True


def test_continuation_guard_ignores_completion_text() -> None:
    guard = ContinuationNudgeGuard()
    settings = resolve_loop_guard_settings()

    decision = guard.evaluate(
        assistant_text="Done, summary below",
        saw_tool_event=False,
        saw_interrupt=False,
        nudge_count=0,
        settings=settings,
    )

    assert decision.should_nudge is False


def test_continuation_guard_ignores_completion_text_vietnamese() -> None:
    guard = ContinuationNudgeGuard()
    settings = resolve_loop_guard_settings()

    decision = guard.evaluate(
        assistant_text="da xong, tong ket ben duoi",
        saw_tool_event=False,
        saw_interrupt=False,
        nudge_count=0,
        settings=settings,
    )

    assert decision.should_nudge is False


def test_continuation_guard_ignores_completion_text_vietnamese_with_diacritics() -> None:
    guard = ContinuationNudgeGuard()
    settings = resolve_loop_guard_settings()

    decision = guard.evaluate(
        assistant_text="đã xong, tổng kết bên dưới",
        saw_tool_event=False,
        saw_interrupt=False,
        nudge_count=0,
        settings=settings,
    )

    assert decision.should_nudge is False


def test_continuation_guard_ignores_completion_text_vietnamese_mojibake_d_stroke() -> None:
    guard = ContinuationNudgeGuard()
    settings = resolve_loop_guard_settings()

    decision = guard.evaluate(
        assistant_text="Đã xong, tổng kết bên dưới",
        saw_tool_event=False,
        saw_interrupt=False,
        nudge_count=0,
        settings=settings,
    )

    assert decision.should_nudge is False


def test_continuation_guard_ignores_explanatory_text() -> None:
    guard = ContinuationNudgeGuard()
    settings = resolve_loop_guard_settings()

    decision = guard.evaluate(
        assistant_text="I'll explain what happened",
        saw_tool_event=False,
        saw_interrupt=False,
        nudge_count=0,
        settings=settings,
    )

    assert decision.should_nudge is False


def test_continuation_guard_respects_cap() -> None:
    guard = ContinuationNudgeGuard()
    settings = resolve_loop_guard_settings()

    decision = guard.evaluate(
        assistant_text="I'll update the file now",
        saw_tool_event=False,
        saw_interrupt=False,
        nudge_count=settings.continuation_nudge_limit,
        settings=settings,
    )

    assert decision.should_nudge is False
    assert decision.stop_after_cap is True


def test_loop_guard_settings_reads_agent_loop_from_effective_settings(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home-aethos"
    managed = tmp_path / "managed-settings"
    workspace = tmp_path / "workspace"
    (workspace / ".aethos").mkdir(parents=True)
    home.mkdir(parents=True)
    managed.mkdir(parents=True)
    monkeypatch.setenv("AETHOS_CONFIG_HOME", str(home))
    monkeypatch.setenv("AETHOS_MANAGED_SETTINGS_DIR", str(managed))
    (workspace / ".aethos" / "settings.json").write_text(
        json.dumps({"agentLoop": {"recursionLimit": 140, "continuationNudgeLimit": 2, "continuationNudgeEnabled": True}}),
        encoding="utf-8",
    )

    settings = resolve_loop_guard_settings(workspace_root=workspace)

    assert settings.graph_recursion_limit == 140
    assert settings.continuation_nudge_limit == 2
    assert settings.continuation_nudge_enabled is True


def test_loop_guard_settings_env_override_wins(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    (workspace / ".aethos").mkdir(parents=True)
    (workspace / ".aethos" / "settings.json").write_text(
        json.dumps({"agentLoop": {"recursionLimit": 140}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("AETHOS_GRAPH_RECURSION_LIMIT", "160")

    settings = resolve_loop_guard_settings(workspace_root=workspace)

    assert settings.graph_recursion_limit == 160


def test_loop_guard_settings_invalid_values_fall_back(monkeypatch) -> None:
    monkeypatch.setenv("AETHOS_GRAPH_RECURSION_LIMIT", "12")
    monkeypatch.setenv("AETHOS_CONTINUATION_NUDGE_LIMIT", "nope")

    settings = resolve_loop_guard_settings()

    assert settings.graph_recursion_limit == DEFAULT_GRAPH_RECURSION_LIMIT
    assert settings.continuation_nudge_limit >= 0


def test_loop_guard_settings_parses_string_false_for_continuation_enabled(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    (workspace / ".aethos").mkdir(parents=True)
    (workspace / ".aethos" / "settings.json").write_text(
        json.dumps({"agentLoop": {"continuationNudgeEnabled": "false"}}),
        encoding="utf-8",
    )

    settings = resolve_loop_guard_settings(workspace_root=workspace)

    assert settings.continuation_nudge_enabled is False


def test_tool_progress_detection_only_counts_after_last_human() -> None:
    messages = [
        HumanMessage(content="first"),
        ToolMessage(content="old result", tool_call_id="call-old"),
        HumanMessage(content="new request"),
        AIMessage(content="I'll inspect the code now"),
    ]

    assert ChatService._saw_tool_after_last_human(messages) is False


def test_tool_progress_detection_counts_current_iteration_tool() -> None:
    messages = [
        HumanMessage(content="new request"),
        AIMessage(content="using a tool"),
        ToolMessage(content="current result", tool_call_id="call-new"),
    ]

    assert ChatService._saw_tool_after_last_human(messages) is True
