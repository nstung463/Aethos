"""Async JSONL checkpoint saver with Claude-style message audit history."""

from __future__ import annotations

import base64
import json
import uuid
from collections.abc import AsyncIterator, Iterator, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiofiles
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

from src.logger import get_logger

logger = get_logger(__name__)


class AsyncJsonlCheckpointSaver(BaseCheckpointSaver):
    """Persist LangGraph checkpoints and Claude-style message history as JSONL."""

    def __init__(self, base_dir: str | Path):
        super().__init__()
        self.base_dir = Path(base_dir).resolve()
        self.checkpoints_dir = self.base_dir / "checkpoints"
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        self._last_message_uuid: dict[str, str] = {}

    def _thread_dir(self, thread_id: str) -> Path:
        thread_dir = self.checkpoints_dir / thread_id
        thread_dir.mkdir(parents=True, exist_ok=True)
        return thread_dir

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _encode_typed(value: tuple[str, bytes]) -> dict[str, str]:
        type_name, payload = value
        return {
            "type": type_name,
            "data": base64.b64encode(payload).decode("ascii"),
        }

    @staticmethod
    def _decode_typed(data: dict[str, Any]) -> tuple[str, bytes]:
        return (
            str(data["type"]),
            base64.b64decode(str(data["data"]).encode("ascii")),
        )

    def _serialize_message(self, msg: BaseMessage) -> dict[str, Any]:
        content: list[dict[str, Any]] = []

        if hasattr(msg, "content") and msg.content:
            if isinstance(msg.content, str):
                content.append({"type": "text", "text": msg.content})
            elif isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, dict):
                        content.append(block)
                    else:
                        content.append({"type": "text", "text": str(block)})

        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_use_block: dict[str, Any] = {
                    "type": "tool_use",
                    "id": getattr(tc, "id", str(uuid.uuid4())),
                }
                if hasattr(tc, "function"):
                    tool_use_block["name"] = tc.function.name
                    tool_use_block["input"] = (
                        json.loads(tc.function.arguments)
                        if isinstance(tc.function.arguments, str)
                        else tc.function.arguments
                    )
                elif isinstance(tc, dict):
                    tool_use_block["name"] = tc.get("function", {}).get("name", "")
                    args = tc.get("function", {}).get("arguments", {})
                    tool_use_block["input"] = json.loads(args) if isinstance(args, str) else args
                content.append(tool_use_block)

        if hasattr(msg, "thinking") and msg.thinking:
            content.append({"type": "thinking", "thinking": msg.thinking})

        result = {
            "role": getattr(msg, "role", None) or self._infer_role(msg),
            "content": content or [{"type": "text", "text": ""}],
            "stop_reason": getattr(msg, "stop_reason", "end_turn"),
        }
        if hasattr(msg, "response_metadata") and isinstance(msg.response_metadata, dict):
            usage = msg.response_metadata.get("usage")
            if usage:
                result["usage"] = usage
        return result

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

    async def _append_messages_claude_format(
        self,
        *,
        thread_dir: Path,
        thread_id: str,
        checkpoint_id: str,
        messages: list[BaseMessage],
    ) -> None:
        if not messages:
            return
        messages_file = thread_dir / "messages.jsonl"
        entries: list[str] = []
        for msg in messages:
            message_uuid = str(uuid.uuid4())
            parent_uuid = self._last_message_uuid.get(thread_id)
            entry = {
                "uuid": message_uuid,
                "parentUuid": parent_uuid,
                "checkpointId": checkpoint_id,
                "type": self._infer_role(msg),
                "message": self._serialize_message(msg),
                "timestamp": self._now_iso(),
                "sessionId": thread_id,
            }
            self._last_message_uuid[thread_id] = message_uuid
            entries.append(json.dumps(entry, ensure_ascii=False))

        async with aiofiles.open(messages_file, "a", encoding="utf-8") as f:
            for entry in entries:
                await f.write(entry + "\n")

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = checkpoint["id"]
        thread_dir = self._thread_dir(thread_id)

        channel_values = checkpoint.get("channel_values", {})
        messages = channel_values.get("messages", []) if isinstance(channel_values, dict) else []
        if isinstance(messages, list):
            base_messages = [msg for msg in messages if isinstance(msg, BaseMessage)]
            await self._append_messages_claude_format(
                thread_dir=thread_dir,
                thread_id=thread_id,
                checkpoint_id=checkpoint_id,
                messages=base_messages,
            )

        entry = {
            "checkpoint_id": checkpoint_id,
            "thread_id": thread_id,
            "checkpoint_ns": checkpoint_ns,
            "timestamp": self._now_iso(),
            "parent_checkpoint_id": config["configurable"].get("checkpoint_id"),
            "checkpoint": self._encode_typed(self.serde.dumps_typed(checkpoint)),
            "metadata": self._encode_typed(
                self.serde.dumps_typed(get_checkpoint_metadata(config, metadata))
            ),
            "new_versions": new_versions,
        }

        async with aiofiles.open(thread_dir / "checkpoints.jsonl", "a", encoding="utf-8") as f:
            await f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        raise NotImplementedError("Use aput() for AsyncJsonlCheckpointSaver")

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"]["checkpoint_id"]
        thread_dir = self._thread_dir(thread_id)

        entries = []
        for idx, (channel, value) in enumerate(writes):
            entries.append(
                {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint_id,
                    "task_id": task_id,
                    "task_path": task_path,
                    "idx": WRITES_IDX_MAP.get(channel, idx),
                    "channel": channel,
                    "value": self._encode_typed(self.serde.dumps_typed(value)),
                }
            )

        async with aiofiles.open(thread_dir / "writes.jsonl", "a", encoding="utf-8") as f:
            for entry in entries:
                await f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        raise NotImplementedError("Use aput_writes() for AsyncJsonlCheckpointSaver")

    def _read_checkpoint_entries(self, thread_dir: Path) -> list[dict[str, Any]]:
        path = thread_dir / "checkpoints.jsonl"
        if not path.exists():
            return []
        entries: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    parsed = json.loads(line)
                    if isinstance(parsed, dict):
                        entries.append(parsed)
                except json.JSONDecodeError:
                    logger.warning("Failed to parse checkpoint entry")
        return entries

    def _read_write_entries(
        self,
        *,
        thread_dir: Path,
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_id: str,
    ) -> list[tuple[str, str, Any]]:
        path = thread_dir / "writes.jsonl"
        if not path.exists():
            return []
        seen: dict[tuple[str, int], tuple[str, str, Any]] = {}
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(entry, dict):
                    continue
                if (
                    entry.get("thread_id") != thread_id
                    or entry.get("checkpoint_ns", "") != checkpoint_ns
                    or entry.get("checkpoint_id") != checkpoint_id
                ):
                    continue
                key = (str(entry.get("task_id", "")), int(entry.get("idx", 0)))
                if key in seen and key[1] >= 0:
                    continue
                seen[key] = (
                    str(entry.get("task_id", "")),
                    str(entry.get("channel", "")),
                    self.serde.loads_typed(self._decode_typed(entry["value"])),
                )
        return list(seen.values())

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        thread_dir = self._thread_dir(thread_id)
        entries = self._read_checkpoint_entries(thread_dir)
        if not entries:
            return None

        requested_id = get_checkpoint_id(config)
        selected: dict[str, Any] | None = None
        for entry in reversed(entries):
            if entry.get("checkpoint_ns", "") != checkpoint_ns:
                continue
            checkpoint_id = entry.get("checkpoint_id")
            if requested_id is not None and checkpoint_id != requested_id:
                continue
            selected = entry
            break
        if selected is None:
            return None

        checkpoint_id = str(selected["checkpoint_id"])
        checkpoint = self.serde.loads_typed(self._decode_typed(selected["checkpoint"]))
        metadata = self.serde.loads_typed(self._decode_typed(selected["metadata"]))
        parent_checkpoint_id = selected.get("parent_checkpoint_id")
        parent_config = None
        if parent_checkpoint_id:
            parent_config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": parent_checkpoint_id,
                }
            }

        return CheckpointTuple(
            config={
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint_id,
                }
            },
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=parent_config,
            pending_writes=self._read_write_entries(
                thread_dir=thread_dir,
                thread_id=thread_id,
                checkpoint_ns=checkpoint_ns,
                checkpoint_id=checkpoint_id,
            ),
        )

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return self.get_tuple(config)

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        thread_ids: list[str]
        if config is None:
            thread_ids = [p.name for p in self.checkpoints_dir.iterdir() if p.is_dir()]
        else:
            thread_ids = [config["configurable"]["thread_id"]]

        remaining = limit
        before_id = get_checkpoint_id(before) if before else None
        config_checkpoint_ns = config["configurable"].get("checkpoint_ns") if config else None
        config_checkpoint_id = get_checkpoint_id(config) if config else None

        for thread_id in thread_ids:
            thread_dir = self._thread_dir(thread_id)
            entries = list(reversed(self._read_checkpoint_entries(thread_dir)))
            for entry in entries:
                checkpoint_ns = str(entry.get("checkpoint_ns", ""))
                checkpoint_id = str(entry.get("checkpoint_id", ""))
                if config_checkpoint_ns is not None and checkpoint_ns != config_checkpoint_ns:
                    continue
                if config_checkpoint_id is not None and checkpoint_id != config_checkpoint_id:
                    continue
                if before_id is not None and checkpoint_id >= before_id:
                    continue

                metadata = self.serde.loads_typed(self._decode_typed(entry["metadata"]))
                if filter and not all(metadata.get(k) == v for k, v in filter.items()):
                    continue

                tuple_value = self.get_tuple(
                    {
                        "configurable": {
                            "thread_id": thread_id,
                            "checkpoint_ns": checkpoint_ns,
                            "checkpoint_id": checkpoint_id,
                        }
                    }
                )
                if tuple_value is None:
                    continue
                yield tuple_value
                if remaining is not None:
                    remaining -= 1
                    if remaining <= 0:
                        return

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        for item in self.list(config, filter=filter, before=before, limit=limit):
            yield item

    async def get_full_message_entries(self, config: RunnableConfig) -> list[dict[str, Any]]:
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        thread_dir = self._thread_dir(thread_id)
        messages_file = thread_dir / "messages.jsonl"
        if not messages_file.exists():
            return []

        entries: list[dict[str, Any]] = []
        async with aiofiles.open(messages_file, "r", encoding="utf-8") as f:
            async for line in f:
                try:
                    parsed = json.loads(line)
                    if isinstance(parsed, dict):
                        entries.append(parsed)
                except json.JSONDecodeError:
                    logger.warning("Failed to parse message entry")
        return entries

    async def get_request_messages_only(self, config: RunnableConfig) -> list[dict[str, Any]]:
        tracker_info = config.get("configurable", {}).get("message_request_tracker")
        if not tracker_info:
            return await self.get_full_message_entries(config)

        marked_indices = set(tracker_info.get("current_request_message_indices", []))
        entries = await self.get_full_message_entries(config)
        return [msg for idx, msg in enumerate(entries) if idx in marked_indices]
