"""Async JSONL checkpoint saver with Claude-style message audit history."""

from __future__ import annotations

import base64
import hashlib
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

    message_log_filename = "messages.jsonl"
    state_log_filename = "checkpoint_state.jsonl"
    legacy_snapshot_log_filenames = ("checkpoint_messages.jsonl", "events.jsonl")
    legacy_state_log_filenames = ("checkpoints.jsonl", "writes.jsonl")

    def __init__(self, base_dir: str | Path):
        super().__init__()
        self.base_dir = Path(base_dir).resolve()
        self.checkpoints_dir = self.base_dir / "checkpoints"
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        self._last_event_message_uuid: dict[str, str] = {}
        self._migrate_existing_logs()

    def _thread_dir(self, thread_id: str) -> Path:
        thread_dir = self.checkpoints_dir / thread_id
        thread_dir.mkdir(parents=True, exist_ok=True)
        return thread_dir

    @classmethod
    def _message_log_path(cls, thread_dir: Path) -> Path:
        return thread_dir / cls.message_log_filename

    @classmethod
    def _state_log_path(cls, thread_dir: Path) -> Path:
        return thread_dir / cls.state_log_filename

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
                content.append(self._serialize_tool_call(tc))

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

    @staticmethod
    def _decode_tool_args(args: Any) -> Any:
        if isinstance(args, str):
            try:
                return json.loads(args)
            except json.JSONDecodeError:
                return args
        return args

    def _serialize_event_message(self, msg: BaseMessage) -> dict[str, Any]:
        if hasattr(msg, "tool_call_id") and msg.tool_call_id:
            return {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content,
                    }
                ],
            }
        return self._serialize_message(msg)

    @staticmethod
    def _read_jsonl_entries(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        entries: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    entries.append(parsed)
        return entries

    @staticmethod
    def _write_jsonl_entries(path: Path, entries: list[dict[str, Any]]) -> None:
        if not entries:
            return
        with path.open("w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    @staticmethod
    def _looks_like_event_entry(entry: dict[str, Any]) -> bool:
        return "isSidechain" in entry or "messageFingerprint" in entry or entry.get("type") in {
            "attachment",
            "file-history-snapshot",
            "last-prompt",
        }

    @classmethod
    def _looks_like_event_log(cls, entries: list[dict[str, Any]]) -> bool:
        return any(cls._looks_like_event_entry(entry) for entry in entries)

    @staticmethod
    def _legacy_entry_fingerprint(entry: dict[str, Any]) -> str:
        payload = {
            "type": entry.get("type"),
            "message": entry.get("message"),
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _event_fingerprint_from_entry(self, entry: dict[str, Any]) -> str:
        payload = {
            "type": entry.get("type"),
            "message": entry.get("message"),
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _build_event_entry_from_legacy(
        self,
        *,
        legacy_entry: dict[str, Any],
        parent_uuid: str | None,
        fingerprint: str,
    ) -> dict[str, Any]:
        return {
            "parentUuid": parent_uuid,
            "isSidechain": False,
            "type": legacy_entry.get("type", "user"),
            "message": legacy_entry.get("message", {}),
            "uuid": str(legacy_entry.get("uuid") or uuid.uuid4()),
            "timestamp": legacy_entry.get("timestamp", self._now_iso()),
            "sessionId": legacy_entry.get("sessionId"),
            "checkpointId": legacy_entry.get("checkpointId"),
            "messageFingerprint": fingerprint,
            "userType": "external",
            "entrypoint": "api",
            "cwd": str(Path.cwd()),
        }

    def _convert_legacy_snapshot_entries_to_event_entries(
        self,
        legacy_entries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not legacy_entries:
            return []
        checkpoint_groups: list[tuple[str, list[dict[str, Any]]]] = []
        current_checkpoint_id: str | None = None
        current_group: list[dict[str, Any]] = []

        for entry in legacy_entries:
            checkpoint_id = str(entry.get("checkpointId") or "")
            if current_checkpoint_id is None or checkpoint_id != current_checkpoint_id:
                if current_group:
                    checkpoint_groups.append((current_checkpoint_id or "", current_group))
                current_checkpoint_id = checkpoint_id
                current_group = [entry]
            else:
                current_group.append(entry)
        if current_group:
            checkpoint_groups.append((current_checkpoint_id or "", current_group))

        event_entries: list[dict[str, Any]] = []
        previous_fingerprints: list[str] = []
        parent_uuid: str | None = None

        for _, group in checkpoint_groups:
            fingerprints = [self._legacy_entry_fingerprint(entry) for entry in group]
            common_prefix = 0
            for left, right in zip(previous_fingerprints, fingerprints):
                if left != right:
                    break
                common_prefix += 1
            for legacy_entry, fingerprint in zip(group[common_prefix:], fingerprints[common_prefix:]):
                event_entry = self._build_event_entry_from_legacy(
                    legacy_entry=legacy_entry,
                    parent_uuid=parent_uuid,
                    fingerprint=fingerprint,
                )
                parent_uuid = event_entry["uuid"]
                event_entries.append(event_entry)
            previous_fingerprints = fingerprints

        return event_entries

    def _merge_event_entries(self, *entry_lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        parent_uuid: str | None = None

        for entries in entry_lists:
            for entry in entries:
                fingerprint = self._event_fingerprint_from_entry(entry)
                if fingerprint in seen:
                    continue
                normalized = dict(entry)
                normalized["uuid"] = str(normalized.get("uuid") or uuid.uuid4())
                normalized["parentUuid"] = parent_uuid
                normalized.setdefault("isSidechain", False)
                normalized.setdefault("userType", "external")
                normalized.setdefault("entrypoint", "api")
                normalized.setdefault("cwd", str(Path.cwd()))
                normalized["messageFingerprint"] = fingerprint
                merged.append(normalized)
                parent_uuid = normalized["uuid"]
                seen.add(fingerprint)

        return merged

    def _migrate_thread_message_logs(self, thread_dir: Path) -> None:
        message_path = self._message_log_path(thread_dir)
        message_entries = self._read_jsonl_entries(message_path)
        event_entries: list[dict[str, Any]] = []
        snapshot_entries: list[dict[str, Any]] = []

        if message_entries:
            if self._looks_like_event_log(message_entries):
                event_entries = message_entries
            else:
                snapshot_entries = message_entries

        for legacy_name in self.legacy_snapshot_log_filenames:
            legacy_path = thread_dir / legacy_name
            legacy_entries = self._read_jsonl_entries(legacy_path)
            if legacy_entries:
                if self._looks_like_event_log(legacy_entries):
                    event_entries = self._merge_event_entries(event_entries, legacy_entries)
                else:
                    snapshot_entries.extend(legacy_entries)

        converted_entries = self._convert_legacy_snapshot_entries_to_event_entries(snapshot_entries)
        merged_entries = self._merge_event_entries(converted_entries, event_entries)

        if merged_entries:
            self._write_jsonl_entries(message_path, merged_entries)
        elif message_path.exists():
            message_path.unlink()

        for legacy_name in self.legacy_snapshot_log_filenames:
            legacy_path = thread_dir / legacy_name
            if legacy_path.exists() and legacy_path != message_path:
                legacy_path.unlink()

    def _migrate_thread_state_logs(self, thread_dir: Path) -> None:
        state_path = self._state_log_path(thread_dir)
        if state_path.exists():
            for legacy_name in self.legacy_state_log_filenames:
                legacy_path = thread_dir / legacy_name
                if legacy_path.exists():
                    legacy_path.unlink()
            return

        checkpoints_path = thread_dir / "checkpoints.jsonl"
        writes_path = thread_dir / "writes.jsonl"
        checkpoint_entries = self._read_jsonl_entries(checkpoints_path)
        if not checkpoint_entries:
            if writes_path.exists():
                writes_path.unlink()
            return

        writes_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for write_entry in self._read_jsonl_entries(writes_path):
            checkpoint_id = str(write_entry.get("checkpoint_id", ""))
            checkpoint_ns = str(write_entry.get("checkpoint_ns", ""))
            if not checkpoint_id:
                continue
            writes_by_key.setdefault((checkpoint_ns, checkpoint_id), []).append(write_entry)

        state_entries: list[dict[str, Any]] = []
        for checkpoint_entry in checkpoint_entries:
            checkpoint_id = str(checkpoint_entry.get("checkpoint_id", ""))
            checkpoint_ns = str(checkpoint_entry.get("checkpoint_ns", ""))
            pending_writes = writes_by_key.get((checkpoint_ns, checkpoint_id), [])
            state_entries.append(
                {
                    **checkpoint_entry,
                    "pending_writes": pending_writes,
                }
            )

        self._write_jsonl_entries(state_path, state_entries)
        if checkpoints_path.exists():
            checkpoints_path.unlink()
        if writes_path.exists():
            writes_path.unlink()

    def _migrate_existing_logs(self) -> None:
        for thread_dir in self.checkpoints_dir.iterdir():
            if not thread_dir.is_dir():
                continue
            try:
                self._migrate_thread_message_logs(thread_dir)
                self._migrate_thread_state_logs(thread_dir)
            except Exception:
                logger.warning("Failed to migrate logs for %s", thread_dir.name)

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

    def _checkpoint_message_count(self, checkpoint: Checkpoint | dict[str, Any] | None) -> int:
        if not isinstance(checkpoint, dict):
            return 0
        channel_values = checkpoint.get("channel_values", {})
        messages = channel_values.get("messages", []) if isinstance(channel_values, dict) else []
        return len(messages) if isinstance(messages, list) else 0

    def _read_checkpoint_by_id(
        self,
        *,
        thread_dir: Path,
        checkpoint_ns: str,
        checkpoint_id: str | None,
    ) -> Checkpoint | None:
        if not checkpoint_id:
            return None
        for entry in reversed(self._read_state_entries(thread_dir)):
            if entry.get("checkpoint_ns", "") != checkpoint_ns:
                continue
            if entry.get("checkpoint_id") != checkpoint_id:
                continue
            return self.serde.loads_typed(self._decode_typed(entry["checkpoint"]))
        return None

    def _message_fingerprint(self, msg: BaseMessage) -> str:
        payload = {
            "type": self._infer_role(msg),
            "message": self._serialize_event_message(msg),
            "tool_call_id": getattr(msg, "tool_call_id", None),
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _read_event_fingerprints(self, thread_dir: Path) -> set[str]:
        path = self._message_log_path(thread_dir)
        if not path.exists():
            return set()
        fingerprints: set[str] = set()
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                fingerprint = entry.get("messageFingerprint")
                if isinstance(fingerprint, str):
                    fingerprints.add(fingerprint)
        return fingerprints

    def _read_state_entries(self, thread_dir: Path) -> list[dict[str, Any]]:
        return self._read_jsonl_entries(self._state_log_path(thread_dir))

    def _last_event_uuid(self, thread_dir: Path) -> str | None:
        path = self._message_log_path(thread_dir)
        if not path.exists():
            return None
        last_uuid: str | None = None
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                uuid_value = entry.get("uuid")
                if isinstance(uuid_value, str):
                    last_uuid = uuid_value
        return last_uuid

    async def _append_events_claude_format(
        self,
        *,
        thread_dir: Path,
        thread_id: str,
        checkpoint_id: str,
        messages: list[BaseMessage],
    ) -> None:
        if not messages:
            return
        events_file = self._message_log_path(thread_dir)
        existing_fingerprints = self._read_event_fingerprints(thread_dir)
        entries: list[str] = []
        if thread_id not in self._last_event_message_uuid:
            last_uuid = self._last_event_uuid(thread_dir)
            if last_uuid:
                self._last_event_message_uuid[thread_id] = last_uuid
        for msg in messages:
            fingerprint = self._message_fingerprint(msg)
            if fingerprint in existing_fingerprints:
                continue
            message_uuid = str(uuid.uuid4())
            parent_uuid = self._last_event_message_uuid.get(thread_id)
            entry = {
                "parentUuid": parent_uuid,
                "isSidechain": False,
                "type": self._infer_role(msg),
                "message": self._serialize_event_message(msg),
                "uuid": message_uuid,
                "timestamp": self._now_iso(),
                "sessionId": thread_id,
                "checkpointId": checkpoint_id,
                "messageFingerprint": fingerprint,
                "userType": "external",
                "entrypoint": "api",
                "cwd": str(Path.cwd()),
            }
            self._last_event_message_uuid[thread_id] = message_uuid
            existing_fingerprints.add(fingerprint)
            entries.append(json.dumps(entry, ensure_ascii=False))

        if not entries:
            return
        async with aiofiles.open(events_file, "a", encoding="utf-8") as f:
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
            parent_checkpoint = self._read_checkpoint_by_id(
                thread_dir=thread_dir,
                checkpoint_ns=checkpoint_ns,
                checkpoint_id=config["configurable"].get("checkpoint_id"),
            )
            parent_count = self._checkpoint_message_count(parent_checkpoint)
            new_messages = base_messages[parent_count:] if parent_count <= len(base_messages) else base_messages
            await self._append_events_claude_format(
                thread_dir=thread_dir,
                thread_id=thread_id,
                checkpoint_id=checkpoint_id,
                messages=new_messages,
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
            "pending_writes": [],
        }

        state_entries = self._read_state_entries(thread_dir)
        state_entries.append(entry)
        self._write_jsonl_entries(self._state_log_path(thread_dir), state_entries)

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

        state_entries = self._read_state_entries(thread_dir)
        updated = False
        for state_entry in state_entries:
            if (
                state_entry.get("thread_id") == thread_id
                and state_entry.get("checkpoint_ns", "") == checkpoint_ns
                and state_entry.get("checkpoint_id") == checkpoint_id
            ):
                existing = state_entry.get("pending_writes", [])
                state_entry["pending_writes"] = [*existing, *entries]
                updated = True
                break
        if not updated:
            logger.warning(
                "State entry not found for pending writes (thread_id=%s, checkpoint_id=%s)",
                thread_id,
                checkpoint_id,
            )
            return
        self._write_jsonl_entries(self._state_log_path(thread_dir), state_entries)

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        raise NotImplementedError("Use aput_writes() for AsyncJsonlCheckpointSaver")

    def _read_write_entries(
        self,
        *,
        state_entry: dict[str, Any],
    ) -> list[tuple[str, str, Any]]:
        seen: dict[tuple[str, int], tuple[str, str, Any]] = {}
        pending_writes = state_entry.get("pending_writes", [])
        for entry in pending_writes:
            if not isinstance(entry, dict):
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
        entries = self._read_state_entries(thread_dir)
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
            pending_writes=self._read_write_entries(state_entry=selected),
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
            entries = list(reversed(self._read_state_entries(thread_dir)))
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
        messages_file = self._message_log_path(thread_dir)
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
