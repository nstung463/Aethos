"""Aethos API server.

OpenAI-compatible API server for Aethos LangGraph agent.

Usage:
    python main.py
    # → http://localhost:8080

Endpoints:
    GET  /v1/models               — list available models
    POST /v1/chat/completions     — chat (streaming + non-streaming)

Aethos frontend (``frontend/``):
    Set ``VITE_API_BASE_URL`` to the API origin (e.g. http://localhost:8080).
    The UI talks to ``/v1/models`` and ``/v1/chat/completions`` on that host.

Multiple models:
    Set ``AETHOS_MODEL_REGISTRY`` in ``.env`` (JSON array of {id, provider, model}).
    Pick the model from the in-app model selector.

Streaming features:
    - Text tokens → streamed as `delta.content`
    - Thinking blocks (Claude extended thinking) → `delta.reasoning_content`
    - Tool calls → shown as status updates in `delta.reasoning_content`
"""

import os
from pathlib import Path

import uvicorn
from src.app import create_app


def main() -> None:
    """Run the API server."""
    reload_enabled = os.getenv("AETHOS_RELOAD", "true").lower() in {"1", "true", "yes", "on"}
    port = int(os.getenv("PORT", "8080"))
    project_root = Path(__file__).resolve().parent
    if reload_enabled:
        # Uvicorn requires import string when reload/workers is enabled.
        uvicorn.run(
            "main:create_app",
            host="0.0.0.0",
            port=port,
            reload=True,
            factory=True,
            log_config=None,
            access_log=True,
            reload_dirs=[str(project_root / "src"), str(project_root)],
            reload_includes=["*.py"],
            reload_excludes=[
                "logs/*",
                "*.log",
                ".git/*",
                ".venv/*",
                "__pycache__/*",
            ],
        )
        return

    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=port, reload=False, log_config=None, access_log=True)


if __name__ == "__main__":
    main()
