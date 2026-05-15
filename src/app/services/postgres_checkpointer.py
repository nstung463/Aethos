"""PostgreSQL-backed LangGraph checkpoint saver with repository-backed persistence."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from collections.abc import AsyncIterator, Iterator, Sequence
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import BaseMessage
from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    ChannelVersions,
    RunnableConfig,
    get_checkpoint_id,
    get_checkpoint_metadata,
)
from sqlalchemy.orm import Session, sessionmaker

from src.app.db.models.checkpoints import ThreadCheckpointWriteModel
from src.app.repositories.checkpoint_repository import CheckpointRepository
from src.logger import get_logger

logger = get_logger(__name__)


class PostgresCheckpointSaver(BaseCheckpointSaver):
    """Persist LangGraph checkpoints and message audit history in PostgreSQL."""

    _checkpoint_visibility_retries = 10
    _checkpoint_visibility_delay_seconds = 0.02

    def __init__(self, session_factory: sessionmaker[Session]):
        super().__init__()
        self._repo = CheckpointRepository(session_factory=session_factory)
        self._interruption_locks: dict[str, asyncio.Lock] = {}

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _infer_role(msg: BaseMessage) -> str:
        class_name = msg.__class__.__name__
        if "Human" in class_name:
            return "user"
        if "AI" in class_name:
            return "assistant"
        if "System" in class_name:
            return "system"
        if "Tool" in class_name:
            return "user"
        return "user"

    @staticmethod
    def _decode_tool_args(args: Any) -> Any:
        if isinstance(args, str):
            try:
                return json.loads(args)
            except json.JSONDecodeError:
                return args
        return args

    def _serialize_tool_call(self, tc: Any) -> dict[str, Any]:
        tool_use_block: dict[str, Any] = {
            "type": "tool_use",
            "id": getattr(tc, "id", None) or str(uuid.uuid4()),
            "name": "",
            "input": {},
        }
        if hasattr(tc, "function"):
            tool_use_block["name"] = tc.function.name
            tool_use_block["input"] = self._decode_tool_args(tc.function.arguments)
        elif isinstance(tc, dict):
            tool_use_block["id"] = tc.get("id") or tool_use_block["id"]
            tool_use_block["name"] = tc.get("name") or tc.get("function", {}).get("name", "")
            args = tc.get("args", tc.get("function", {}).get("arguments", {}))
            tool_use_block["input"] = self._decode_tool_args(args)
        return tool_use_block

    def _serialize_message(self, msg: BaseMessage) -> dict[str, Any]:
        raw_content: list[dict[str, Any]] = []

        if hasattr(msg, "content") and msg.content:
            if isinstance(msg.content, str):
                raw_content.append({"type": "text", "text": msg.content})
            elif isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, dict):
                        raw_content.append(block)
                    else:
                        raw_content.append({"type": "text", "text": str(block)})

        reasoning_content = None
        if hasattr(msg, "thinking") and msg.thinking:
            reasoning_content = str(msg.thinking)

        additional_kwargs = getattr(msg, "additional_kwargs", None)
        if isinstance(additional_kwargs, dict):
            additional_reasoning = additional_kwargs.get("reasoning_content")
            if isinstance(additional_reasoning, str) and additional_reasoning.strip():
                reasoning_content = additional_reasoning

        content: list[dict[str, Any]] = []
        thinking_blocks = [block for block in raw_content if block.get("type") == "thinking"]
        if thinking_blocks:
            content.extend(thinking_blocks)
        elif reasoning_content:
            content.append({"type": "thinking", "thinking": reasoning_content})

        content.extend(block for block in raw_content if block.get("type") not in {"thinking", "tool_use"})
        content.extend(block for block in raw_content if block.get("type") == "tool_use")

        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                content.append(self._serialize_tool_call(tc))

        result = {
            "role": getattr(msg, "role", None) or self._infer_role(msg),
            "content": content or [{"type": "text", "text": ""}],
            "stop_reason": getattr(msg, "stop_reason", "end_turn"),
        }
        if isinstance(reasoning_content, str) and reasoning_content.strip():
            result["reasoning_content"] = reasoning_content
        if hasattr(msg, "response_metadata") and isinstance(msg.response_metadata, dict):
            usage = msg.response_metadata.get("usage")
            if usage:
                result["usage"] = usage
        return result

    def _serialize_event_message(self, msg: BaseMessage) -> dict[str, Any]:
        if hasattr(msg, "tool_call_id") and msg.tool_call_id:
            return {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": msg.tool_call_id, "content": msg.content}],
            }
        return self._serialize_message(msg)

    @staticmethod
    def _split_event_message(message: dict[str, Any]) -> list[dict[str, Any]]:
        content = message.get("content")
        if not isinstance(content, list) or len(content) <= 1:
            return [message]
        split_messages: list[dict[str, Any]] = []
        for block in content:
            if not isinstance(block, dict):
                block = {"type": "text", "text": str(block)}
            event_message = {"role": message.get("role"), "content": [block], "stop_reason": message.get("stop_reason", "end_turn")}
            if block.get("type") == "thinking" and message.get("reasoning_content"):
                event_message["reasoning_content"] = message["reasoning_content"]
            split_messages.append(event_message)
        return split_messages

    def _serialize_event_messages(self, msg: BaseMessage) -> list[dict[str, Any]]:
        return self._split_event_message(self._serialize_event_message(msg))

    def _message_fingerprint(self, msg: BaseMessage) -> str:
        payload = {
            "type": self._infer_role(msg),
            "message": self._serialize_event_message(msg),
            "tool_call_id": getattr(msg, "tool_call_id", None),
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _checkpoint_message_count(checkpoint: Checkpoint | dict[str, Any] | None) -> int:
        if not isinstance(checkpoint, dict):
            return 0
        channel_values = checkpoint.get("channel_values", {})
        messages = channel_values.get("messages", []) if isinstance(channel_values, dict) else []
        return len(messages) if isinstance(messages, list) else 0

    def _write_entries_from_rows(self, rows: list[ThreadCheckpointWriteModel]) -> list[tuple[str, str, Any]]:
        seen: dict[tuple[str, int], tuple[str, str, Any]] = {}
        for row in rows:
            key = (str(row.task_id), int(row.idx))
            if key in seen and key[1] >= 0:
                continue
            seen[key] = (str(row.task_id), str(row.channel), self.serde.loads_typed((str(row.value_type), bytes(row.value_payload))))
        return list(seen.values())

    def _list_checkpoint_rows(self, config: RunnableConfig | None, *, filter: dict[str, Any] | None, before: RunnableConfig | None, limit: int | None) -> list[dict[str, Any]]:
        thread_id = config["configurable"]["thread_id"] if config is not None else None
        checkpoint_ns = config["configurable"].get("checkpoint_ns") if config is not None else None
        checkpoint_id = get_checkpoint_id(config) if config is not None else None
        before_id = get_checkpoint_id(before) if before else None
        rows = self._repo.list_checkpoint_rows(thread_id, checkpoint_ns, checkpoint_id, before_id, limit)
        result: list[dict[str, Any]] = []
        for row in rows:
            metadata = self.serde.loads_typed((str(row.metadata_type), bytes(row.metadata_payload)))
            if filter and not all(metadata.get(k) == v for k, v in filter.items()):
                continue
            result.append({"id": row.id, "thread_id": row.thread_id, "checkpoint_ns": row.checkpoint_ns})
        return result

    def _append_events(self, *, thread_id: str, checkpoint_id: str, messages: list[BaseMessage]) -> None:
        if not messages:
            return
        max_seq, parent_uuid = self._repo.get_max_seq_and_parent(thread_id=thread_id)
        seq = int(max_seq)
        rows: list[dict[str, Any]] = []
        for msg in messages:
            fingerprint = self._message_fingerprint(msg)
            if self._repo.message_exists(thread_id=thread_id, fingerprint=fingerprint):
                continue
            event_messages = self._serialize_event_messages(msg)
            for index, event_message in enumerate(event_messages):
                seq += 1
                event_id = str(uuid.uuid4())
                event_fingerprint = fingerprint if len(event_messages) == 1 else f"{fingerprint}:{index}"
                rows.append(
                    {
                        "id": event_id,
                        "thread_id": thread_id,
                        "seq": seq,
                        "parent_event_id": parent_uuid,
                        "event_type": self._infer_role(msg),
                        "message_json": event_message,
                        "message_fingerprint": event_fingerprint,
                        "checkpoint_id": checkpoint_id,
                        "run_id": None,
                        "interruption_reason": None,
                        "tool_use": None,
                        "is_sidechain": False,
                        "session_id": thread_id,
                        "user_type": "external",
                        "entrypoint": "api",
                        "cwd": ".",
                    }
                )
                parent_uuid = event_id
        self._repo.append_event_rows(rows)

    async def append_interruption_event(self, *, thread_id: str, run_id: str, reason: str, tool_use: bool = False) -> dict[str, Any] | None:
        lock_key = f"{thread_id}:{run_id}"
        lock = self._interruption_locks.setdefault(lock_key, asyncio.Lock())
        async with lock:
            return await asyncio.to_thread(self._repo.append_interruption_event, thread_id=thread_id, run_id=run_id, reason=reason, tool_use=tool_use)

    async def aput(self, config: RunnableConfig, checkpoint: Checkpoint, metadata: CheckpointMetadata, new_versions: ChannelVersions) -> RunnableConfig:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = checkpoint["id"]
        parent_checkpoint_id = config["configurable"].get("checkpoint_id")

        channel_values = checkpoint.get("channel_values", {})
        messages = channel_values.get("messages", []) if isinstance(channel_values, dict) else []
        new_messages: list[BaseMessage] = []
        if isinstance(messages, list):
            base_messages = [msg for msg in messages if isinstance(msg, BaseMessage)]
            parent_checkpoint = await asyncio.to_thread(self._repo.read_checkpoint_by_id, thread_id=thread_id, checkpoint_ns=checkpoint_ns, checkpoint_id=parent_checkpoint_id)
            parent_obj = self.serde.loads_typed(parent_checkpoint) if parent_checkpoint is not None else None
            parent_count = self._checkpoint_message_count(parent_obj)
            new_messages = base_messages[parent_count:] if parent_count <= len(base_messages) else base_messages

        await asyncio.to_thread(self._append_events, thread_id=thread_id, checkpoint_id=checkpoint_id, messages=new_messages)

        checkpoint_typed = self.serde.dumps_typed(checkpoint)
        metadata_typed = self.serde.dumps_typed(get_checkpoint_metadata(config, metadata))
        await asyncio.to_thread(
            self._repo.insert_checkpoint,
            checkpoint_id=checkpoint_id,
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
            parent_checkpoint_id=parent_checkpoint_id,
            checkpoint_type=checkpoint_typed[0],
            checkpoint_payload=checkpoint_typed[1],
            metadata_type=metadata_typed[0],
            metadata_payload=metadata_typed[1],
            new_versions_json=dict(new_versions),
        )

        return {"configurable": {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns, "checkpoint_id": checkpoint_id}}

    async def _wait_for_checkpoint_visibility(self, *, thread_id: str, checkpoint_ns: str, checkpoint_id: str) -> bool:
        for attempt in range(self._checkpoint_visibility_retries):
            exists = await asyncio.to_thread(
                self._repo.checkpoint_exists,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                checkpoint_id=checkpoint_id,
            )
            if exists:
                return True
            if attempt + 1 < self._checkpoint_visibility_retries:
                await asyncio.sleep(self._checkpoint_visibility_delay_seconds)
        return False

    def put(self, config: RunnableConfig, checkpoint: Checkpoint, metadata: CheckpointMetadata, new_versions: ChannelVersions) -> RunnableConfig:
        raise NotImplementedError("Use aput() for PostgresCheckpointSaver")

    async def aput_writes(self, config: RunnableConfig, writes: Sequence[tuple[str, Any]], task_id: str, task_path: str = "") -> None:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"]["checkpoint_id"]
        checkpoint_visible = await self._wait_for_checkpoint_visibility(
            thread_id=thread_id,
            checkpoint_ns=checkpoint_ns,
            checkpoint_id=checkpoint_id,
        )
        if not checkpoint_visible:
            logger.warning(
                "Checkpoint row not visible yet; skipping checkpoint writes",
                extra={
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint_id,
                    "task_id": task_id,
                },
            )
            return
        serialized: list[dict[str, Any]] = []
        for idx, (channel, value) in enumerate(writes):
            value_typed = self.serde.dumps_typed(value)
            serialized.append(
                {
                    "thread_id": thread_id,
                    "checkpoint_id": checkpoint_id,
                    "task_id": task_id,
                    "task_path": task_path,
                    "idx": WRITES_IDX_MAP.get(channel, idx),
                    "channel": channel,
                    "value_payload": value_typed[1],
                    "value_type": value_typed[0],
                }
            )
        inserted = await asyncio.to_thread(self._repo.insert_writes, serialized)
        if not inserted:
            logger.warning(
                "Checkpoint row disappeared before checkpoint writes were committed; skipping writes",
                extra={
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint_id,
                    "task_id": task_id,
                },
            )

    def put_writes(self, config: RunnableConfig, writes: Sequence[tuple[str, Any]], task_id: str, task_path: str = "") -> None:
        raise NotImplementedError("Use aput_writes() for PostgresCheckpointSaver")

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        requested_id = get_checkpoint_id(config)
        checkpoint_row, write_rows = self._repo.get_checkpoint_with_writes(thread_id=thread_id, checkpoint_ns=checkpoint_ns, checkpoint_id=requested_id)
        if checkpoint_row is None:
            return None
        checkpoint = self.serde.loads_typed((str(checkpoint_row.checkpoint_type), bytes(checkpoint_row.checkpoint_payload)))
        metadata = self.serde.loads_typed((str(checkpoint_row.metadata_type), bytes(checkpoint_row.metadata_payload)))
        parent_config = None
        if checkpoint_row.parent_checkpoint_id:
            parent_config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns, "checkpoint_id": str(checkpoint_row.parent_checkpoint_id)}}
        return CheckpointTuple(
            config={"configurable": {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns, "checkpoint_id": checkpoint_row.id}},
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=parent_config,
            pending_writes=self._write_entries_from_rows(write_rows),
        )

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return await asyncio.to_thread(self.get_tuple, config)

    def list(self, config: RunnableConfig | None, *, filter: dict[str, Any] | None = None, before: RunnableConfig | None = None, limit: int | None = None) -> Iterator[CheckpointTuple]:
        rows = self._list_checkpoint_rows(config, filter=filter, before=before, limit=limit)
        for row in rows:
            tuple_value = self.get_tuple({"configurable": {"thread_id": str(row["thread_id"]), "checkpoint_ns": str(row["checkpoint_ns"]), "checkpoint_id": str(row["id"])}})
            if tuple_value is not None:
                yield tuple_value

    async def alist(self, config: RunnableConfig | None, *, filter: dict[str, Any] | None = None, before: RunnableConfig | None = None, limit: int | None = None) -> AsyncIterator[CheckpointTuple]:
        for item in await asyncio.to_thread(lambda: list(self.list(config, filter=filter, before=before, limit=limit))):
            yield item

    async def get_full_message_entries(self, config: RunnableConfig) -> list[dict[str, Any]]:
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        return await asyncio.to_thread(self._repo.get_full_message_entries, thread_id=thread_id)

    async def get_request_messages_only(self, config: RunnableConfig) -> list[dict[str, Any]]:
        tracker_info = config.get("configurable", {}).get("message_request_tracker")
        if not tracker_info:
            return await self.get_full_message_entries(config)
        marked_indices = set(tracker_info.get("current_request_message_indices", []))
        entries = await self.get_full_message_entries(config)
        return [msg for idx, msg in enumerate(entries) if idx in marked_indices]

