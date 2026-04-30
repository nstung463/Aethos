# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Ethos** is an AI agent framework built on LangGraph that executes code in sandboxed environments. It provides both a CLI interface and an OpenAI-compatible REST API.

The agent can be deployed in multiple modes:
- **Local**: Direct filesystem access via pathlib
- **LocalSandbox**: Subprocess-based execution within a workspace directory
- **Daytona**: Remote cloud sandbox execution
- **OpenTerminal**: HTTP-based execution backend

## Architecture

### Core Components

**Agent Factory** (`src/graph.py`)
- Creates the main LangGraph agent via `create_ethos_agent()`
- Supports multiple backend implementations (local, sandbox, Daytona, OpenTerminal)
- Configures tools, middleware, and model selection

**Backends** (`src/backends/`)
- `protocol.py` — Abstract base class defining the sandbox interface
- `local.py` — LocalSandbox backend (subprocess execution in workspace)
- `daytona.py` — Remote sandbox via Daytona cloud
- `open_terminal.py` — HTTP-based execution via Open Terminal service
- `sandbox.py` — Base implementation for file operations

**Tools** (`src/ai/tools/`)
- `filesystem/` — Read, write, edit, glob, grep, notebook operations
- `execute.py` — Execute shell commands in sandbox mode
- `web.py` — Tavily web search, thinking tool

**Middleware** (`src/ai/middleware/`)
- `todos.py` — Manages task tracking and progress
- `skills.py` — Loads and applies custom agent skills from workspace
- `memory.py` — Persistent context via AGENTS.md file

**API** (`src/app/`)
- `app.py` — FastAPI application factory with CORS middleware
- `routes/` — OpenAI-compatible chat, files, terminals
- `models/` — Request/response schemas

### Execution Modes

The agent runs in two primary ways:

1. **CLI Mode** (`python ethos.py`)
   - Interactive REPL for agent interaction
   - Maintains thread ID for conversation state
   - Modes: local (default), `--sandbox`, `--daytona`, `--open-terminal`

2. **API Server** (`python main.py`)
   - OpenAI-compatible surface for the Ethos frontend (`frontend/`) and other clients
   - Streams responses including thinking blocks and tool calls
   - Runs on port 8080

3. **LangGraph Deployment** (`langgraph dev`)
   - Exposes graph for LangGraph Studio
   - Uses `graph` exported from `ethos.py`

### Full Stack

Docker Compose (`docker-compose.yml`) orchestrates three services:
- **ethos-api** — Main agent API (port 8080)
- **open-terminal** — Execution backend (port 8000)
- **ethos-frontend** — Vite + React UI from `frontend/` (port 3000)

## Development

### Setup & Installation

```bash
# Install dependencies using uv
uv sync --all-groups

# Copy environment configuration
cp .env.example .env
# Edit .env with your API keys (OPENROUTER, ANTHROPIC, or OPENAI)
```

### Common Commands

**CLI Agent** (local mode, default)
```bash
python ethos.py
```

**CLI Agent** (with execution backend)
```bash
# LocalSandbox mode (subprocess in ./workspace)
python ethos.py --sandbox

# Daytona remote sandbox
python ethos.py --daytona

# Open Terminal HTTP backend
python ethos.py --open-terminal
```

**API Server** (listens on http://localhost:8080)
```bash
python main.py
```

**Full Stack** (Docker Compose with all services)
```bash
./start-dev.sh
# or on Windows:
# start-dev.bat
```

**Tests**
```bash
# Run all tests
pytest

# Run a specific test file
pytest tests/tools/filesystem/test_read_file.py

# Run with verbose output
pytest -v

# Run async tests with live event loop
pytest --asyncio-mode=auto
```

**LangGraph Deployment**
```bash
langgraph dev
# Exposes graph on http://localhost:8123
```

## Key Files & Structure

```
ethos/
├── ethos.py              # CLI entry point; exports create_graph()
├── main.py               # API server (OpenAI compatible)
├── pyproject.toml        # Python project config (uv, pytest, hatchling)
├── docker-compose.yml    # Full stack orchestration
├── Dockerfile            # Container image for ethos-api
├── start-dev.sh/bat      # Start full stack with health checks
│
├── src/                  # Core agent implementation
│   ├── graph.py          # Agent factory; create_ethos_agent()
│   ├── config.py         # Environment config (model, workspace, providers)
│   ├── prompts.py        # System prompts
│   ├── subagents.py      # Task tool for delegating to subagents
│   ├── logger/           # Structured logging
│   │
│   ├── backends/         # Execution environments
│   │   ├── protocol.py   # BaseSandbox interface
│   │   ├── sandbox.py    # Base implementations
│   │   ├── local.py      # LocalSandbox (subprocess)
│   │   ├── daytona.py    # Daytona cloud sandbox
│   │   └── open_terminal.py  # OpenTerminal HTTP backend
│   │
│   ├── tools/            # Agent tools
│   │   ├── filesystem/   # File operations (read, write, edit, glob, grep)
│   │   ├── execute.py    # Shell execution in sandbox
│   │   └── web.py        # Tavily search, thinking tool
│   │
│   ├── middleware/       # Middleware stack
│   │   ├── todos.py      # Task tracking
│   │   ├── skills.py     # Skill loading from workspace/skills
│   │   └── memory.py     # Context via workspace/AGENTS.md
│   │
│   └── api/              # FastAPI application
│       ├── app.py        # App factory with CORS
│       ├── routes/       # v1, files, terminals
│       └── models/       # Request/response schemas
│
├── frontend/             # Ethos web UI (Vite + React)
│
├── tests/                # Test suite
│   ├── conftest.py       # pytest fixtures
│   ├── test_*_backend.py # Backend tests
│   └── tools/            # Tool-specific tests
│
└── workspace/            # Default workspace (in .gitignore)
    ├── skills/           # Custom agent skills (YAML)
    └── AGENTS.md         # Memory file for persistent context
```

## Model & Provider Configuration

Configuration via `.env`:

**Provider Options**
- `ETHOS_PROVIDER=openrouter` (default) → requires `OPENROUTER_API_KEY`
- `ETHOS_PROVIDER=anthropic` → requires `ANTHROPIC_API_KEY`
- `ETHOS_PROVIDER=openai` → requires `OPENAI_API_KEY`

**Model Selection**
- Single model: `ETHOS_MODEL=openai/gpt-4o-mini`
- Multiple models: `ETHOS_MODEL_REGISTRY=[...]` (JSON array with id/provider/model)

See `src/config.py:get_model()` for how config is parsed.

## Testing

- **Framework**: pytest with async support (`pytest-asyncio`)
- **Config**: `pyproject.toml` sets `asyncio_mode = "auto"`
- **Location**: `tests/` with mirrored structure to source
- **Backend Tests**: Test against LocalSandbox, Daytona, OpenTerminal backends
- **Tool Tests**: Individual tool validation (filesystem, execution)

Run a single test:
```bash
pytest tests/tools/filesystem/test_read_file.py -v
```

## Storage Architecture

File-based, local-first — no external database required.

```
workspace/
├── users/
│   └── <user_id>/
│       ├── profile.json              # user info + permission defaults
│       ├── sessions/
│       │   └── <token_hash>.json     # session with 30-day sliding TTL
│       └── threads/
│           └── <thread_id>/
│               └── meta.json         # thread metadata + permission overlay
└── checkpoints.db                    # SQLite — LangGraph conversation history
```

Key properties:
- **Per-entity files** — no single-file bottleneck or corruption risk
- **Session TTL** — 30-day sliding expiry, configurable via `ETHOS_SESSION_TTL_SECONDS`
- **Token hashing** — session filenames are SHA-256 of the raw token (never stored in paths)
- **Atomic writes** — temp file + rename to prevent corruption on crash
- **Auto-migration** — first boot reads legacy `workspace/security/auth.json` and `threads.json`, migrates to new layout, renames originals to `.migrated`
- **Checkpoints** — `SqliteSaver` persists conversation history across server restarts

### Frontend Auth Flow

```
App load → ensureAuthToken()
  ├── Token in localStorage + validated? → use it (fast path)
  ├── Token in localStorage + not validated? → GET /auth/me
  │     ├── 200 OK → mark validated, proceed
  │     └── 401   → clear token, create new guest session
  └── No token → POST /auth/guest → save token
```

Concurrent startup calls are deduplicated via a `pendingValidation` promise. Mid-session 401s trigger automatic re-authentication and request retry in `authFetch`.

## Important Patterns

### Backend Selection

```python
# Local mode (default): use pathlib directly
agent = create_ethos_agent()

# Sandbox mode: all file/exec operations delegate to backend
from src.backends.local import LocalSandbox
backend = LocalSandbox(root_dir="./workspace")
agent = create_ethos_agent(backend=backend)
```

### Tools in Different Modes

- **Local mode**: Filesystem tools use pathlib; no execute tool
- **Sandbox mode**: Filesystem + execute tools delegate to backend (subprocess, Daytona, HTTP)

### Middleware Stack

Middleware runs in order:
1. **TodosMiddleware** — Tracks tasks created during execution
2. **SkillsMiddleware** — Loads skills from workspace/skills directory
3. **MemoryMiddleware** — Reads/writes context to workspace/AGENTS.md

### Streaming API

The API streams responses with:
- `delta.content` — Text tokens
- `delta.reasoning_content` — Thinking blocks + tool call status

The Ethos frontend consumes these streams for real-time display.

## Dependencies

Key dependencies (see `pyproject.toml`):
- `langgraph>=0.3` — Graph-based agents
- `langchain>=0.3` — LLM abstractions and tools
- `langchain-anthropic`, `langchain-openai` — Model providers
- `fastapi>=0.115` — REST API
- `uvicorn[standard]>=0.30` — ASGI server
- `tavily-python` — Web search tool
- `daytona>=0.161.0` — Cloud sandbox (optional)
- `python-dotenv` — Environment variables

Dev dependencies:
- `pytest>=8.0` — Testing
- `pytest-asyncio>=0.23` — Async test support
- `httpx>=0.27` — Async HTTP client

## Environment Variables

Required:
- `OPENROUTER_API_KEY` OR `ANTHROPIC_API_KEY` OR `OPENAI_API_KEY`
- `OPEN_TERMINAL_API_KEY` (if using open-terminal backend)

Optional:
- `ETHOS_PROVIDER` — Provider name (default: openrouter)
- `ETHOS_MODEL` — Model identifier (default: openai/gpt-4o-mini)
- `ETHOS_WORKSPACE` — Workspace path (default: ./workspace)
- `ETHOS_WORKSPACE_DIR` — Root workspace directory (default: `./workspace`)
- `ETHOS_USERS_DIR` — Per-user storage root (default: `$WORKSPACE/users`)
- `ETHOS_CHECKPOINTS_DB` — SQLite path for conversation history (default: `$WORKSPACE/checkpoints.db`)
- `ETHOS_SESSION_TTL_SECONDS` — Auth session lifetime in seconds (default: 2592000 = 30 days, sliding)
- `ETHOS_SECURITY_STATE_DIR` — Legacy security dir, used only for one-time migration (default: `$WORKSPACE/security`)
- `DAYTONA_API_KEY` — Daytona API key (if using --daytona)
- `OPEN_TERMINAL_URL` — OpenTerminal base URL (default: http://localhost:8000)
- `OPEN_TERMINAL_USER_ID` — User ID for OpenTerminal

## Docker & Deployment

**Build image locally:**
```bash
docker build -t ethos-api:latest .
```

**Run full stack:**
```bash
./start-dev.sh
```

**View logs:**
```bash
docker-compose logs -f ethos-api
docker-compose logs -f open-terminal
docker-compose logs -f ethos-frontend
```

**Stop stack:**
```bash
docker-compose down
```

The stack includes health checks for all three services. The startup script (`start-dev.sh`) validates configuration and service health before declaring success.

## Debugging

**Structured logging** via `src/logger/`:
- Set log level in environment (e.g., `LOG_LEVEL=DEBUG`)
- Logs include trace IDs for request correlation

**LangSmith integration** (optional):
- Set `LANGSMITH_API_KEY` and `LANGSMITH_PROJECT` in .env
- Traces appear in LangSmith dashboard

**Local testing without Docker:**
- Use `python ethos.py` for CLI (local mode)
- Use `python main.py` for API server
- Requires only `uv sync` and .env configuration
