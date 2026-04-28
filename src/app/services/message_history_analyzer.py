"""Analyze and understand message history flow.

Helps reconstruct conversation tree and track message relationships.
"""

from __future__ import annotations

from typing import Any


class MessageHistoryAnalyzer:
    """Analyze message history entries to understand conversation flow."""

    def __init__(self, message_entries: list[dict[str, Any]]):
        """Initialize analyzer with message entries.

        Args:
            message_entries: Full message entries from checkpointer including uuid, parentUuid, etc
        """
        self.entries = message_entries
        self._uuid_index = self._build_uuid_index()

    def _build_uuid_index(self) -> dict[str, int]:
        """Build index from uuid to entry position."""
        return {entry.get("uuid"): idx for idx, entry in enumerate(self.entries)}

    def get_message_chain(self, end_uuid: str | None = None) -> list[dict[str, Any]]:
        """Get chain of messages from start to end (following parentUuid).

        Args:
            end_uuid: The UUID to trace back from. If None, starts from last message.

        Returns:
            List of message entries in chronological order.
        """
        if not self.entries:
            return []

        if end_uuid is None:
            end_uuid = self.entries[-1].get("uuid")

        chain = []
        current_uuid = end_uuid

        while current_uuid is not None:
            if current_uuid not in self._uuid_index:
                break

            idx = self._uuid_index[current_uuid]
            entry = self.entries[idx]
            chain.append(entry)
            current_uuid = entry.get("parentUuid")

        return list(reversed(chain))

    def get_conversation_summary(self) -> dict[str, Any]:
        """Get summary of conversation structure."""
        return {
            "total_messages": len(self.entries),
            "first_message_uuid": self.entries[0].get("uuid") if self.entries else None,
            "last_message_uuid": self.entries[-1].get("uuid") if self.entries else None,
            "message_types": self._count_message_types(),
            "timestamp_range": self._get_timestamp_range(),
        }

    def _count_message_types(self) -> dict[str, int]:
        """Count messages by type (user, assistant, system)."""
        counts = {}
        for entry in self.entries:
            msg_type = entry.get("type", "unknown")
            counts[msg_type] = counts.get(msg_type, 0) + 1
        return counts

    def _get_timestamp_range(self) -> dict[str, str | None]:
        """Get first and last message timestamps."""
        if not self.entries:
            return {"first": None, "last": None}

        return {
            "first": self.entries[0].get("timestamp"),
            "last": self.entries[-1].get("timestamp"),
        }

    def validate_chain_integrity(self) -> dict[str, Any]:
        """Validate that parentUuid references form a valid chain.

        Returns:
            Dict with issues found, empty if valid.
        """
        issues = {
            "broken_references": [],
            "orphaned_messages": [],
            "duplicates": [],
        }

        seen_uuids = set()
        for idx, entry in enumerate(self.entries):
            uuid = entry.get("uuid")

            # Check for duplicates
            if uuid in seen_uuids:
                issues["duplicates"].append({"index": idx, "uuid": uuid})
            seen_uuids.add(uuid)

            # Check parent reference
            parent_uuid = entry.get("parentUuid")
            if parent_uuid and parent_uuid not in self._uuid_index:
                issues["broken_references"].append({
                    "index": idx,
                    "uuid": uuid,
                    "broken_parent": parent_uuid,
                })

        # Check for orphaned messages (not in any chain)
        first_uuids = {e.get("uuid") for e in self.entries if e.get("parentUuid") is None}
        for uuid in self._uuid_index.keys():
            if uuid not in first_uuids:
                chain_found = False
                for entry in self.entries:
                    if entry.get("uuid") == uuid:
                        chain = self.get_message_chain(uuid)
                        if chain:
                            chain_found = True
                            break
                if not chain_found:
                    issues["orphaned_messages"].append(uuid)

        return {k: v for k, v in issues.items() if v}
