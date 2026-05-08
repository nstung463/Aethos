# AI Core Structure

Use `src/ai` for all agent-runtime code.

```text
src/ai/
  agents/        # agent factories, subagent catalogs, orchestration
  middleware/    # LangChain/LangGraph middleware and guards
  prompts/       # system prompts and prompt builders
  skills/        # skill loaders, registries, and prompt injection support
  tools/         # tool groups exposed to agents
```

Migration mapping from the current codebase:

- `src/graph.py` -> `src/ai/agents/aethos.py`
- `src/subagents.py` -> `src/ai/agents/subagents.py`
- `src/prompts.py` -> `src/ai/prompts/catalog.py`
- `src/middleware/*` -> `src/ai/middleware/*`
- `src/tools/*` -> `src/ai/tools/*`
- root `skills/` directory remains content/data; loader code belongs in `src/ai/skills`

Current status:

- `src/ai/agents/aethos.py` is the Aethos agent factory
- `src/ai/agents/subagents.py` is the subagent and task-tool implementation
- `src/ai/prompts/catalog.py` is the prompt catalog
- `src/ai/middleware/*` is the middleware location
- `src/ai/tools/*` is the tool implementation tree
- legacy runtime paths under `src/graph.py`, `src/subagents.py`, `src/prompts.py`,
  `src/middleware/*`, and `src/tools/*` have been removed

Recommended split:

1. Keep HTTP/API/business logic under `src/app`
2. Keep AI orchestration under `src/ai`
3. Keep infrastructure integrations under existing shared packages until they need a dedicated home
