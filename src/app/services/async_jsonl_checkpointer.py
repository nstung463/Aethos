"""Async JSONL-based checkpoint saver using Claude's message format.

Stores complete conversation history with full context:
- Tool use calls with IDs and inputs
- Tool results linked to calls
- Thinking blocks
- Token usage and cache stats
- Conversation tree via parentUuid
"""

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
    """Claude-style JSONL checkpoint saver for complete conversation history.

    Storage structure (Claude format):
    workspace/checkpoints/
    ├── thread_1/
    │   ├── messages.jsonl      # Complete message history
    │   └── checkpoints.jsonl   # Checkpoint metadata

    Each message follows Claude's content block format:
    {
      "uuid": "msg-id",
      "parentUuid": "prev-msg-id",
      "type": "assistant|user|system",
      "message": {
        "role": "assistant|user|system",
        "content": [
          {"type": "text", "text": "..."},
          {"type": "tool_use", "id": "call_...", "name": "Read", "input": {...}},
          {"type": "tool_result", "tool_use_id": "call_...", "content": "..."},
          {"type": "thinking", "thinking": "..."}
        ],
        "stop_reason": "tool_use|end_turn",
        "usage": {"input_tokens": 123, "output_tokens": 45, ...}
      },
      "timestamp": "2026-04-20T16:00:00Z",
      "sessionId": "thread_id"
    }
    """

    def __init__(self, base_dir: str | Path):
        """Initialize async JSONL checkpoint saver."""
        super().__init__()
        self.base_dir = Path(base_dir).resolve()
        self.checkpoints_dir = self.base_dir / "checkpoints"
        logger.debug(f"AsyncJsonlCheckpointSaver initialized with base_dir={self.base_dir}")
        self._last_message_uuid: dict[str, str] = {}

    async def _ensure_thread_dir(self, thread_id: str) -> Path:
        """Ensure thread directory exists."""
        thread_dir = self.checkpoints_dir / thread_id
        thread_dir.mkdir(parents=True, exist_ok=True)
        return thread_dir

    def _serialize_message(self, msg: BaseMessage) -> dict[str, Any]:
        """Convert LangChain message to Claude-style content blocks."""
        content: list[dict[str, Any]] = []

        # Handle content as text block
        if hasattr(msg, "content") and msg.content:
            if isinstance(msg.content, str):
                content.append({"type": "text", "text": msg.content})
            elif isinstance(msg.content, list):
                for block in msg.content:
                    if isinstance(block, dict):
                        content.append(block)
                    else:
                        content.append({"type": "text", "text": str(block)})

        # Add tool_calls as tool_use blocks
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

        # Add thinking blocks if present
        if hasattr(msg, "thinking") and msg.thinking:
            content.append({"type": "thinking", "thinking": msg.thinking})

        result = {
            "role": getattr(msg, "role", None) or self._infer_role(msg),
            "content": content or [{"type": "text", "text": ""}],
        }

        # Add stop_reason if present
        if hasattr(msg, "stop_reason"):
            result["stop_reason"] = msg.stop_reason
        else:
            result["stop_reason"] = "end_turn"

        # Add usage stats if present
        if hasattr(msg, "response_metadata") and isinstance(msg.response_metadata, dict):
            usage = msg.response_metadata.get("usage")
            if usage:
                result["usage"] = usage

        return result

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
            return "user"
        return "user"

    async def put(
        self,
        config: dict[str, Any],
        values: dict[str, Any],
        metadata: dict[str, Any],
    ) -> None:
        """Save checkpoint with message history (Claude format)."""
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        thread_dir = await self._ensure_thread_dir(thread_id)

        messages = values.get("messages", [])
        if messages:
            await self._append_messages_claude_format(thread_dir, thread_id, messages)

        await self._save_checkpoint(thread_dir, thread_id, metadata, len(messages))

    async def _append_messages_claude_format(
        self,
        thread_dir: Path,
        thread_id: str,
        messages: list[BaseMessage],
    ) -> None:
        """Append messages to messages.jsonl in Claude format."""
        messages_file = thread_dir / "messages.jsonl"
        entries = []

        for msg in messages:
            message_uuid = str(uuid.uuid4())
            parent_uuid = self._last_message_uuid.get(thread_id)

            entry = {
                "uuid": message_uuid,
                "parentUuid": parent_uuid,
                "type": self._infer_role(msg),
                "message": self._serialize_message(msg),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "sessionId": thread_id,
            }

            self._last_message_uuid[thread_id] = message_uuid
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
        """Retrieve latest checkpoint for a thread."""
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        thread_dir = self.checkpoints_dir / thread_id

        if not thread_dir.exists():
            return None

        messages = await self._read_messages(thread_dir)
        if not messages:
            return None

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
        """List checkpoints for a thread."""
        result = await self.get(config)
        return [result] if result else []

    async def get_tuple(self, config: dict[str, Any]) -> CheckpointTuple | None:
        """Get checkpoint tuple."""
        return await self.get(config)
