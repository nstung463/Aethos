from __future__ import annotations

import fnmatch
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from src.ai.filesystem.backend import FilesystemBackendAdapter
from src.ai.filesystem.pathing import WorkspacePathResolver
from src.backends.protocol import LsEntry

MAX_MATCHES = 500


@dataclass(frozen=True)
class GlobSearchResult:
    matches: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class GrepSearchResult:
    matches: list[dict[str, object]] = field(default_factory=list)
    error: str | None = None


def format_glob_matches(pattern: str, path: str, matches: list[str]) -> str:
    if not matches:
        return f"No files matched '{pattern}' in '{path}'."
    if len(matches) <= MAX_MATCHES:
        return "\n".join(matches)
    visible = "\n".join(matches[:MAX_MATCHES])
    return f"{visible}\n\n[Truncated: showing {MAX_MATCHES} of {len(matches)} matches]"


def format_grep_matches(pattern: str, output_mode: str, matches: list[dict[str, object]]) -> str:
    if not matches:
        return f"No matches found for '{pattern}'."
    if output_mode == "files_with_matches":
        return "\n".join(dict.fromkeys(str(match["path"]) for match in matches))
    if output_mode == "count":
        counts = Counter(str(match["path"]) for match in matches)
        return "\n".join(f"{path}: {count}" for path, count in counts.items())

    visible = [f"{match['path']}:{match['line']}: {match['text']}" for match in matches[:MAX_MATCHES]]
    result = "\n".join(visible)
    if len(matches) > MAX_MATCHES:
        result += f"\n\n[Truncated at {MAX_MATCHES} matches]"
    return result


def list_path(resolver: WorkspacePathResolver, adapter: FilesystemBackendAdapter, path: str = ".") -> str:
    path = resolver.sanitize_input_path(path)
    info = adapter.stat_path(path)
    if not info.exists:
        return f"Error: '{path}' does not exist."
    if info.is_file:
        return resolver.normalize_path(path)

    result = adapter.list_dir(path)
    if result.error:
        return f"Error: {result.error}"
    if not result.entries:
        return "(empty directory)"

    lines = [
        f"{resolver.normalize_path(entry.path)}{'/' if entry.is_dir else ''}"
        for entry in sorted(result.entries, key=lambda entry: (not entry.is_dir, entry.path))
    ]
    return "\n".join(lines)


def glob_search(
    resolver: WorkspacePathResolver,
    adapter: FilesystemBackendAdapter,
    pattern: str,
    path: str = ".",
) -> GlobSearchResult:
    path = resolver.sanitize_input_path(path)
    info = adapter.stat_path(path)
    if not info.exists:
        return GlobSearchResult(error=f"Error: '{path}' does not exist.")

    if info.is_file:
        candidates = [resolver.normalize_path(path)]
    else:
        candidates = [resolver.normalize_path(entry.path) for entry in adapter.walk(path)]

    matches = [
        candidate
        for candidate in candidates
        if _matches_glob(pattern, resolver.relative_to_base(candidate, path))
    ]
    return GlobSearchResult(matches=sorted(matches))


def grep_search(
    resolver: WorkspacePathResolver,
    adapter: FilesystemBackendAdapter,
    pattern: str,
    path: str = ".",
    glob: str | None = None,
) -> GrepSearchResult:
    path = resolver.sanitize_input_path(path)
    info = adapter.stat_path(path)
    if not info.exists:
        return GrepSearchResult(error=f"Error: '{path}' does not exist.")

    try:
        regex = re.compile(pattern)
    except re.error as exc:
        return GrepSearchResult(error=f"Error: invalid regex '{pattern}': {exc}")

    entries: list[LsEntry]
    if info.is_file:
        entries = [LsEntry(path=path, is_dir=False)]
    else:
        entries = [entry for entry in adapter.walk(path) if not entry.is_dir]

    matches: list[dict[str, object]] = []
    for entry in entries:
        display_path = resolver.normalize_path(entry.path)
        if glob and not fnmatch.fnmatch(PurePosixPath(display_path).name, glob):
            continue

        response = adapter.read_bytes(entry.path)
        if response.error or response.content is None:
            continue
        try:
            lines = response.content.decode("utf-8").splitlines()
        except UnicodeDecodeError:
            continue

        for line_number, line in enumerate(lines, start=1):
            if regex.search(line):
                matches.append({"path": display_path, "line": line_number, "text": line})

    return GrepSearchResult(matches=matches)


def _matches_glob(pattern: str, relative_path: str) -> bool:
    if relative_path == ".":
        return False
    pure = PurePosixPath(relative_path)
    if pure.match(pattern):
        return True
    if pattern.startswith("**/"):
        return pure.match(pattern[3:])
    return False
