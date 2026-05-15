from __future__ import annotations

import asyncio
from unittest.mock import Mock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.base import empty_checkpoint
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from src.app.repositories.checkpoint_repository import CheckpointRepository
from src.app.services.postgres_checkpointer import PostgresCheckpointSaver


@pytest.fixture()
def postgres_checkpointer():
    pytest.importorskip("psycopg")
    database_url = __import__("os").environ.get("AETHOS_TEST_DATABASE_URL", "").strip()
    if not database_url:
        pytest.skip("AETHOS_TEST_DATABASE_URL is not configured for PostgreSQL checkpoint testing")

    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
    except OperationalError:
        pytest.skip("Configured PostgreSQL test database is not available")

    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS thread_checkpoint_writes")
        conn.exec_driver_sql("DROP TABLE IF EXISTS thread_checkpoints")
        conn.exec_driver_sql("DROP TABLE IF EXISTS thread_events")
        conn.exec_driver_sql("DROP TABLE IF EXISTS thread_permissions")
        conn.exec_driver_sql("DROP TABLE IF EXISTS threads")
        conn.exec_driver_sql("DROP TABLE IF EXISTS projects")
        conn.exec_driver_sql(
            """
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                project_key TEXT NOT NULL UNIQUE,
                canonical_root TEXT NOT NULL,
                original_root TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE threads (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                project_id TEXT NULL REFERENCES projects(id) ON DELETE SET NULL,
                workspace_root TEXT NULL,
                canonical_root TEXT NULL,
                backend TEXT NULL,
                status TEXT NOT NULL DEFAULT 'idle',
                title TEXT NULL,
                summary TEXT NULL,
                model TEXT NULL,
                mode TEXT NULL,
                profile_id TEXT NULL,
                project_label TEXT NULL,
                is_favorite BOOLEAN NOT NULL DEFAULT FALSE,
                active_run_id TEXT NULL,
                run_started_at TIMESTAMPTZ NULL,
                last_stop_run_id TEXT NULL,
                last_stop_reason TEXT NULL,
                last_interrupted_at TIMESTAMPTZ NULL,
                last_message_at TIMESTAMPTZ NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE thread_permissions (
                thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL,
                overlay_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (thread_id, user_id)
            )
            """
        )
        conn.exec_driver_sql("INSERT INTO threads (id, user_id) VALUES ('thread-1', 'user-1')")
        conn.exec_driver_sql("INSERT INTO threads (id, user_id) VALUES ('thread-2', 'user-1')")
        conn.exec_driver_sql("INSERT INTO threads (id, user_id) VALUES ('thread-3', 'user-1')")
        conn.exec_driver_sql("INSERT INTO threads (id, user_id) VALUES ('thread-4', 'user-1')")
        conn.exec_driver_sql("INSERT INTO threads (id, user_id) VALUES ('thread-stop', 'user-1')")
        conn.exec_driver_sql("INSERT INTO threads (id, user_id) VALUES ('thread-stop-race', 'user-1')")
        conn.exec_driver_sql("INSERT INTO threads (id, user_id) VALUES ('thread-reasoning', 'user-1')")
        conn.exec_driver_sql("INSERT INTO threads (id, user_id) VALUES ('thread-reasoning-tool', 'user-1')")
        conn.exec_driver_sql("INSERT INTO threads (id, user_id) VALUES ('thread-reasoning-text-tool', 'user-1')")
        conn.exec_driver_sql(
            """
            CREATE TABLE thread_events (
                id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
                seq BIGINT NOT NULL,
                parent_event_id TEXT NULL REFERENCES thread_events(id) ON DELETE SET NULL,
                event_type TEXT NOT NULL,
                message_json JSONB NOT NULL,
                message_fingerprint TEXT NOT NULL,
                checkpoint_id TEXT NULL,
                run_id TEXT NULL,
                interruption_reason TEXT NULL,
                tool_use BOOLEAN NULL,
                is_sidechain BOOLEAN NOT NULL DEFAULT FALSE,
                session_id TEXT NULL,
                user_type TEXT NULL,
                entrypoint TEXT NULL,
                cwd TEXT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_thread_event_fingerprint UNIQUE (thread_id, message_fingerprint)
            )
            """
        )
        conn.exec_driver_sql("CREATE INDEX ix_thread_events_thread_seq ON thread_events(thread_id, seq)")
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX uq_thread_interruption_event ON thread_events(thread_id, run_id, event_type) WHERE event_type = 'interruption'"
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE thread_checkpoints (
                id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
                checkpoint_ns TEXT NOT NULL DEFAULT '',
                parent_checkpoint_id TEXT NULL,
                checkpoint_payload BYTEA NOT NULL,
                checkpoint_type TEXT NOT NULL,
                metadata_payload BYTEA NOT NULL,
                metadata_type TEXT NOT NULL,
                new_versions_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.exec_driver_sql(
            "CREATE INDEX ix_thread_checkpoints_thread_ns_created ON thread_checkpoints(thread_id, checkpoint_ns, created_at)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX ix_thread_checkpoints_thread_ns_id ON thread_checkpoints(thread_id, checkpoint_ns, id)"
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE thread_checkpoint_writes (
                thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
                checkpoint_id TEXT NOT NULL REFERENCES thread_checkpoints(id) ON DELETE CASCADE,
                task_id TEXT NOT NULL,
                task_path TEXT NOT NULL DEFAULT '',
                idx INTEGER NOT NULL,
                channel TEXT NOT NULL,
                value_payload BYTEA NOT NULL,
                value_type TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (checkpoint_id, task_id, idx)
            )
            """
        )
        conn.exec_driver_sql(
            "CREATE INDEX ix_thread_checkpoint_writes_thread_checkpoint ON thread_checkpoint_writes(thread_id, checkpoint_id)"
        )

    return PostgresCheckpointSaver(engine)


def test_postgres_checkpointer_round_trips_checkpoint_and_writes(postgres_checkpointer: PostgresCheckpointSaver) -> None:
    saver = postgres_checkpointer
    config = {"configurable": {"thread_id": "thread-1", "checkpoint_ns": ""}}
    checkpoint = empty_checkpoint()
    checkpoint["id"] = "cp-1"
    checkpoint["channel_values"] = {"messages": [HumanMessage(content="hello")]}
    metadata = {"source": "input", "step": 1}

    saved_config = asyncio.run(saver.aput(config, checkpoint, metadata, {}))
    asyncio.run(saver.aput_writes(saved_config, [("tasks", {"done": False}), ("custom", "value")], task_id="task-1"))

    restored = asyncio.run(saver.aget_tuple(saved_config))
    assert restored is not None
    assert restored.config["configurable"]["checkpoint_id"] == "cp-1"
    assert restored.checkpoint["id"] == "cp-1"
    assert restored.metadata["source"] == "input"
    assert restored.metadata["step"] == 1
    assert restored.pending_writes == [("task-1", "tasks", {"done": False}), ("task-1", "custom", "value")]

    message_entries = asyncio.run(saver.get_full_message_entries(config))
    assert len(message_entries) == 1
    assert message_entries[0]["checkpointId"] == "cp-1"
    assert message_entries[0]["type"] == "user"
    assert message_entries[0]["message"]["content"][0]["text"] == "hello"


def test_postgres_checkpointer_immediately_returns_latest_checkpoint_with_interrupt_write(
    postgres_checkpointer: PostgresCheckpointSaver,
) -> None:
    saver = postgres_checkpointer
    config = {"configurable": {"thread_id": "thread-1", "checkpoint_ns": ""}}
    checkpoint = empty_checkpoint()
    checkpoint["id"] = "cp-1"
    checkpoint["channel_values"] = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[{"id": "call-shell", "name": "powershell", "args": {"command": "python -c \"print(1)\""}}],
            )
        ]
    }

    saved_config = asyncio.run(saver.aput(config, checkpoint, {"step": 1}, {}))
    asyncio.run(
        saver.aput_writes(
            saved_config,
            [
                (
                    "__interrupt__",
                    {
                        "behavior": "ask",
                        "reason": "powershell command classified as code_execution",
                        "subject": "powershell",
                        "command": "python -c \"print(1)\"",
                    },
                )
            ],
            task_id="task-1",
        )
    )

    restored = asyncio.run(saver.aget_tuple({"configurable": {"thread_id": "thread-1"}}))

    assert restored is not None
    assert restored.config["configurable"]["checkpoint_id"] == "cp-1"
    assert restored.checkpoint["id"] == "cp-1"
    assert restored.pending_writes == [
        (
            "task-1",
            "__interrupt__",
            {
                "behavior": "ask",
                "reason": "powershell command classified as code_execution",
                "subject": "powershell",
                "command": "python -c \"print(1)\"",
            },
        )
    ]


def test_postgres_checkpointer_waits_for_checkpoint_visibility_before_writing() -> None:
    saver = PostgresCheckpointSaver(session_factory=Mock())
    config = {"configurable": {"thread_id": "thread-1", "checkpoint_ns": "", "checkpoint_id": "cp-1"}}

    with (
        patch.object(CheckpointRepository, "checkpoint_exists", Mock(side_effect=[False, False, True])) as checkpoint_exists,
        patch.object(CheckpointRepository, "insert_writes", Mock()) as insert_writes,
    ):
        asyncio.run(saver.aput_writes(config, [("tasks", {"done": False})], task_id="task-1"))

    assert checkpoint_exists.call_count == 3
    insert_writes.assert_called_once()


def test_postgres_checkpointer_skips_writes_when_checkpoint_never_becomes_visible() -> None:
    saver = PostgresCheckpointSaver(session_factory=Mock())
    config = {"configurable": {"thread_id": "thread-1", "checkpoint_ns": "", "checkpoint_id": "cp-missing"}}

    with (
        patch.object(CheckpointRepository, "checkpoint_exists", Mock(return_value=False)) as checkpoint_exists,
        patch.object(CheckpointRepository, "insert_writes", Mock()) as insert_writes,
    ):
        asyncio.run(saver.aput_writes(config, [("tasks", {"done": False})], task_id="task-1"))

    assert checkpoint_exists.call_count == saver._checkpoint_visibility_retries
    insert_writes.assert_not_called()


def test_postgres_checkpointer_handles_insert_race_when_checkpoint_disappears() -> None:
    saver = PostgresCheckpointSaver(session_factory=Mock())
    config = {"configurable": {"thread_id": "thread-1", "checkpoint_ns": "", "checkpoint_id": "cp-race"}}

    with (
        patch.object(CheckpointRepository, "checkpoint_exists", Mock(return_value=True)) as checkpoint_exists,
        patch.object(CheckpointRepository, "insert_writes", Mock(return_value=False)) as insert_writes,
    ):
        asyncio.run(saver.aput_writes(config, [("tasks", {"done": False})], task_id="task-1"))

    checkpoint_exists.assert_called_once()
    insert_writes.assert_called_once()


def test_postgres_checkpointer_returns_latest_checkpoint_when_id_not_specified(postgres_checkpointer: PostgresCheckpointSaver) -> None:
    saver = postgres_checkpointer
    config = {"configurable": {"thread_id": "thread-2", "checkpoint_ns": ""}}

    first = empty_checkpoint()
    first["id"] = "cp-1"
    first["channel_values"] = {"messages": [HumanMessage(content="first")]}
    second = empty_checkpoint()
    second["id"] = "cp-2"
    second["channel_values"] = {"messages": [HumanMessage(content="second")]}

    first_config = asyncio.run(saver.aput(config, first, {"step": 1}, {}))
    second_config = asyncio.run(saver.aput(first_config, second, {"step": 2}, {}))

    latest = asyncio.run(saver.aget_tuple(config))
    assert latest is not None
    assert latest.config["configurable"]["checkpoint_id"] == "cp-2"
    assert latest.parent_config == {
        "configurable": {"thread_id": "thread-2", "checkpoint_ns": "", "checkpoint_id": "cp-1"}
    }

    async def _collect() -> list:
        return [item async for item in saver.alist(config, limit=2)]

    listed = asyncio.run(_collect())
    assert [item.config["configurable"]["checkpoint_id"] for item in listed] == ["cp-2", "cp-1"]
    assert second_config["configurable"]["checkpoint_id"] == "cp-2"


def test_postgres_checkpointer_writes_events_without_replayed_messages(postgres_checkpointer: PostgresCheckpointSaver) -> None:
    saver = postgres_checkpointer
    config = {"configurable": {"thread_id": "thread-3", "checkpoint_ns": ""}}

    user_message = HumanMessage(content="hello")
    assistant_message = AIMessage(content="hi there")

    first = empty_checkpoint()
    first["id"] = "cp-1"
    first["channel_values"] = {"messages": [user_message]}
    second = empty_checkpoint()
    second["id"] = "cp-2"
    second["channel_values"] = {"messages": [user_message, assistant_message]}

    first_config = asyncio.run(saver.aput(config, first, {"step": 1}, {}))
    asyncio.run(saver.aput(first_config, second, {"step": 2}, {}))

    events = asyncio.run(saver.get_full_message_entries(config))
    assert len(events) == 2
    assert [event["type"] for event in events] == ["user", "assistant"]
    assert events[0]["message"]["content"][0]["text"] == "hello"
    assert events[1]["message"]["content"][0]["text"] == "hi there"
    assert events[1]["parentUuid"] == events[0]["uuid"]


def test_postgres_checkpointer_serializes_reasoning_content(postgres_checkpointer: PostgresCheckpointSaver) -> None:
    saver = postgres_checkpointer
    config = {"configurable": {"thread_id": "thread-reasoning", "checkpoint_ns": ""}}
    checkpoint = empty_checkpoint()
    checkpoint["id"] = "cp-1"
    checkpoint["channel_values"] = {
        "messages": [
            AIMessage(content="Using a tool.", additional_kwargs={"reasoning_content": "Need to inspect the workbook first."})
        ]
    }

    asyncio.run(saver.aput(config, checkpoint, {"step": 1}, {}))
    events = asyncio.run(saver.get_full_message_entries(config))

    assert len(events) == 2
    thinking_message = events[0]["message"]
    text_message = events[1]["message"]
    assert thinking_message["reasoning_content"] == "Need to inspect the workbook first."
    assert thinking_message["content"] == [{"type": "thinking", "thinking": "Need to inspect the workbook first."}]
    assert text_message["content"] == [{"type": "text", "text": "Using a tool."}]
    assert events[1]["parentUuid"] == events[0]["uuid"]


def test_postgres_checkpointer_serializes_reasoning_before_tool_calls(postgres_checkpointer: PostgresCheckpointSaver) -> None:
    saver = postgres_checkpointer
    config = {"configurable": {"thread_id": "thread-reasoning-tool", "checkpoint_ns": ""}}
    checkpoint = empty_checkpoint()
    checkpoint["id"] = "cp-1"
    checkpoint["channel_values"] = {
        "messages": [
            AIMessage(
                content="",
                additional_kwargs={"reasoning_content": "Need to inspect the project first."},
                tool_calls=[{"id": "call-1", "name": "list_files", "args": {"path": "."}}],
            )
        ]
    }

    asyncio.run(saver.aput(config, checkpoint, {"step": 1}, {}))
    events = asyncio.run(saver.get_full_message_entries(config))

    assert len(events) == 2
    assert events[0]["message"]["content"] == [{"type": "thinking", "thinking": "Need to inspect the project first."}]
    assert events[1]["message"]["content"][0]["type"] == "tool_use"
    assert events[1]["message"]["content"][0]["name"] == "list_files"
    assert events[1]["parentUuid"] == events[0]["uuid"]


def test_postgres_checkpointer_splits_thinking_text_and_tool_rows(postgres_checkpointer: PostgresCheckpointSaver) -> None:
    saver = postgres_checkpointer
    config = {"configurable": {"thread_id": "thread-reasoning-text-tool", "checkpoint_ns": ""}}
    checkpoint = empty_checkpoint()
    checkpoint["id"] = "cp-1"
    checkpoint["channel_values"] = {
        "messages": [
            AIMessage(
                content="I will inspect the project.",
                additional_kwargs={"reasoning_content": "Need to inspect before writing."},
                tool_calls=[{"id": "call-1", "name": "list_files", "args": {"path": "."}}],
            )
        ]
    }

    asyncio.run(saver.aput(config, checkpoint, {"step": 1}, {}))
    events = asyncio.run(saver.get_full_message_entries(config))

    assert [event["message"]["content"][0]["type"] for event in events] == ["thinking", "text", "tool_use"]
    assert events[1]["parentUuid"] == events[0]["uuid"]
    assert events[2]["parentUuid"] == events[1]["uuid"]


def test_postgres_checkpointer_serializes_tool_calls_and_results_in_events(postgres_checkpointer: PostgresCheckpointSaver) -> None:
    saver = postgres_checkpointer
    config = {"configurable": {"thread_id": "thread-4", "checkpoint_ns": ""}}
    checkpoint = empty_checkpoint()
    checkpoint["id"] = "cp-1"
    checkpoint["channel_values"] = {
        "messages": [
            AIMessage(content="", tool_calls=[{"id": "call-1", "name": "list_files", "args": {"path": "."}}]),
            ToolMessage(content="README.md", tool_call_id="call-1"),
        ]
    }

    asyncio.run(saver.aput(config, checkpoint, {"step": 1}, {}))
    events = asyncio.run(saver.get_full_message_entries(config))

    tool_use = events[0]["message"]["content"][0]
    tool_result = events[1]["message"]["content"][0]
    assert tool_use == {"type": "tool_use", "id": "call-1", "name": "list_files", "input": {"path": "."}}
    assert tool_result == {"type": "tool_result", "tool_use_id": "call-1", "content": "README.md"}


def test_postgres_checkpointer_appends_interruption_once(postgres_checkpointer: PostgresCheckpointSaver) -> None:
    saver = postgres_checkpointer
    config = {"configurable": {"thread_id": "thread-stop", "checkpoint_ns": ""}}
    checkpoint = empty_checkpoint()
    checkpoint["id"] = "cp-1"
    checkpoint["channel_values"] = {"messages": [HumanMessage(content="start")]}

    asyncio.run(saver.aput(config, checkpoint, {"step": 1}, {}))
    first = asyncio.run(saver.append_interruption_event(thread_id="thread-stop", run_id="run-1", reason="user_cancel"))
    second = asyncio.run(saver.append_interruption_event(thread_id="thread-stop", run_id="run-1", reason="user_cancel"))

    events = asyncio.run(saver.get_full_message_entries(config))
    assert first is not None
    assert second is None
    assert len(events) == 2
    assert events[1]["type"] == "interruption"
    assert events[1]["message"]["content"][0]["text"] == "[Request interrupted by user]"
    assert events[1]["runId"] == "run-1"
    assert events[1]["interruptionReason"] == "user_cancel"
    assert events[1]["parentUuid"] == events[0]["uuid"]


def test_postgres_checkpointer_concurrent_interruption_append_is_idempotent(postgres_checkpointer: PostgresCheckpointSaver) -> None:
    saver = postgres_checkpointer
    config = {"configurable": {"thread_id": "thread-stop-race", "checkpoint_ns": ""}}
    checkpoint = empty_checkpoint()
    checkpoint["id"] = "cp-1"
    checkpoint["channel_values"] = {"messages": [HumanMessage(content="start")]}

    asyncio.run(saver.aput(config, checkpoint, {"step": 1}, {}))

    async def _run() -> list:
        return await asyncio.gather(
            saver.append_interruption_event(thread_id="thread-stop-race", run_id="run-race", reason="user_cancel"),
            saver.append_interruption_event(thread_id="thread-stop-race", run_id="run-race", reason="client_disconnect"),
        )

    results = asyncio.run(_run())

    events = asyncio.run(saver.get_full_message_entries(config))
    interruptions = [event for event in events if event.get("type") == "interruption"]
    assert len([result for result in results if result is not None]) == 1
    assert len(interruptions) == 1
    assert interruptions[0]["runId"] == "run-race"

