"""Server-sent event (SSE) utilities for streaming chat responses."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any


SANDBOX_ATTACHMENTS_ROOT = "/tmp/ethos/attachments"


def sse(delta: dict[str, Any], model: str, finish_reason: str | None = None) -> str:
    """Format one SSE data frame in OpenAI chat completion chunk format."""
    payload = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "delta": delta,
            "finish_reason": finish_reason,
        }],
    }
    return f"data: {json.dumps(payload)}\n\n"
