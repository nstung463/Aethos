from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.base import empty_checkpoint

from src.app.services.async_jsonl_checkpointer import AsyncJsonlCheckpointSaver


@pytest.mark.asyncio
async def test_async_jsonl_checkpointer_round_trips_checkpoint_and_writes(tmp_path: Path) -> None:
    saver = AsyncJsonlCheckpointSaver(tmp_path)
    config = {"configurable": {"thread_id": "thread-1", "checkpoint_ns": ""}}
    checkpoint = empty_checkpoint()
    checkpoint["id"] = "cp-1"
    checkpoint["channel_values"] = {"messages": [HumanMessage(content="hello")]}
    metadata = {"source": "input", "step": 1}

    saved_config = await saver.aput(config, checkpoint, metadata, {})
    await saver.aput_writes(
        saved_config,
        [("tasks", {"done": False}), ("custom", "value")],
        task_id="task-1",
    )

    restored = await saver.aget_tuple(saved_config)
    assert restored is not None
    assert restored.config["configurable"]["checkpoint_id"] == "cp-1"
    assert restored.checkpoint["id"] == "cp-1"
    assert restored.metadata["source"] == "input"
    assert restored.metadata["step"] == 1
    assert restored.pending_writes == [
        ("task-1", "tasks", {"done": False}),
        ("task-1", "custom", "value"),
    ]
    state_entries = [
        json.loads(line)
        for line in (tmp_path / "checkpoints" / "thread-1" / "checkpoint_state.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(state_entries) == 1
    assert len(state_entries[0]["pending_writes"]) == 2

    message_entries = await saver.get_full_message_entries(config)
    assert len(message_entries) == 1
    assert message_entries[0]["checkpointId"] == "cp-1"
    assert message_entries[0]["type"] == "user"
    assert message_entries[0]["message"]["content"][0]["text"] == "hello"


@pytest.mark.asyncio
async def test_async_jsonl_checkpointer_returns_latest_checkpoint_when_id_not_specified(
    tmp_path: Path,
) -> None:
    saver = AsyncJsonlCheckpointSaver(tmp_path)
    config = {"configurable": {"thread_id": "thread-2", "checkpoint_ns": ""}}

    first = empty_checkpoint()
    first["id"] = "cp-1"
    first["channel_values"] = {"messages": [HumanMessage(content="first")]}
    second = empty_checkpoint()
    second["id"] = "cp-2"
    second["channel_values"] = {"messages": [HumanMessage(content="second")]}

    first_config = await saver.aput(config, first, {"step": 1}, {})
    second_config = await saver.aput(first_config, second, {"step": 2}, {})

    latest = await saver.aget_tuple(config)
    assert latest is not None
    assert latest.config["configurable"]["checkpoint_id"] == "cp-2"
    assert latest.parent_config == {
        "configurable": {
            "thread_id": "thread-2",
            "checkpoint_ns": "",
            "checkpoint_id": "cp-1",
        }
    }

    listed = [item async for item in saver.alist(config, limit=2)]
    assert [item.config["configurable"]["checkpoint_id"] for item in listed] == ["cp-2", "cp-1"]
    assert second_config["configurable"]["checkpoint_id"] == "cp-2"


@pytest.mark.asyncio
async def test_async_jsonl_checkpointer_writes_claude_style_events_without_replayed_messages(
    tmp_path: Path,
) -> None:
    saver = AsyncJsonlCheckpointSaver(tmp_path)
    config = {"configurable": {"thread_id": "thread-3", "checkpoint_ns": ""}}

    user_message = HumanMessage(content="hello")
    assistant_message = AIMessage(content="hi there")

    first = empty_checkpoint()
    first["id"] = "cp-1"
    first["channel_values"] = {"messages": [user_message]}
    second = empty_checkpoint()
    second["id"] = "cp-2"
    second["channel_values"] = {"messages": [user_message, assistant_message]}

    first_config = await saver.aput(config, first, {"step": 1}, {})
    await saver.aput(first_config, second, {"step": 2}, {})

    events_path = tmp_path / "checkpoints" / "thread-3" / "messages.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]

    assert len(events) == 2
    assert [event["type"] for event in events] == ["user", "assistant"]
    assert events[0]["message"]["content"][0]["text"] == "hello"
    assert events[1]["message"]["content"][0]["text"] == "hi there"
    assert events[1]["parentUuid"] == events[0]["uuid"]


@pytest.mark.asyncio
async def test_async_jsonl_checkpointer_serializes_reasoning_content(tmp_path: Path) -> None:
    saver = AsyncJsonlCheckpointSaver(tmp_path)
    config = {"configurable": {"thread_id": "thread-reasoning", "checkpoint_ns": ""}}
    checkpoint = empty_checkpoint()
    checkpoint["id"] = "cp-1"
    checkpoint["channel_values"] = {
        "messages": [
            AIMessage(
                content="Using a tool.",
                additional_kwargs={"reasoning_content": "Need to inspect the workbook first."},
            ),
        ]
    }

    await saver.aput(config, checkpoint, {"step": 1}, {})

    events_path = tmp_path / "checkpoints" / "thread-reasoning" / "messages.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]

    assert len(events) == 2
    thinking_message = events[0]["message"]
    text_message = events[1]["message"]
    assert thinking_message["reasoning_content"] == "Need to inspect the workbook first."
    assert thinking_message["content"] == [
        {"type": "thinking", "thinking": "Need to inspect the workbook first."},
    ]
    assert text_message["content"] == [{"type": "text", "text": "Using a tool."}]
    assert events[1]["parentUuid"] == events[0]["uuid"]


@pytest.mark.asyncio
async def test_async_jsonl_checkpointer_serializes_reasoning_before_tool_calls(tmp_path: Path) -> None:
    saver = AsyncJsonlCheckpointSaver(tmp_path)
    config = {"configurable": {"thread_id": "thread-reasoning-tool", "checkpoint_ns": ""}}
    checkpoint = empty_checkpoint()
    checkpoint["id"] = "cp-1"
    checkpoint["channel_values"] = {
        "messages": [
            AIMessage(
                content="",
                additional_kwargs={"reasoning_content": "Need to inspect the project first."},
                tool_calls=[{"id": "call-1", "name": "list_files", "args": {"path": "."}}],
            ),
        ]
    }

    await saver.aput(config, checkpoint, {"step": 1}, {})

    events_path = tmp_path / "checkpoints" / "thread-reasoning-tool" / "messages.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]

    assert len(events) == 2
    assert events[0]["message"]["content"] == [
        {"type": "thinking", "thinking": "Need to inspect the project first."},
    ]
    assert events[1]["message"]["content"][0]["type"] == "tool_use"
    assert events[1]["message"]["content"][0]["name"] == "list_files"
    assert events[1]["parentUuid"] == events[0]["uuid"]


@pytest.mark.asyncio
async def test_async_jsonl_checkpointer_splits_thinking_text_and_tool_rows(tmp_path: Path) -> None:
    saver = AsyncJsonlCheckpointSaver(tmp_path)
    config = {"configurable": {"thread_id": "thread-reasoning-text-tool", "checkpoint_ns": ""}}
    checkpoint = empty_checkpoint()
    checkpoint["id"] = "cp-1"
    checkpoint["channel_values"] = {
        "messages": [
            AIMessage(
                content="I will inspect the project.",
                additional_kwargs={"reasoning_content": "Need to inspect before writing."},
                tool_calls=[{"id": "call-1", "name": "list_files", "args": {"path": "."}}],
            ),
        ]
    }

    await saver.aput(config, checkpoint, {"step": 1}, {})

    events_path = tmp_path / "checkpoints" / "thread-reasoning-text-tool" / "messages.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]

    assert [event["message"]["content"][0]["type"] for event in events] == ["thinking", "text", "tool_use"]
    assert events[1]["parentUuid"] == events[0]["uuid"]
    assert events[2]["parentUuid"] == events[1]["uuid"]


@pytest.mark.asyncio
async def test_async_jsonl_checkpointer_serializes_tool_calls_and_results_in_events(
    tmp_path: Path,
) -> None:
    saver = AsyncJsonlCheckpointSaver(tmp_path)
    config = {"configurable": {"thread_id": "thread-4", "checkpoint_ns": ""}}
    checkpoint = empty_checkpoint()
    checkpoint["id"] = "cp-1"
    checkpoint["channel_values"] = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[{"id": "call-1", "name": "list_files", "args": {"path": "."}}],
            ),
            ToolMessage(content="README.md", tool_call_id="call-1"),
        ]
    }

    await saver.aput(config, checkpoint, {"step": 1}, {})

    events_path = tmp_path / "checkpoints" / "thread-4" / "messages.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]

    tool_use = events[0]["message"]["content"][0]
    tool_result = events[1]["message"]["content"][0]
    assert tool_use == {
        "type": "tool_use",
        "id": "call-1",
        "name": "list_files",
        "input": {"path": "."},
    }
    assert tool_result == {
        "type": "tool_result",
        "tool_use_id": "call-1",
        "content": "README.md",
    }


@pytest.mark.asyncio
async def test_async_jsonl_checkpointer_appends_interruption_once(tmp_path: Path) -> None:
    saver = AsyncJsonlCheckpointSaver(tmp_path)
    config = {"configurable": {"thread_id": "thread-stop", "checkpoint_ns": ""}}
    checkpoint = empty_checkpoint()
    checkpoint["id"] = "cp-1"
    checkpoint["channel_values"] = {"messages": [HumanMessage(content="start")]}

    await saver.aput(config, checkpoint, {"step": 1}, {})
    first = await saver.append_interruption_event(
        thread_id="thread-stop",
        run_id="run-1",
        reason="user_cancel",
    )
    second = await saver.append_interruption_event(
        thread_id="thread-stop",
        run_id="run-1",
        reason="user_cancel",
    )

    events_path = tmp_path / "checkpoints" / "thread-stop" / "messages.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]

    assert first is not None
    assert second is None
    assert len(events) == 2
    assert events[1]["type"] == "interruption"
    assert events[1]["message"]["content"][0]["text"] == "[Request interrupted by user]"
    assert events[1]["runId"] == "run-1"
    assert events[1]["interruptionReason"] == "user_cancel"
    assert events[1]["parentUuid"] == events[0]["uuid"]


@pytest.mark.asyncio
async def test_async_jsonl_checkpointer_concurrent_interruption_append_is_idempotent(tmp_path: Path) -> None:
    saver = AsyncJsonlCheckpointSaver(tmp_path)
    config = {"configurable": {"thread_id": "thread-stop-race", "checkpoint_ns": ""}}
    checkpoint = empty_checkpoint()
    checkpoint["id"] = "cp-1"
    checkpoint["channel_values"] = {"messages": [HumanMessage(content="start")]}

    await saver.aput(config, checkpoint, {"step": 1}, {})
    results = await asyncio.gather(
        saver.append_interruption_event(thread_id="thread-stop-race", run_id="run-race", reason="user_cancel"),
        saver.append_interruption_event(thread_id="thread-stop-race", run_id="run-race", reason="client_disconnect"),
    )

    events_path = tmp_path / "checkpoints" / "thread-stop-race" / "messages.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    interruptions = [event for event in events if event.get("type") == "interruption"]

    assert len([result for result in results if result is not None]) == 1
    assert len(interruptions) == 1
    assert interruptions[0]["runId"] == "run-race"


def test_async_jsonl_checkpointer_migrates_legacy_message_snapshots(tmp_path: Path) -> None:
    thread_dir = tmp_path / "checkpoints" / "thread-legacy"
    thread_dir.mkdir(parents=True, exist_ok=True)
    legacy_entries = [
        {
            "uuid": "legacy-1",
            "parentUuid": None,
            "checkpointId": "cp-1",
            "type": "user",
            "message": {"role": "user", "content": [{"type": "text", "text": "hello"}]},
            "timestamp": "2026-04-01T00:00:00+00:00",
            "sessionId": "thread-legacy",
        },
        {
            "uuid": "legacy-2",
            "parentUuid": "legacy-1",
            "checkpointId": "cp-2",
            "type": "user",
            "message": {"role": "user", "content": [{"type": "text", "text": "hello"}]},
            "timestamp": "2026-04-01T00:00:01+00:00",
            "sessionId": "thread-legacy",
        },
        {
            "uuid": "legacy-3",
            "parentUuid": "legacy-2",
            "checkpointId": "cp-2",
            "type": "assistant",
            "message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
            "timestamp": "2026-04-01T00:00:01+00:00",
            "sessionId": "thread-legacy",
        },
    ]
    with (thread_dir / "messages.jsonl").open("w", encoding="utf-8") as f:
        for entry in legacy_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    saver = AsyncJsonlCheckpointSaver(tmp_path)
    migrated_entries = [
        json.loads(line)
        for line in (thread_dir / "messages.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert len(migrated_entries) == 2
    assert [entry["type"] for entry in migrated_entries] == ["user", "assistant"]
    assert migrated_entries[1]["parentUuid"] == migrated_entries[0]["uuid"]
    assert saver.message_log_filename == "messages.jsonl"
    assert not (thread_dir / "checkpoint_messages.jsonl").exists()


def test_async_jsonl_checkpointer_migrates_legacy_state_logs(tmp_path: Path) -> None:
    thread_dir = tmp_path / "checkpoints" / "thread-state"
    thread_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_entry = {
        "checkpoint_id": "cp-1",
        "thread_id": "thread-state",
        "checkpoint_ns": "",
        "timestamp": "2026-04-01T00:00:00+00:00",
        "parent_checkpoint_id": None,
        "checkpoint": AsyncJsonlCheckpointSaver._encode_typed(
            AsyncJsonlCheckpointSaver(tmp_path).serde.dumps_typed(empty_checkpoint())
        ),
        "metadata": AsyncJsonlCheckpointSaver._encode_typed(
            AsyncJsonlCheckpointSaver(tmp_path).serde.dumps_typed({"step": 1})
        ),
        "new_versions": {},
    }
    write_entry = {
        "thread_id": "thread-state",
        "checkpoint_ns": "",
        "checkpoint_id": "cp-1",
        "task_id": "task-1",
        "task_path": "",
        "idx": 0,
        "channel": "tasks",
        "value": AsyncJsonlCheckpointSaver._encode_typed(
            AsyncJsonlCheckpointSaver(tmp_path).serde.dumps_typed({"done": False})
        ),
    }
    with (thread_dir / "checkpoints.jsonl").open("w", encoding="utf-8") as f:
        f.write(json.dumps(checkpoint_entry, ensure_ascii=False) + "\n")
    with (thread_dir / "writes.jsonl").open("w", encoding="utf-8") as f:
        f.write(json.dumps(write_entry, ensure_ascii=False) + "\n")

    AsyncJsonlCheckpointSaver(tmp_path)

    state_entries = [
        json.loads(line)
        for line in (thread_dir / "checkpoint_state.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(state_entries) == 1
    assert state_entries[0]["pending_writes"][0]["task_id"] == "task-1"
    assert not (thread_dir / "checkpoints.jsonl").exists()
    assert not (thread_dir / "writes.jsonl").exists()
