"""Migration utilities for checkpoint format conversion."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from src.logger import get_logger

logger = get_logger(__name__)


async def migrate_sqlite_to_jsonl(sqlite_db_path: Path, output_dir: Path) -> None:
    """Migrate checkpoints from SQLite to JSONL format.

    Args:
        sqlite_db_path: Path to SQLite checkpoints.db
        output_dir: Target directory for JSONL output
    """
    if not sqlite_db_path.exists():
        logger.info(f"SQLite database not found at {sqlite_db_path}, skipping migration")
        return

    logger.info(f"Starting migration from SQLite ({sqlite_db_path}) to JSONL ({output_dir})")

    conn = sqlite3.connect(sqlite_db_path)
    cursor = conn.cursor()

    # Get all threads
    cursor.execute("SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id;")
    threads = [row[0] for row in cursor.fetchall()]
    logger.info(f"Found {len(threads)} threads to migrate")

    checkpoints_dir = output_dir / "checkpoints"
    checkpoints_dir.mkdir(parents=True, exist_ok=True)

    migrated_count = 0
    for thread_id in threads:
        # Get all checkpoints for this thread, ordered by checkpoint_id
        cursor.execute(
            """
            SELECT checkpoint_id, checkpoint, metadata
            FROM checkpoints
            WHERE thread_id = ?
            ORDER BY checkpoint_id
            """,
            (thread_id,),
        )

        checkpoints = cursor.fetchall()
        if not checkpoints:
            continue

        thread_dir = checkpoints_dir / thread_id
        thread_dir.mkdir(exist_ok=True)

        messages_file = thread_dir / "messages.jsonl"
        checkpoints_file = thread_dir / "checkpoints.jsonl"

        # Process each checkpoint
        for checkpoint_id, checkpoint_blob, metadata_blob in checkpoints:
            try:
                # Deserialize checkpoint state
                state = json.loads(checkpoint_blob) if isinstance(checkpoint_blob, str) else checkpoint_blob

                # Deserialize metadata
                metadata = {}
                if metadata_blob:
                    try:
                        metadata = json.loads(metadata_blob) if isinstance(metadata_blob, str) else metadata_blob
                    except (json.JSONDecodeError, TypeError):
                        logger.debug(f"Could not deserialize metadata for {thread_id}/{checkpoint_id}")

                # Extract and save messages
                messages = state.get("messages", [])
                for msg in messages:
                    if isinstance(msg, dict):
                        entry = {
                            "timestamp": metadata.get("timestamp", ""),
                            "message": msg,
                        }
                        with open(messages_file, "a", encoding="utf-8") as f:
                            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

                # Save checkpoint metadata
                checkpoint_entry = {
                    "checkpoint_id": checkpoint_id,
                    "timestamp": metadata.get("timestamp", ""),
                    "thread_id": thread_id,
                    "metadata": metadata,
                    "message_count": len(messages),
                }
                with open(checkpoints_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(checkpoint_entry, ensure_ascii=False) + "\n")

                migrated_count += 1

            except Exception as e:
                logger.warning(f"Failed to migrate checkpoint {thread_id}/{checkpoint_id}: {e}")

        logger.debug(f"Migrated thread {thread_id}: {len(checkpoints)} checkpoints")

    conn.close()
    logger.info(f"Migration complete: {migrated_count} checkpoints migrated to JSONL")

    # Backup original database
    backup_path = sqlite_db_path.parent / f"{sqlite_db_path.name}.backup"
    if not backup_path.exists():
        import shutil

        shutil.copy2(sqlite_db_path, backup_path)
        logger.info(f"Original database backed up to {backup_path}")
