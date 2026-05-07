# Message Tracking & History Management Guide

## Overview

Fixed the message persistence system to properly track conversation history and distinguish between new messages and resumed messages.

## Key Improvements

### 1. **Preserved Message Metadata**
Previously, only `message` objects were saved. Now the full entry is preserved:

```json
{
  "uuid": "msg-uuid-1",              // Unique identifier
  "parentUuid": "msg-uuid-0",        // Parent message (forms chain)
  "type": "user|assistant|system",   // Message role
  "message": {...},                  // Actual message content
  "timestamp": "2026-04-22T...",    // When message was created
  "sessionId": "thread_id"           // Thread identifier
}
```

### 2. **Message Request Tracking**
New system distinguishes between:
- **Current Request Messages**: Messages sent in the current API call
- **Resumed Messages**: Messages loaded from history
- **System Injected**: Messages added by the system (tool results, etc)

#### How it works:
```python
# In chat request
tracker = create_request_tracker(
    thread_id="thread-123",
    incoming_messages=[...],
    is_resume=False  # True if resuming
)

# Tracker stores which message indices are from this request
tracker.current_request_markers = {0, 1, 2}  # Indices of current messages
```

### 3. **Enhanced Checkpoint Metadata**
Checkpoint metadata now includes:
```json
{
  "checkpoint_id": "ckpt-uuid",
  "timestamp": "2026-04-22T...",
  "thread_id": "thread-123",
  "metadata": {
    "message_request_tracker": {
      "thread_id": "thread-123",
      "incoming_message_count": 3,
      "current_request_message_indices": [0, 1, 2]
    },
    "is_resume": false
  },
  "message_count": 5
}
```

## New APIs

### AsyncJsonlCheckpointSaver Methods

#### 1. `get_full_message_entries(config)`
Get complete message entries with all metadata.

```python
# Get full entries including uuid, parentUuid, timestamp
entries = await checkpointer.get_full_message_entries(config)

for entry in entries:
    print(f"UUID: {entry['uuid']}")
    print(f"Parent: {entry['parentUuid']}")
    print(f"Type: {entry['type']}")
    print(f"Content: {entry['message']}")
```

#### 2. `get_request_messages_only(config)`
Get only messages from current request (not resumed).

```python
# Useful to know what's new in this request
current_msgs = await checkpointer.get_request_messages_only(config)
print(f"Added {len(current_msgs)} new messages in this request")
```

### MessageHistoryAnalyzer

Reconstruct conversation tree and validate message chains.

```python
from src.app.services.message_history_analyzer import MessageHistoryAnalyzer

# Get full entries
entries = await checkpointer.get_full_message_entries(config)
analyzer = MessageHistoryAnalyzer(entries)

# Get chain from any message (following parentUuid)
chain = analyzer.get_message_chain(uuid="msg-uuid-5")

# Get conversation summary
summary = analyzer.get_conversation_summary()
# {
#   "total_messages": 10,
#   "first_message_uuid": "msg-uuid-0",
#   "last_message_uuid": "msg-uuid-9",
#   "message_types": {"user": 5, "assistant": 5},
#   "timestamp_range": {"first": "...", "last": "..."}
# }

# Validate integrity
issues = analyzer.validate_chain_integrity()
if issues:
    print(f"Found issues: {issues}")
```

## File Structure

### messages.jsonl
```
~/.ethos/projects/<project_key>/checkpoints/thread-123/messages.jsonl

Each line is a complete entry:
{"uuid": "...", "parentUuid": "...", "type": "user", "message": {...}, "timestamp": "...", "sessionId": "..."}
{"uuid": "...", "parentUuid": "...", "type": "assistant", "message": {...}, "timestamp": "...", "sessionId": "..."}
```

### checkpoint_state.jsonl
```
~/.ethos/projects/<project_key>/checkpoints/thread-123/checkpoint_state.jsonl

Each line is a checkpoint:
{"checkpoint_id": "...", "timestamp": "...", "thread_id": "...", "metadata": {...}, "message_count": 10}
```

### thread metadata
```
~/.ethos/projects/<project_key>/threads/<user_id>/<thread_id>/meta.json
```

This file carries the thread runtime state used to reconcile stuck or interrupted runs:
- `status`
- `active_run_id`
- `run_started_at`
- `last_stop_run_id`
- `last_stop_reason`
- `last_interrupted_at`

## Message Flow Diagram

```
User sends chat request
    ↓
ChatService.run_completion()
    ├─ Create MessageRequestTracker
    │  └─ Mark indices: [0, 1, 2] (current request)
    ├─ Pass config with tracker to agent
    │
    └─ Agent processes messages
        ├─ LangGraph runs
        └─ Calls checkpointer.put(config, values, metadata)
            ├─ AsyncJsonlCheckpointSaver.put()
            │  ├─ Extract tracker from config
            │  ├─ Append messages with uuid, parentUuid
            │  └─ Save checkpoint with tracker metadata
            │
            └─ Result:
                messages.jsonl: Full entries with metadata
                checkpoints.jsonl: Metadata + tracker info
```

## Resume Behavior

When resuming a conversation:

```python
# 1. User provides resume_command
request = ChatRequest(
    messages=[...],
    resume_command={"type": "resume", "node": "agent", "aid": "..."}
)

# 2. ChatService creates tracker with is_resume=True
tracker = create_request_tracker(
    thread_id="thread-123",
    incoming_messages=[...],
    is_resume=True  # ← Different!
)

# 3. Tracker marks NOTHING as current request
# (all messages are resumed, not new)

# 4. Agent resumes from interrupted state
# New outputs are appended, with parentUuid pointing to resume point
```

## Debugging & Analysis

### Check message history:
```python
# Get all messages with metadata
entries = await checkpointer.get_full_message_entries(config)
print(f"Total: {len(entries)}")
for e in entries:
    print(f"  {e['timestamp']} | {e['type']:10} | {e['uuid']}")
```

### Validate chain:
```python
analyzer = MessageHistoryAnalyzer(entries)
issues = analyzer.validate_chain_integrity()
if issues:
    print("⚠️  Issues found:")
    print(f"  Broken refs: {issues.get('broken_references')}")
    print(f"  Orphaned: {issues.get('orphaned_messages')}")
```

### Reconstruct conversation:
```python
# Trace a message back to its origin
last_uuid = entries[-1]['uuid']
chain = analyzer.get_message_chain(last_uuid)
print(f"Conversation chain ({len(chain)} messages):")
for msg in chain:
    print(f"  {msg['timestamp']} | {msg['type']:10} | {msg['message']['content'][:50]}...")
```

## Key Changes Made

1. ✅ `async_jsonl_checkpointer.py`: 
   - Now saves full message entries (uuid, parentUuid, etc)
   - Enhanced metadata in checkpoints
   - New methods: `get_full_message_entries()`, `get_request_messages_only()`

2. ✅ `chat/service.py`:
   - Integrated `MessageRequestTracker`
   - Pass tracker through config
   - Better tracking of resume operations

3. ✅ New modules:
   - `message_tracker.py`: Track which messages are from current request
   - `message_history_analyzer.py`: Reconstruct and validate message chains

## Migration Notes

- **Backward compatible**: Old checkpoints still work, just lack metadata
- **No data loss**: SQLite data was deleted, starting fresh with JSON
- **Future improvements**: Can now easily add:
  - Message editing/deletion
  - Conversation branching
  - Message importance scoring
  - Selective message compression
