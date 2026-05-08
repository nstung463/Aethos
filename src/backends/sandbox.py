"""Command-backed backend base that derives file operations from shell primitives.

Concrete subclasses only need to implement:
  - execute(command, timeout)
  - upload_files([(path, bytes)])
  - download_files([path])
  - id property

All other operations (ls, read, write, edit, glob, grep) are implemented
here using shell commands run via execute().
"""

from __future__ import annotations

import base64
import json
import logging
import os
import shlex
from abc import ABC, abstractmethod
from typing import Final

from src.backends.protocol import (
    EditResult,
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
    LsEntry,
    LsResult,
    PathInfo,
    ReadResult,
    SandboxProtocol,
    WriteResult,
)

logger = logging.getLogger(__name__)

_EDIT_INLINE_MAX_BYTES: Final = 50_000


# ── Shell script templates ─────────────────────────────────────────────────────

_LS_CMD = """python3 -c "
import os, json, base64
path = base64.b64decode('{path_b64}').decode()
try:
    with os.scandir(path) as it:
        for e in it:
            print(json.dumps({{'path': os.path.join(path, e.name), 'is_dir': e.is_dir(follow_symlinks=False)}}))
except (FileNotFoundError, PermissionError):
    pass
" 2>/dev/null"""

_READ_CMD = """python3 -c "
import os, sys, base64, json
path = base64.b64decode('{path_b64}').decode()
offset, limit = {offset}, {limit}
if not os.path.isfile(path):
    print(json.dumps({{'error': 'file_not_found'}})); sys.exit(0)
if os.path.getsize(path) == 0:
    print(json.dumps({{'content': '(empty file)'}})); sys.exit(0)
try:
    lines = open(path, encoding='utf-8').readlines()
    selected = lines[offset:offset+limit]
    numbered = [f'{{i+offset+1:>6}}\t{{l.rstrip()}}' for i, l in enumerate(selected)]
    text = '\n'.join(numbered)
    if offset + limit < len(lines):
        text += f'\n\n[Showing lines {{offset+1}}–{{offset+len(selected)}} of {{len(lines)}}. Use offset={{offset+limit}} to read more.]'
    print(json.dumps({{'content': text}}))
except UnicodeDecodeError:
    import base64 as b64
    raw = open(path, 'rb').read()
    print(json.dumps({{'content': '[binary file]', 'encoding': 'base64', 'data': b64.b64encode(raw).decode()}}))
" 2>&1"""

_WRITE_CHECK_CMD = """python3 -c "
import os, sys, base64
path = base64.b64decode('{path_b64}').decode()
os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
" 2>&1"""

_EDIT_INLINE_CMD = """python3 -c "
import sys, os, base64, json
payload = json.loads(base64.b64decode(sys.stdin.read().strip()).decode())
path, old, new, ra = payload['path'], payload['old'], payload['new'], payload.get('replace_all', False)
if not os.path.isfile(path):
    print(json.dumps({{'error': 'file_not_found'}})); sys.exit(0)
try:
    text = open(path, encoding='utf-8').read()
except UnicodeDecodeError:
    print(json.dumps({{'error': 'not_a_text_file'}})); sys.exit(0)
count = text.count(old)
if count == 0:
    print(json.dumps({{'error': 'string_not_found'}})); sys.exit(0)
if count > 1 and not ra:
    print(json.dumps({{'error': 'multiple_occurrences', 'count': count}})); sys.exit(0)
result = text.replace(old, new) if ra else text.replace(old, new, 1)
open(path, 'w', encoding='utf-8').write(result)
print(json.dumps({{'count': count}}))
" 2>&1 <<'__AETHOS_EDIT_EOF__'
{payload_b64}
__AETHOS_EDIT_EOF__
"""

_GLOB_CMD = """python3 -c "
import glob, os, json, base64
path = base64.b64decode('{path_b64}').decode()
pattern = base64.b64decode('{pattern_b64}').decode()
os.chdir(path)
for m in sorted(glob.glob(pattern, recursive=True)):
    print(json.dumps({{'path': m, 'is_dir': os.path.isdir(m)}}))
" 2>&1"""

_GREP_CMD = "grep -rHnF {glob_flag} -e {pattern} {path} 2>/dev/null || true"

_STAT_CMD = """python3 -c "
import os, json, base64
path = base64.b64decode('{path_b64}').decode()
exists = os.path.exists(path)
print(json.dumps({{
    'path': path,
    'exists': exists,
    'is_file': os.path.isfile(path),
    'is_dir': os.path.isdir(path),
    'size': (os.path.getsize(path) if exists and os.path.isfile(path) else None),
}}))
" 2>&1"""

_WALK_CMD = """python3 -c "
import os, json, base64
path = base64.b64decode('{path_b64}').decode()
if os.path.isfile(path):
    print(json.dumps({{'path': path, 'is_dir': False}}))
elif os.path.isdir(path):
    for root, dirs, files in os.walk(path):
        for d in sorted(dirs):
            print(json.dumps({{'path': os.path.join(root, d), 'is_dir': True}}))
        for f in sorted(files):
            print(json.dumps({{'path': os.path.join(root, f), 'is_dir': False}}))
" 2>&1"""

_READ_BYTES_CMD = """python3 -c "
import os, sys, json, base64
path = base64.b64decode('{path_b64}').decode()
if not os.path.isfile(path):
    print(json.dumps({{'error': 'file_not_found'}})); sys.exit(0)
raw = open(path, 'rb').read()
print(json.dumps({{'data': base64.b64encode(raw).decode()}}))
" 2>&1"""

_WRITE_BYTES_CMD = """python3 -c "
import os, base64
path = base64.b64decode('{path_b64}').decode()
data = base64.b64decode('{data_b64}')
os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
open(path, 'wb').write(data)
" 2>&1"""


# ── Base class ─────────────────────────────────────────────────────────────────

class CommandBackedBackend(ABC):
    """Backend base for environments that derive filesystem ops from shell primitives."""

    # ── Abstract primitives ────────────────────────────────────────────────────

    @property
    @abstractmethod
    def id(self) -> str: ...

    @property
    @abstractmethod
    def supported_shells(self) -> set[str]: ...

    @abstractmethod
    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse: ...

    @abstractmethod
    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]: ...

    @abstractmethod
    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]: ...

    def read_bytes(self, path: str) -> FileDownloadResponse:
        path_b64 = base64.b64encode(path.encode()).decode()
        result = self.execute(_READ_BYTES_CMD.format(path_b64=path_b64))
        try:
            data = json.loads(result.output.strip())
        except json.JSONDecodeError:
            return FileDownloadResponse(path=path, error=f"unexpected_response: {result.output[:200]}")
        if "error" in data:
            return FileDownloadResponse(path=path, error=str(data["error"]))
        return FileDownloadResponse(path=path, content=base64.b64decode(data["data"]))

    def write_bytes(self, path: str, content: bytes) -> FileUploadResponse:
        path_b64 = base64.b64encode(path.encode()).decode()
        data_b64 = base64.b64encode(content).decode()
        result = self.execute(_WRITE_BYTES_CMD.format(path_b64=path_b64, data_b64=data_b64))
        if result.exit_code != 0:
            return FileUploadResponse(path=path, error=result.output.strip() or "write_failed")
        return FileUploadResponse(path=path)

    def stat_path(self, path: str) -> PathInfo:
        path_b64 = base64.b64encode(path.encode()).decode()
        result = self.execute(_STAT_CMD.format(path_b64=path_b64))
        try:
            data = json.loads(result.output.strip())
        except json.JSONDecodeError:
            return PathInfo(path=path, exists=False, is_file=False, is_dir=False)
        return PathInfo(
            path=str(data.get("path", path)),
            exists=bool(data.get("exists")),
            is_file=bool(data.get("is_file")),
            is_dir=bool(data.get("is_dir")),
            size=data.get("size"),
        )

    def list_dir(self, path: str) -> LsResult:
        return self.ls(path)

    def walk(self, path: str) -> list[LsEntry]:
        path_b64 = base64.b64encode(path.encode()).decode()
        result = self.execute(_WALK_CMD.format(path_b64=path_b64))
        entries: list[LsEntry] = []
        for line in result.output.strip().splitlines():
            try:
                data = json.loads(line)
                entries.append(LsEntry(path=data["path"], is_dir=data["is_dir"]))
            except (json.JSONDecodeError, KeyError):
                continue
        return entries

    # ── Derived file operations ────────────────────────────────────────────────

    def ls(self, path: str) -> LsResult:
        path_b64 = base64.b64encode(path.encode()).decode()
        result = self.execute(_LS_CMD.format(path_b64=path_b64))
        entries = []
        for line in result.output.strip().splitlines():
            try:
                d = json.loads(line)
                entries.append(LsEntry(path=d["path"], is_dir=d["is_dir"]))
            except (json.JSONDecodeError, KeyError):
                continue
        return LsResult(entries=entries)

    def read(self, file_path: str, offset: int = 0, limit: int = 200) -> ReadResult:
        path_b64 = base64.b64encode(file_path.encode()).decode()
        cmd = _READ_CMD.format(path_b64=path_b64, offset=int(offset), limit=int(limit))
        result = self.execute(cmd)
        try:
            data = json.loads(result.output.strip())
        except json.JSONDecodeError:
            return ReadResult(error=f"Unexpected response: {result.output[:200]}")
        if "error" in data:
            return ReadResult(error=f"'{file_path}': {data['error']}")
        return ReadResult(content=data.get("content", ""))

    def write(self, file_path: str, content: str) -> WriteResult:
        path_b64 = base64.b64encode(file_path.encode()).decode()
        result = self.execute(_WRITE_CHECK_CMD.format(path_b64=path_b64))
        if result.exit_code != 0:
            return WriteResult(error=result.output.strip() or f"Failed to prepare '{file_path}'")
        responses = self.upload_files([(file_path, content.encode("utf-8"))])
        if not responses or responses[0].error:
            error = responses[0].error if responses else "no response"
            return WriteResult(error=f"Failed to write '{file_path}': {error}")
        return WriteResult(path=file_path)

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> EditResult:
        payload_size = len(old_string.encode()) + len(new_string.encode())
        if payload_size <= _EDIT_INLINE_MAX_BYTES:
            return self._edit_inline(file_path, old_string, new_string, replace_all)
        return self._edit_via_upload(file_path, old_string, new_string, replace_all)

    def _edit_inline(self, file_path: str, old: str, new: str, replace_all: bool) -> EditResult:
        payload = json.dumps({"path": file_path, "old": old, "new": new, "replace_all": replace_all})
        payload_b64 = base64.b64encode(payload.encode()).decode()
        result = self.execute(_EDIT_INLINE_CMD.format(payload_b64=payload_b64))
        try:
            data = json.loads(result.output.strip())
        except json.JSONDecodeError:
            return EditResult(error=f"Unexpected response editing '{file_path}': {result.output[:200]}")
        if "error" in data:
            return _map_edit_error(data["error"], file_path, old, data.get("count"))
        return EditResult(path=file_path, occurrences=data.get("count", 1))

    def _edit_via_upload(self, file_path: str, old: str, new: str, replace_all: bool) -> EditResult:
        uid = base64.b32encode(os.urandom(10)).decode().lower()
        old_tmp = f"/tmp/.aethos_edit_{uid}_old"
        new_tmp = f"/tmp/.aethos_edit_{uid}_new"
        self.upload_files([(old_tmp, old.encode()), (new_tmp, new.encode())])

        old_b64 = base64.b64encode(old_tmp.encode()).decode()
        new_b64 = base64.b64encode(new_tmp.encode()).decode()
        target_b64 = base64.b64encode(file_path.encode()).decode()

        cmd = f"""python3 -c "
import os,json,base64
old=open(base64.b64decode('{old_b64}').decode()).read()
new=open(base64.b64decode('{new_b64}').decode()).read()
target=base64.b64decode('{target_b64}').decode()
[os.remove(p) for p in [base64.b64decode('{old_b64}').decode(),base64.b64decode('{new_b64}').decode()] if os.path.exists(p)]
text=open(target,encoding='utf-8').read()
count=text.count(old)
if count==0: print(json.dumps({{'error':'string_not_found'}}))
elif count>1 and not {replace_all}: print(json.dumps({{'error':'multiple_occurrences','count':count}}))
else:
    open(target,'w',encoding='utf-8').write(text.replace(old,new) if {replace_all} else text.replace(old,new,1))
    print(json.dumps({{'count':count}}))
" 2>&1"""
        result = self.execute(cmd)
        try:
            data = json.loads(result.output.strip())
        except json.JSONDecodeError:
            return EditResult(error=f"Unexpected response: {result.output[:200]}")
        if "error" in data:
            return _map_edit_error(data["error"], file_path, old, data.get("count"))
        return EditResult(path=file_path, occurrences=data.get("count", 1))

    def glob(self, pattern: str, path: str = "/") -> list[str]:
        path_b64 = base64.b64encode(path.encode()).decode()
        pattern_b64 = base64.b64encode(pattern.encode()).decode()
        result = self.execute(_GLOB_CMD.format(path_b64=path_b64, pattern_b64=pattern_b64))
        paths = []
        for line in result.output.strip().splitlines():
            try:
                paths.append(json.loads(line)["path"])
            except (json.JSONDecodeError, KeyError):
                continue
        return paths

    def grep(self, pattern: str, path: str = ".", glob: str | None = None) -> list[dict]:
        glob_flag = f"--include={shlex.quote(glob)}" if glob else ""
        cmd = _GREP_CMD.format(
            glob_flag=glob_flag,
            pattern=shlex.quote(pattern),
            path=shlex.quote(path),
        )
        result = self.execute(cmd)
        matches = []
        for line in result.output.strip().splitlines():
            parts = line.split(":", 2)
            if len(parts) >= 3:  # noqa: PLR2004
                try:
                    matches.append({"path": parts[0], "line": int(parts[1]), "text": parts[2]})
                except ValueError:
                    continue
        return matches


def _map_edit_error(error: str, file_path: str, old_string: str, count: int | None = None) -> EditResult:
    if error == "file_not_found":
        return EditResult(error=f"File '{file_path}' not found. Read it before editing.")
    if error == "string_not_found":
        return EditResult(error=f"old_string not found in '{file_path}'. Check exact whitespace and indentation.")
    if error == "multiple_occurrences":
        n = count or "?"
        return EditResult(error=f"old_string appears {n} times in '{file_path}'. Add more context or use replace_all=True.")
    if error == "not_a_text_file":
        return EditResult(error=f"'{file_path}' is not a text file.")
    return EditResult(error=f"Error editing '{file_path}': {error}")


# Backward-compatible alias while call sites migrate to the clearer name.
BaseSandbox = CommandBackedBackend
