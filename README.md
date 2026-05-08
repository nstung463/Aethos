<div align="center">
  <h1>Aethos</h1>
</div>

<div align="center">
  <h3>A full-stack AI agent and automation platform.</h3>
</div>

<div align="center">
  <a href="https://aethos-frontend-inky.vercel.app/app" target="_blank"><img src="https://img.shields.io/badge/Live%20App-Open-0f766e" alt="Live App"></a>
  <img src="https://img.shields.io/badge/Agent-LangGraph%20%2B%20LangChain-2563eb" alt="LangGraph + LangChain">
  <img src="https://img.shields.io/badge/Connectors-MCP%20%2B%20Zapier-0f766e" alt="MCP + Zapier">
  <img src="https://img.shields.io/badge/API-FastAPI-f97316" alt="FastAPI">
  <img src="https://img.shields.io/badge/UI-React%20%2B%20Vite-7e22ce" alt="React + Vite">
</div>

<br>

Aethos is an agent harness for coding, research, operations, and workflow automation. It wraps an LLM with tools, skills, MCP connectors, memory, permissions, streaming, and execution backends - then ships it as an OpenAI-compatible API and a web workspace.

Not a chat wrapper. Aethos is the runtime layer around the model, built to connect agents with real tools, apps, data, and business workflows.

**What's included:**

- **Models** - OpenAI-compatible provider routing and per-request model profiles
- **Tools** - filesystem, shell, web, terminal, uploads, and task delegation
- **Skills** - local `SKILL.md` workflows loaded into the agent context
- **MCP** - first-class MCP connector and custom MCP server support
- **Integrations** - connect agents to apps through MCP, Zapier, Slack, APIs, and data sources
- **Memory** - project-scoped threads, checkpoints, and persistent context
- **Permissions** - approval-aware read, edit, shell, skill, MCP, and automation policies
- **Streaming** - tokens, tool calls, reasoning, permission events, and run state

## Integrations

Aethos is designed for agent workflows that reach beyond the IDE. Connect tools and services through MCP connectors, custom MCP servers, Zapier, Slack integrations, the Manus API, and structured data sources.

Example apps and data sources:

- **Work apps** - Gmail, Notion, Slack, Google Calendar, Google Drive
- **Developer tools** - GitHub, Hugging Face, custom APIs, internal services
- **Business systems** - Stripe, HubSpot, CRMs, billing, support, and analytics tools
- **Automation layers** - Zapier, MCP servers, webhooks, scheduled jobs, and human approvals

Use Aethos to build agents that code, search, summarize, update systems, trigger workflows, and coordinate work across connected applications.

## Quickstart

```bash
uv sync --all-groups
cp .env.example .env
uv run python main.py
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Backend runs on `http://localhost:8080`. Frontend usually runs on `http://localhost:5173`.

## CLI

```bash
uv run python aethos.py
uv run python aethos.py --sandbox
uv run python aethos.py --daytona
uv run python aethos.py --open-terminal
```

## API

Aethos exposes OpenAI-compatible chat completions plus workspace APIs.

```bash
curl http://localhost:8080/v1/models
```

Core routes:

- `POST /v1/chat/completions` - streaming and non-streaming agent runs
- `GET /v1/models` - available model profiles
- `POST /v1/threads` - persisted conversation threads
- `GET/PATCH /v1/threads/{id}/permissions` - thread permission overlays
- `GET/POST /v1/extensions/*` - skills and MCP configuration
- `POST /api/files` - managed file uploads

## Architecture

```text
React/Vite UI
    v
FastAPI API  ->  threads, files, auth, settings
    v
LangGraph/LangChain agent
    v
tools + skills + MCP + memory + permissions
    v
local tools, sandboxes, MCP servers, apps, APIs, and data sources
```

## Repository

```text
src/ai/              agent, tools, middleware, skills, permissions
src/app/             FastAPI modules and services
src/backends/        local, sandbox, Daytona, Open Terminal adapters
frontend/src/        React workspace UI
tests/               backend test suite
rules/               development rules for agents
```

## Configuration

Set at least one provider key in `.env`:

```bash
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
OPENROUTER_API_KEY=...
```

Runtime settings use Claude-style layering through `SettingsService`:

```text
~/.ethos/settings.json
<workspace>/.ethos/settings.json
<workspace>/.ethos/settings.local.json
<managed-dir>/managed-settings.json
<managed-dir>/managed-settings.d/*.json
```

Project runtime data lives under `~/.ethos/projects/<project_key>/`.

## Tests

```bash
uv run pytest
cd frontend && npm run build
```

## Why Aethos?

- **Agent-native** - built for coding agents, research agents, ops agents, and automation workflows
- **Connector-ready** - integrate MCP servers, Zapier actions, Slack bots, APIs, and live data
- **Provider agnostic** - bring OpenAI, Anthropic, OpenRouter, local, or compatible models
- **Permission-aware** - risky actions pause for approval instead of silently executing
- **Workspace-native** - files, terminals, memory, settings, and threads are first-class
- **Built on LangGraph** - durable execution, streaming, checkpoints, and tool orchestration
