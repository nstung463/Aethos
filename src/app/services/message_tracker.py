"""Track which messages are from the current request vs resumed from history.

Solves the problem of distinguishing between:
1. New messages from current client request
2. Messages resumed from thread history
3. Messages injected by system (tool results, etc)
"""

from __future__ import annotations

from typing import Any


class MessageRequestTracker:
    """Track message flow through a chat request."""

    def __init__(self, thread_id: str, incoming_message_count: int):
        """Initialize tracker.

        Args:
            thread_id: The thread being processed
            incoming_message_count: Number of messages in current request
        """
        self.thread_id = thread_id
        self.incoming_message_count = incoming_message_count
        self.current_request_markers: set[int] = set()

    def mark_as_current_request(self, message_indices: list[int]) -> None:
        """Mark message indices as being from current request."""
        self.current_request_markers.update(message_indices)

    def is_from_current_request(self, message_index: int) -> bool:
        """Check if message at index is from current request."""
        return message_index in self.current_request_markers

    def get_incoming_messages_count(self) -> int:
        """Get count of messages in current request."""
        return self.incoming_message_count

    def to_dict(self) -> dict[str, Any]:
        """Serialize tracker state for metadata."""
        return {
            "thread_id": self.thread_id,
            "incoming_message_count": self.incoming_message_count,
            "current_request_message_indices": sorted(self.current_request_markers),
        }


def create_request_tracker(
    thread_id: str,
    incoming_messages: list[Any],
    is_resume: bool = False,
) -> MessageRequestTracker:
    """Factory to create properly initialized tracker.

    Args:
        thread_id: The thread ID
        incoming_messages: Messages from current request
        is_resume: Whether this is a resume operation

    Returns:
        Initialized MessageRequestTracker
    """
    tracker = MessageRequestTracker(
        thread_id=thread_id,
        incoming_message_count=len(incoming_messages),
    )

    if not is_resume:
        # All messages in request are from current request
        tracker.mark_as_current_request(list(range(len(incoming_messages))))

    return tracker
