# Message Tracking Guide (PostgreSQL Runtime)

## Runtime Source of Truth

Message history, checkpoints, and checkpoint writes are persisted in PostgreSQL via `PostgresCheckpointSaver`.

- `thread_events`: normalized message/event stream used to rebuild thread history
- `thread_checkpoints`: LangGraph checkpoint payloads
- `thread_checkpoint_writes`: pending writes (including interrupt payloads)

File-based JSONL artifacts are legacy migration inputs and are not the runtime source of truth.

## Request Tracking Model

The chat flow tracks which incoming messages belong to the current request so resumed history is not misclassified as fresh input.

- `MessageRequestTracker` is attached to checkpoint metadata
- tracker metadata records incoming count and indices for the current request
- resume flows mark resumed context while preserving event lineage

## Event Shape

`PostgresCheckpointSaver.get_full_message_entries()` returns Claude-style entries with lineage metadata:

```json
{
  "uuid": "evt-uuid",
  "parentUuid": "evt-parent-uuid",
  "type": "user|assistant|system|interruption",
  "message": {"content": [...]},
  "timestamp": "2026-05-13T12:34:56Z",
  "sessionId": "thread-id"
}
```

Reasoning and tool events are expanded into stable event rows in order:

- thinking blocks first (when present)
- assistant text blocks
- tool use blocks
- tool result blocks

This keeps UI reconstruction deterministic for `run_steps`, permission prompts, and workspace frames.

## Debugging Checklist

When a thread looks inconsistent:

1. Check `thread_events` ordering (`seq`) for the thread.
2. Verify `parentUuid` chain continuity from `get_full_message_entries()`.
3. Check `thread_checkpoint_writes` for pending `__interrupt__` writes.
4. Confirm thread status metadata in the thread repository (`status`, `active_run_id`, stop reason fields).

## Notes

- Legacy JSONL checkpointer docs are retained only for migration context.
- New behavior and test coverage should target PostgreSQL repositories/checkpointer paths.
