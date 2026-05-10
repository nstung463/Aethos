"""Resolve Aethos runtime storage paths outside project source trees."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any

from src.app.core.settings import Settings, get_settings
from src.logger import get_logger

logger = get_logger(__name__)

MAX_PROJECT_KEY_LENGTH = 64


def _legacy_workspace_root() -> Path:
    raw = os.getenv("AETHOS_WORKSPACE_DIR") or os.getenv("AETHOS_WORKSPACE") or "./workspace"
    return Path(raw).expanduser().resolve()


def _safe_copy_tree(source: Path, target: Path) -> tuple[int, int]:
    copied = 0
    skipped = 0
    if not source.exists():
        return copied, skipped
    if source.resolve() == target.resolve():
        return copied, skipped
    for item in source.rglob("*"):
        relative = item.relative_to(source)
        destination = target / relative
        if item.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        if not item.is_file():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            skipped += 1
            continue
        shutil.copy2(item, destination)
        copied += 1
    return copied, skipped


def _safe_copy_legacy_users(source: Path, target: Path) -> tuple[int, int]:
    copied = 0
    skipped = 0
    if not source.exists():
        return copied, skipped
    if source.resolve() == target.resolve():
        return copied, skipped
    for user_dir in source.iterdir():
        if not user_dir.is_dir():
            continue
        for child_name in ("profile.json", "sessions"):
            child = user_dir / child_name
            if not child.exists():
                continue
            destination = target / user_dir.name / child_name
            if child.is_dir():
                child_copied, child_skipped = _safe_copy_tree(child, destination)
                copied += child_copied
                skipped += child_skipped
            elif child.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    skipped += 1
                    continue
                shutil.copy2(child, destination)
                copied += 1
    return copied, skipped


def sanitize_project_key(path: str | Path) -> str:
    value = str(Path(path).expanduser().resolve())
    if os.name == "nt":
        value = value.lower()
    sanitized = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")
    if not sanitized:
        sanitized = "project"
    if len(sanitized) <= MAX_PROJECT_KEY_LENGTH:
        return sanitized
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    prefix_length = max(1, MAX_PROJECT_KEY_LENGTH - len(digest) - 1)
    return f"{sanitized[:prefix_length]}-{digest}"


def find_canonical_project_root(workspace_root: str | Path) -> Path:
    root = Path(workspace_root).expanduser().resolve()
    current = root
    while True:
        if (current / ".git").exists():
            return current
        if current.parent == current:
            return root
        current = current.parent


class StoragePathsService:
    """Centralized path resolver for user/runtime data under ``~/.aethos``."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.config_home = self.settings.aethos_config_dir.expanduser().resolve()

    def user_settings_dir(self) -> Path:
        return self.config_home

    def users_dir(self) -> Path:
        if os.getenv("AETHOS_USERS_DIR"):
            return self.settings.users_dir.expanduser().resolve()
        return self.config_home / "users"

    def auth_db_path(self) -> Path:
        return self.users_dir() / "auth.db"

    def auth_migration_marker_path(self) -> Path:
        users_digest = hashlib.sha256(str(self.users_dir()).encode("utf-8")).hexdigest()[:12]
        return self.migrations_dir() / f"auth-sqlite-{users_digest}.migrated"

    def security_state_dir(self) -> Path:
        if os.getenv("AETHOS_SECURITY_STATE_DIR"):
            return self.settings.security_state_dir.expanduser().resolve()
        return self.config_home / "security"

    def project_key(self, workspace_root: str | Path | None = None) -> str:
        root = self.project_identity_root(workspace_root)
        return sanitize_project_key(root)

    def project_identity_root(self, workspace_root: str | Path | None = None) -> Path:
        root = Path(workspace_root).expanduser().resolve() if workspace_root else _legacy_workspace_root()
        return find_canonical_project_root(root)

    def projects_dir(self) -> Path:
        return self.config_home / "projects"

    def project_dir(self, workspace_root: str | Path | None = None) -> Path:
        return self.projects_dir() / self.project_key(workspace_root)

    def threads_dir(self, workspace_root: str | Path | None = None) -> Path:
        return self.project_dir(workspace_root) / "threads"

    def checkpoints_base_dir(self, workspace_root: str | Path | None = None) -> Path:
        if os.getenv("AETHOS_CHECKPOINTS_DIR"):
            return self.settings.checkpoints_dir.expanduser().resolve()
        return self.project_dir(workspace_root)

    def checkpoints_dir(self, workspace_root: str | Path | None = None) -> Path:
        return self.checkpoints_base_dir(workspace_root) / "checkpoints"

    def files_dir(self, workspace_root: str | Path | None = None) -> Path:
        if os.getenv("AETHOS_MANAGED_FILES_DIR"):
            return Path(os.getenv("AETHOS_MANAGED_FILES_DIR", "")).expanduser().resolve()
        return self.project_dir(workspace_root) / "files"

    def memory_dir(self, workspace_root: str | Path | None = None) -> Path:
        return self.project_dir(workspace_root) / "memory"

    def memory_file(self, workspace_root: str | Path | None = None) -> Path:
        return self.memory_dir(workspace_root) / "MEMORY.md"

    def integrations_dir(self, workspace_root: str | Path | None = None) -> Path:
        return self.project_dir(workspace_root) / "integrations"

    def integrations_db_path(self, workspace_root: str | Path | None = None) -> Path:
        return self.integrations_dir(workspace_root) / "integrations.db"

    def migrations_dir(self) -> Path:
        return self.config_home / "migrations"

    def project_metadata_path(self, workspace_root: str | Path | None = None) -> Path:
        return self.project_dir(workspace_root) / "project.json"

    def ensure_project_metadata(self, workspace_root: str | Path | None = None) -> dict[str, Any]:
        now = int(time.time())
        root = Path(workspace_root).expanduser().resolve() if workspace_root else _legacy_workspace_root()
        canonical_root = self.project_identity_root(root)
        path = self.project_metadata_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(metadata, dict):
                metadata = {}
        except Exception:
            metadata = {}
        metadata.setdefault("created_at", now)
        metadata["last_seen_at"] = now
        metadata["original_path"] = str(root)
        metadata["canonical_root"] = str(canonical_root)
        metadata["project_key"] = self.project_key(root)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        tmp.replace(path)
        return metadata

    def migrate_legacy_workspace(self, workspace_root: str | Path | None = None) -> None:
        legacy_root = Path(workspace_root).expanduser().resolve() if workspace_root else _legacy_workspace_root()
        marker = self.migrations_dir() / f"runtime-storage-{self.project_key(legacy_root)}.migrated"
        if marker.exists():
            return
        self.migrations_dir().mkdir(parents=True, exist_ok=True)

        migrations = [
            (legacy_root / "security", self.security_state_dir()),
            (legacy_root / "checkpoints", self.checkpoints_dir(legacy_root)),
            (legacy_root / "managed_files", self.files_dir(legacy_root)),
        ]
        summary: dict[str, Any] = {"workspace_root": str(legacy_root), "migrations": []}
        try:
            copied, skipped = _safe_copy_legacy_users(legacy_root / "users", self.users_dir())
            summary["migrations"].append(
                {
                    "source": str(legacy_root / "users"),
                    "target": str(self.users_dir()),
                    "copied": copied,
                    "skipped": skipped,
                }
            )
        except Exception as exc:
            logger.warning("Failed to migrate legacy users from %s to %s: %s", legacy_root / "users", self.users_dir(), exc)
            summary["migrations"].append(
                {
                    "source": str(legacy_root / "users"),
                    "target": str(self.users_dir()),
                    "error": str(exc),
                }
            )

        for source, target in migrations:
            try:
                copied, skipped = _safe_copy_tree(source, target)
                summary["migrations"].append(
                    {
                        "source": str(source),
                        "target": str(target),
                        "copied": copied,
                        "skipped": skipped,
                    }
                )
            except Exception as exc:
                logger.warning("Failed to migrate legacy storage from %s to %s: %s", source, target, exc)
                summary["migrations"].append(
                    {
                        "source": str(source),
                        "target": str(target),
                        "error": str(exc),
                    }
                )

        legacy_users = legacy_root / "users"
        if legacy_users.exists():
            for user_dir in legacy_users.iterdir():
                if not user_dir.is_dir():
                    continue
                source = user_dir / "threads"
                if not source.exists():
                    continue
                target = self.threads_dir(legacy_root) / user_dir.name
                try:
                    copied, skipped = _safe_copy_tree(source, target)
                    summary["migrations"].append(
                        {
                            "source": str(source),
                            "target": str(target),
                            "copied": copied,
                            "skipped": skipped,
                        }
                    )
                except Exception as exc:
                    logger.warning("Failed to migrate legacy threads from %s to %s: %s", source, target, exc)
                    summary["migrations"].append(
                        {
                            "source": str(source),
                            "target": str(target),
                            "error": str(exc),
                        }
                    )

        marker.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def get_storage_paths(workspace_root: str | Path | None = None) -> StoragePathsService:
    service = StoragePathsService()
    service.ensure_project_metadata(workspace_root)
    return service
