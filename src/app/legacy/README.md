# Legacy App Storage

This folder keeps transitional storage implementations that still exist for one of two reasons:

- active runtime support for old thread metadata layouts while the newer project-scoped storage model settles
- back-compat import paths for code that has not been fully migrated yet

Do not add new product code here. New storage or checkpoint work should go into `src/app/services`, `src/app/repositories`, or `src/app/db` depending on responsibility.

## Current status

- `thread_index.py`: Compatibility shim. Re-exports `src.app.services.thread_index.ThreadIndex` for callers still using the old import path.
- `thread_store.py`: Compatibility shim. Re-exports `src.app.services.thread_store.ThreadStore` for callers still using the old import path.
- `postgres_thread_store.py`: Compatibility shim. Preserves the old `PostgresThreadRepository` import path while delegating runtime behavior to `src/app/repositories/thread_repository.py`.
- `async_jsonl_checkpointer.py`: Legacy checkpoint implementation. Retained for migration/reference, but not imported by current runtime paths in `src/app`.
- `jsonl_checkpointer.py`: Older JSONL checkpoint implementation retained for reference only. Not imported by current runtime paths in `src/app`.

## Retirement direction

- Remove `thread_index.py` and `thread_store.py` once no external callers depend on the old import paths.
- Remove `postgres_thread_store.py` after all callers stop depending on the old class name/import path.
- Remove the JSONL checkpoint savers once there is no remaining data migration or debugging workflow that depends on them.

## Contributor rule

If you are adding a new feature and think it belongs here, that is usually a sign the code should live somewhere else.
