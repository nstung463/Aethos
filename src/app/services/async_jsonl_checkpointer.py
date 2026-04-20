"""Async JSONL-based checkpoint saver for conversation history."""

from __future__ import annotations

import aiofiles
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver, CheckpointTuple
from langchain_core.messages import BaseMessage

from src.logger import get_logger

logger = get_logger(__name__)


class AsyncJsonlCheckpointSaver(BaseCheckpointSaver):
    """Async JSONL-based checkpoint saver for full message context preservation.

    Structure:
    ```
    workspace/
    ├── checkpoints/
    │   ├── thread_id_1/
    │   │   ├── messages.jsonl      # Complete message history
    │   │   ├── checkpoints.jsonl   # Checkpoint metadata
    │   │   └── metadata.json       # Thread metadata
    │   └── thread_id_2/
    │       ├── messages.jsonl
    │       ├── checkpoints.jsonl
    │       └── metadata.json
    ```

    Each message in messages.jsonl:
    ```json
    {"timestamp": "2026-04-20T16:00:00Z", "message": {"type": "HumanMessage", "role": "user", "content": "..."}}
    ```
    """

    def __init__(self, base_dir: str | Path):
        """Initialize async JSONL checkpoint saver.

        Args:
            base_dir: Root directory for storing checkpoint data
        """
        super().__init__()
        self.base_dir = Path(base_dir).resolve()
        self.checkpoints_dir = self.base_dir / "checkpoints"
        logger.debug(f"AsyncJsonlCheckpointSaver initialized with base_dir={self.base_dir}")

    async def _ensure_thread_dir(self, thread_id: str) -> Path:
        """Ensure thread directory exists."""
        thread_dir = self.checkpoints_dir / thread_id
        thread_dir.mkdir(parents=True, exist_ok=True)
        return thread_dir

    def _serialize_message(self, msg: BaseMessage) -> dict[str, Any]:
        """Convert LangChain message to serializable dict."""
        data: dict[str, Any] = {
            "type": msg.__class__.__name__,
            "role": getattr(msg, "role", None) or self._infer_role(msg),
            "content": msg.content,
        }

        # Preserve tool-related fields
        if hasattr(msg, "tool_call_id") and msg.tool_call_id:
            data["tool_call_id"] = msg.tool_call_id

        if hasattr(msg, "tool_calls") and msg.tool_calls:
            data["tool_calls"] = self._serialize_tool_calls(msg.tool_calls)

        # Preserve additional attributes
        if hasattr(msg, "response_metadata") and msg.response_metadata:
            data["response_metadata"] = msg.response_metadata

        return data

    def _infer_role(self, msg: BaseMessage) -> str:
        """Infer role from message class name."""
        class_name = msg.__class__.__name__
        if "Human" in class_name:
            return "user"
        if "AI" in class_name:
            return "assistant"
        if "System" in class_name:
            return "system"
        if "Tool" in class_name:
            return "tool"
        return class_name.replace("Message", "").lower()

    def _serialize_tool_calls(self, tool_calls: list[Any]) -> list[dict[str, Any]]:
        """Serialize tool calls from message."""
        result = []
        for tc in tool_calls:
            try:
                entry: dict[str, Any] = {"id": getattr(tc, "id", str(uuid.uuid4()))}

                # Handle ToolCall objects
                if hasattr(tc, "function"):
                    entry["name"] = tc.function.name
                    entry["args"] = tc.function.arguments
                # Handle dict-like tool calls
                elif isinstance(tc, dict):
                    entry["name"] = tc.get("function", {}).get("name", "")
                    entry["args"] = tc.get("function", {}).get("arguments", "")

                result.append(entry)
            except Exception as e:
                logger.warning(f"Failed to serialize tool call: {e}")

        return result

    async def put(
        self,
        config: dict[str, Any],
        values: dict[str, Any],
        metadata: dict[str, Any],
    ) -> None:
        """Save checkpoint with message history.

        Args:
            config: Configuration with thread_id
            values: State dict containing messages
            metadata: Checkpoint metadata
        """
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        thread_dir = await self._ensure_thread_dir(thread_id)

        # Save messages
        messages = values.get("messages", [])
        if messages:
            await self._append_messages(thread_dir, messages)

        # Save checkpoint metadata
        await self._save_checkpoint(thread_dir, thread_id, metadata, len(messages))

    async def _append_messages(self, thread_dir: Path, messages: list[BaseMessage]) -> None:
        """Append messages to messages.jsonl file."""
        messages_file = thread_dir / "messages.jsonl"
        entries = []

        for msg in messages:
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": self._serialize_message(msg),
            }
            entries.append(json.dumps(entry, ensure_ascii=False))

        async with aiofiles.open(messages_file, "a", encoding="utf-8") as f:
            for entry in entries:
                await f.write(entry + "\n")

        logger.debug(f"Saved {len(messages)} messages to {messages_file}")

    async def _save_checkpoint(
        self,
        thread_dir: Path,
        thread_id: str,
        metadata: dict[str, Any],
        message_count: int,
    ) -> None:
        """Save checkpoint metadata."""
        checkpoint_file = thread_dir / "checkpoints.jsonl"
        checkpoint_entry = {
            "checkpoint_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "thread_id": thread_id,
            "metadata": metadata,
            "message_count": message_count,
        }

        async with aiofiles.open(checkpoint_file, "a", encoding="utf-8") as f:
            await f.write(json.dumps(checkpoint_entry, ensure_ascii=False) + "\n")

    async def get(self, config: dict[str, Any]) -> CheckpointTuple | None:
        """Retrieve latest checkpoint for a thread.

        Args:
            config: Configuration with thread_id

        Returns:
            CheckpointTuple if found, None otherwise
        """
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        thread_dir = self.checkpoints_dir / thread_id

        if not thread_dir.exists():
            return None

        # Read all messages
        messages = await self._read_messages(thread_dir)
        if not messages:
            return None

        # Read latest checkpoint metadata
        checkpoint_file = thread_dir / "checkpoints.jsonl"
        metadata = {}
        if checkpoint_file.exists():
            async with aiofiles.open(checkpoint_file, "r", encoding="utf-8") as f:
                async for line in f:
                    checkpoint_data = json.loads(line)
                    metadata = checkpoint_data.get("metadata", {})

        values = {"messages": messages}
        return CheckpointTuple(
            values=values,
            metadata=metadata,
            config=config,
        )

    async def _read_messages(self, thread_dir: Path) -> list[dict[str, Any]]:
        """Read all messages from messages.jsonl file."""
        messages_file = thread_dir / "messages.jsonl"
        if not messages_file.exists():
            return []

        messages = []
        async with aiofiles.open(messages_file, "r", encoding="utf-8") as f:
            async for line in f:
                try:
                    entry = json.loads(line)
                    messages.append(entry["message"])
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse message entry: {e}")

        return messages

    async def list(
        self,
        config: dict[str, Any],
        filter: dict[str, Any] | None = None,
        before: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> list[CheckpointTuple]:
        """List checkpoints for a thread (simplified implementation)."""
        result = await self.get(config)
        return [result] if result else []

    async def get_tuple(self, config: dict[str, Any]) -> CheckpointTuple | None:
        """Get checkpoint tuple."""
        return await self.get(config)
