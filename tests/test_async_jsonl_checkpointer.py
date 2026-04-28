from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.messages import HumanMessage
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
