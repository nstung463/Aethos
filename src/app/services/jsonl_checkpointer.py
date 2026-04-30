"""JSONL-based checkpoint saver for conversation history and full message context."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver, CheckpointTuple
from langchain_core.messages import BaseMessage


class JsonlCheckpointSaver(BaseCheckpointSaver):
    """Store LangGraph checkpoints as JSONL for full message context preservation.

    Each thread gets a directory with:
    - messages.jsonl: Complete message history with all metadata
    - checkpoints.jsonl: Checkpoint metadata for resumption
    """

    def __init__(self, base_dir: str | Path):
        """Initialize JSONL checkpoint saver.

        Args:
            base_dir: Root directory for storing checkpoint data
        """
        super().__init__()
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints_dir = self.base_dir / "checkpoints"
        self.checkpoints_dir.mkdir(exist_ok=True)

    def _get_thread_dir(self, thread_id: str) -> Path:
        """Get or create directory for a thread."""
        thread_dir = self.checkpoints_dir / thread_id
        thread_dir.mkdir(exist_ok=True)
        return thread_dir

    def _serialize_message(self, msg: BaseMessage) -> dict[str, Any]:
        """Convert LangChain message to serializable dict."""
        data: dict[str, Any] = {
            "type": msg.__class__.__name__,
            "role": getattr(msg, "role", None) or msg.__class__.__name__.replace("Message", "").lower(),
            "content": msg.content,
        }

        # Preserve tool-related fields
        if hasattr(msg, "tool_call_id") and msg.tool_call_id:
            data["tool_call_id"] = msg.tool_call_id
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            data["tool_calls"] = [
                {
                    "id": tc.id,
                    "name": tc.function.name if hasattr(tc, "function") else tc.get("function", {}).get("name"),
                    "args": tc.function.arguments if hasattr(tc, "function") else tc.get("function", {}).get("arguments"),
                }
                for tc in msg.tool_calls
            ]

        # Preserve additional attributes
        if hasattr(msg, "response_metadata"):
            data["response_metadata"] = msg.response_metadata

        return data

    def _messages_to_jsonl(self, thread_id: str, messages: list[BaseMessage]) -> None:
        """Write messages to JSONL file."""
        thread_dir = self._get_thread_dir(thread_id)
        messages_file = thread_dir / "messages.jsonl"

        with open(messages_file, "a", encoding="utf-8") as f:
            for msg in messages:
                entry = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "message": self._serialize_message(msg),
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def put(
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
        checkpoint_id = str(uuid.uuid4())

        thread_dir = self._get_thread_dir(thread_id)

        # Save messages separately for easy access
        messages = values.get("messages", [])
        if messages:
            self._messages_to_jsonl(thread_id, messages)

        # Save checkpoint metadata
        checkpoint_file = thread_dir / "checkpoints.jsonl"
        checkpoint_entry = {
            "checkpoint_id": checkpoint_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "thread_id": thread_id,
            "metadata": metadata,
            "message_count": len(messages),
        }

        with open(checkpoint_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(checkpoint_entry, ensure_ascii=False) + "\n")

    def get(self, config: dict[str, Any]) -> CheckpointTuple | None:
        """Retrieve latest checkpoint for a thread.

        Args:
            config: Configuration with thread_id

        Returns:
            CheckpointTuple if found, None otherwise
        """
        thread_id = config.get("configurable", {}).get("thread_id", "default")
        thread_dir = self._get_thread_dir(thread_id)

        # Read latest checkpoint
        checkpoint_file = thread_dir / "checkpoints.jsonl"
        if not checkpoint_file.exists():
            return None

        checkpoint_data = None
        with open(checkpoint_file, "r", encoding="utf-8") as f:
            for line in f:
                checkpoint_data = json.loads(line)

        if not checkpoint_data:
            return None

        # Read all messages for state
        messages = []
        messages_file = thread_dir / "messages.jsonl"
        if messages_file.exists():
            with open(messages_file, "r", encoding="utf-8") as f:
                for line in f:
                    entry = json.loads(line)
                    messages.append(entry["message"])

        values = {"messages": messages}
        metadata = checkpoint_data.get("metadata", {})

        return CheckpointTuple(
            values=values,
            metadata=metadata,
            config=config,
        )

    def list(
        self,
        config: dict[str, Any],
        filter: dict[str, Any] | None = None,
        before: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> list[CheckpointTuple]:
        """List checkpoints for a thread (simplified implementation)."""
        result = self.get(config)
        return [result] if result else []

    def get_tuple(self, config: dict[str, Any]) -> CheckpointTuple | None:
        """Get checkpoint tuple (same as get for our implementation)."""
        return self.get(config)
