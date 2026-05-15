# src/app Backend Structure

This package is organized around `features` plus shared platform layers.

## Folder Responsibilities

- `api/`: HTTP transport assembly only (`router`, DI dependencies, error handling). Keep request wiring here, not business logic.
- `features/`: Domain vertical slices (for example `auth`, `files`, `chat`, `extensions`). Each feature should own its route handlers, schemas, services, and feature-local repository/policy logic.
- `services/`: Cross-feature infrastructure and runtime services (database wiring, storage paths, rate limiting, permissions helpers, profiler, task helpers).
- `repositories/`: Shared persistence abstractions/implementations reused across features.
- `db/`: SQLAlchemy base/session and database models.
- `core/`: App-global primitives such as settings and logging setup.
- `legacy/`: Transitional compatibility code. Do not add new product logic here.
- `modules/`: Transitional namespace retained only for thin compatibility shims. New code should not be added here.

## Deprecation Window (modules/chat + modules/extensions)

- Deprecation window: `1 release cycle`.
- `src.app.modules.chat` and `src.app.modules.extensions` remain only as thin package shims during this window.
- The only supported shim surface is package import plus `router.py`.
- New imports in active source and tests must use `src.app.features.chat.*` and `src.app.features.extensions.*`.
- Sunset criteria for removing these shims:
  - no imports outside the temporary shim allowlist
  - backend structure guardrails are green
  - core backend regression suite for chat/extensions/storage is green

## Import Boundaries

- `api/*` may import from `features/*`, `services/*`, `repositories/*`, `core/*`, and `db/*`.
- `features/*` may import from `services/*`, `repositories/*`, `core/*`, and `db/*`.
- `services/*` must stay feature-agnostic whenever possible.
- Avoid adding new imports from `features/*` into `repositories/*` unless there is a shared contract that cannot live elsewhere.
- Do not add new dependencies from active code into `legacy/*`.

## Adding a New Feature

1. Create `src/app/features/<feature_name>/`.
2. Add at minimum `router.py`, `schemas.py`, and `service.py`; add `repository.py` and `policy.py` when needed.
3. Export a single `router = APIRouter()` from the feature.
4. Register the router in `src/app/api/router.py` via `include_router()`.
5. Keep DI wiring in `src/app/api/dependencies.py`; do not duplicate singleton wiring inside route modules.
6. Add focused backend tests for the feature behavior and route integration.
