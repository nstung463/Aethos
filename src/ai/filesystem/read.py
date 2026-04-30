from __future__ import annotations

import base64
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.ai.filesystem.backend import FilesystemBackendAdapter
from src.ai.filesystem.pathing import WorkspacePathResolver
from src.ai.filesystem.state import ReadStateStore

DEFAULT_READ_LIMIT = 200
FAST_PATH_MAX_SIZE = 10 * 1024 * 1024
MAX_READ_SIZE_BYTES = 256 * 1024
MAX_LINES_TO_READ = 2000
PDF_MAX_PAGES_PER_READ = 20
PDF_INLINE_PAGE_THRESHOLD = 10

TEXT_BINARY_EXTENSIONS = {
    ".7z",
    ".bin",
    ".bmp",
    ".class",
    ".dll",
    ".dylib",
    ".exe",
    ".gz",
    ".ico",
    ".jar",
    ".lock",
    ".mo",
    ".mp3",
    ".mp4",
    ".o",
    ".pyc",
    ".so",
    ".svgz",
    ".tar",
    ".ttf",
    ".wav",
    ".woff",
    ".woff2",
    ".zip",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
BLOCKED_DEVICE_PATHS = {
    "/dev/zero",
    "/dev/random",
    "/dev/urandom",
    "/dev/full",
    "/dev/stdin",
    "/dev/tty",
    "/dev/console",
    "/dev/stdout",
    "/dev/stderr",
    "/dev/fd/0",
    "/dev/fd/1",
    "/dev/fd/2",
}


def read_file(
    resolver: WorkspacePathResolver,
    adapter: FilesystemBackendAdapter,
    state: ReadStateStore,
    path: str,
    offset: int = 1,
    limit: int | None = None,
    pages: str | None = None,
) -> str:
    path = resolver.sanitize_input_path(path)
    if adapter.backend is None:
        target = resolver.resolve_workspace_path(path)
        rendered = read_path(target, display_path=path, offset=offset, limit=limit, pages=pages)
        state.remember_successful_read(path, rendered, limit=limit, pages=pages, adapter=adapter)
        return rendered

    info = adapter.stat_path(path)
    if not info.exists:
        return f"Error: '{path}' does not exist."
    if info.is_dir:
        return f"Error: '{path}' is a directory. Use ls to list its contents."

    response = adapter.read_bytes(path, offset=offset, limit=limit)
    if response.error or response.content is None:
        return f"Error reading '{path}': {response.error or 'no content returned'}."
    rendered = render_bytes_read(
        response.content,
        display_path=path,
        suffix=Path(path).suffix.lower(),
        offset=offset,
        limit=limit,
        pages=pages,
    )
    state.remember_successful_read(path, rendered, limit=limit, pages=pages, adapter=adapter, content=response.content)
    return rendered


def read_media_file(
    resolver: WorkspacePathResolver,
    adapter: FilesystemBackendAdapter,
    path: str,
    *,
    pages: str | None = None,
    allow_image_blocks: bool = False,
    allow_file_blocks: bool = False,
) -> str | list[dict[str, Any]]:
    path = resolver.sanitize_input_path(path)
    if adapter.backend is None:
        target = resolver.resolve_workspace_path(path)
        return read_media_path(
            target,
            display_path=path,
            pages=pages,
            allow_image_blocks=allow_image_blocks,
            allow_file_blocks=allow_file_blocks,
        )

    info = adapter.stat_path(path)
    if not info.exists:
        return f"Error: '{path}' does not exist."
    if info.is_dir:
        return f"Error: '{path}' is a directory. Use ls to list its contents."

    response = adapter.read_bytes(path)
    if response.error or response.content is None:
        return f"Error reading '{path}': {response.error or 'no content returned'}."
    return render_media_bytes_read(
        response.content,
        display_path=path,
        suffix=Path(path).suffix.lower(),
        pages=pages,
        allow_image_blocks=allow_image_blocks,
        allow_file_blocks=allow_file_blocks,
    )


def read_path(
    path: Path,
    *,
    display_path: str,
    offset: int = 1,
    limit: int | None = None,
    pages: str | None = None,
) -> str:
    if not path.exists():
        return f"Error: '{display_path}' does not exist."
    if path.is_dir():
        return f"Error: '{display_path}' is a directory. Use ls to list its contents."
    if is_blocked_device_path(path):
        return f"Cannot read '{display_path}': this device file would block or produce infinite output."

    suffix = path.suffix.lower()
    if suffix == ".ipynb":
        return render_notebook_read(path.read_bytes(), display_path=display_path)
    if suffix in IMAGE_EXTENSIONS:
        return render_image_read(path.read_bytes(), display_path=display_path, suffix=suffix)
    if suffix == ".pdf":
        return render_pdf_read(path, display_path=display_path, pages=pages)
    if suffix in TEXT_BINARY_EXTENSIONS:
        return (
            "This tool cannot read binary files. "
            f"The file appears to be a binary {suffix} file. "
            "Please use appropriate tools for binary file analysis."
        )

    # Guard against huge files with very long lines (not caught by the line cap).
    if limit is None and path.stat().st_size > MAX_READ_SIZE_BYTES:
        return _file_too_large_message(path.stat().st_size)
    effective_limit = limit if limit is not None else MAX_LINES_TO_READ
    return render_text_path(path, display_path=display_path, offset=offset, limit=effective_limit)


def read_media_path(
    path: Path,
    *,
    display_path: str,
    pages: str | None = None,
    allow_image_blocks: bool = False,
    allow_file_blocks: bool = False,
) -> str | list[dict[str, Any]]:
    if not path.exists():
        return f"Error: '{display_path}' does not exist."
    if path.is_dir():
        return f"Error: '{display_path}' is a directory. Use ls to list its contents."
    if is_blocked_device_path(path):
        return f"Cannot read '{display_path}': this device file would block or produce infinite output."

    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return render_image_media_read(
            path.read_bytes(),
            display_path=display_path,
            suffix=suffix,
            allow_image_blocks=allow_image_blocks,
        )
    if suffix == ".pdf":
        return render_pdf_media_read(
            path,
            display_path=display_path,
            pages=pages,
            allow_image_blocks=allow_image_blocks,
            allow_file_blocks=allow_file_blocks,
        )
    return (
        f"Unsupported media file type for '{display_path}'. "
        "Use read_file instead for text, notebook, or other non-media files."
    )


def render_bytes_read(
    content: bytes,
    *,
    display_path: str,
    suffix: str,
    offset: int = 1,
    limit: int | None = None,
    pages: str | None = None,
) -> str:
    if suffix == ".ipynb":
        return render_notebook_read(content, display_path=display_path)
    if suffix in IMAGE_EXTENSIONS:
        return render_image_read(content, display_path=display_path, suffix=suffix)
    if suffix == ".pdf":
        with tempfile.TemporaryDirectory(prefix="ethos-read-pdf-") as tmp_dir:
            temp_path = Path(tmp_dir) / f"{uuid4().hex}.pdf"
            temp_path.write_bytes(content)
            return render_pdf_read(temp_path, display_path=display_path, pages=pages)
    if suffix in TEXT_BINARY_EXTENSIONS:
        return (
            "This tool cannot read binary files. "
            f"The file appears to be a binary {suffix} file. "
            "Please use appropriate tools for binary file analysis."
        )
    if limit is None and len(content) > MAX_READ_SIZE_BYTES:
        return _file_too_large_message(len(content))
    effective_limit = limit if limit is not None else MAX_LINES_TO_READ
    return render_text_bytes(content, display_path=display_path, offset=offset, limit=effective_limit)


def render_media_bytes_read(
    content: bytes,
    *,
    display_path: str,
    suffix: str,
    pages: str | None = None,
    allow_image_blocks: bool = False,
    allow_file_blocks: bool = False,
) -> str | list[dict[str, Any]]:
    if suffix in IMAGE_EXTENSIONS:
        return render_image_media_read(
            content,
            display_path=display_path,
            suffix=suffix,
            allow_image_blocks=allow_image_blocks,
        )
    if suffix == ".pdf":
        with tempfile.TemporaryDirectory(prefix="ethos-read-media-pdf-") as tmp_dir:
            temp_path = Path(tmp_dir) / f"{uuid4().hex}.pdf"
            temp_path.write_bytes(content)
            return render_pdf_media_read(
                temp_path,
                display_path=display_path,
                pages=pages,
                allow_image_blocks=allow_image_blocks,
                allow_file_blocks=allow_file_blocks,
            )
    return (
        f"Unsupported media file type for '{display_path}'. "
        "Use read_file instead for text, notebook, or other non-media files."
    )


def render_text_path(path: Path, *, display_path: str, offset: int = 1, limit: int | None = None) -> str:
    try:
        if limit is None and path.stat().st_size <= FAST_PATH_MAX_SIZE:
            return render_text_bytes(path.read_bytes(), display_path=display_path, offset=offset, limit=limit)

        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            requested_offset = max(0, offset)
            line_offset = 0 if requested_offset == 0 else requested_offset - 1
            selected: list[str] = []
            total_lines = 0
            end_line = None if limit is None else line_offset + limit

            for raw_line in handle:
                line = raw_line.rstrip("\n").rstrip("\r")
                if total_lines >= line_offset and (end_line is None or total_lines < end_line):
                    selected.append(line)
                total_lines += 1

            return _format_text_selection(
                selected,
                total_lines=total_lines,
                requested_offset=requested_offset,
                line_offset=line_offset,
                limit=limit,
            )
    except UnicodeDecodeError:
        return f"Error: '{display_path}' is not a text file (binary content)."


def render_text_bytes(content: bytes, *, display_path: str, offset: int = 1, limit: int | None = None) -> str:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return f"Error: '{display_path}' is not a text file (binary content)."

    requested_offset = max(0, offset)
    line_offset = 0 if requested_offset == 0 else requested_offset - 1
    all_lines = text.splitlines()
    total_lines = len(all_lines)
    end_line = total_lines if limit is None else min(total_lines, line_offset + limit)
    selected = all_lines[line_offset:end_line]
    return _format_text_selection(
        selected,
        total_lines=total_lines,
        requested_offset=requested_offset,
        line_offset=line_offset,
        limit=limit,
    )


def render_notebook_read(content: bytes, *, display_path: str) -> str:
    try:
        notebook = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return f"Error reading notebook: {exc}"

    cells = notebook.get("cells")
    if not isinstance(cells, list):
        return f"Error reading notebook: '{display_path}' is not a valid Jupyter notebook."

    language = (
        notebook.get("metadata", {})
        .get("language_info", {})
        .get("name", "python")
    )

    rendered_cells: list[str] = []
    for index, cell in enumerate(cells):
        if not isinstance(cell, dict):
            continue
        cell_type = str(cell.get("cell_type", "unknown"))
        cell_id = str(cell.get("id") or f"cell-{index}")
        source = _join_notebook_field(cell.get("source"))

        metadata_parts: list[str] = []
        if cell_type != "code":
            metadata_parts.append(f"<cell_type>{cell_type}</cell_type>")
        elif language != "python":
            metadata_parts.append(f"<language>{language}</language>")

        rendered = f'<cell id="{cell_id}">{"".join(metadata_parts)}{source}</cell>'
        outputs = _render_notebook_outputs(cell.get("outputs"))
        if outputs:
            rendered = rendered + "\n" + outputs
        rendered_cells.append(rendered)

    return "\n\n".join(rendered_cells) if rendered_cells else "(empty notebook)"


def render_image_read(content: bytes, *, display_path: str, suffix: str) -> str:
    media_type = detect_image_media_type(content, suffix)
    dimensions = get_image_dimensions(content, media_type)
    size_text = _format_file_size(len(content))
    parts = [f"Image file read: {display_path}", f"MIME type: {media_type}", f"Size: {size_text}"]
    if dimensions is not None:
        parts.append(f"Dimensions: {dimensions[0]}x{dimensions[1]}")
    return "\n".join(parts)


def render_image_media_read(
    content: bytes,
    *,
    display_path: str,
    suffix: str,
    allow_image_blocks: bool = False,
) -> str | list[dict[str, Any]]:
    summary = render_image_read(content, display_path=display_path, suffix=suffix)
    if not allow_image_blocks:
        return summary

    media_type = detect_image_media_type(content, suffix)
    return [
        {"type": "text", "text": summary},
        {
            "type": "image",
            "base64": base64.b64encode(content).decode("ascii"),
            "mime_type": media_type,
        },
    ]


def render_pdf_read(path: Path, *, display_path: str, pages: str | None = None) -> str:
    pdf_bytes = path.read_bytes()
    if not pdf_bytes.startswith(b"%PDF-"):
        return f"File is not a valid PDF (missing %PDF- header): {display_path}"

    if pages is not None:
        parsed = parse_pdf_page_range(pages)
        if parsed is None:
            return f'Invalid pages parameter: "{pages}". Use formats like "1-5", "3", or "10-20". Pages are 1-indexed.'
        first_page, last_page = parsed
        if last_page != float("inf") and last_page - first_page + 1 > PDF_MAX_PAGES_PER_READ:
            return (
                f'Page range "{pages}" exceeds maximum of {PDF_MAX_PAGES_PER_READ} pages per request. '
                "Please use a smaller range."
            )
        return extract_pdf_pages(path, display_path=display_path, first_page=first_page, last_page=last_page)

    page_count = get_pdf_page_count(path)
    if page_count is not None and page_count > PDF_INLINE_PAGE_THRESHOLD:
        return (
            f"This PDF has {page_count} pages, which is too many to read at once. "
            'Use the pages parameter to read specific page ranges (e.g., pages: "1-5"). '
            f"Maximum {PDF_MAX_PAGES_PER_READ} pages per request."
        )

    parts = [f"PDF file read: {display_path}", f"Size: {_format_file_size(len(pdf_bytes))}"]
    if page_count is not None:
        parts.append(f"Pages: {page_count}")
    return "\n".join(parts)


def render_pdf_media_read(
    path: Path,
    *,
    display_path: str,
    pages: str | None = None,
    allow_image_blocks: bool = False,
    allow_file_blocks: bool = False,
) -> str | list[dict[str, Any]]:
    pdf_bytes = path.read_bytes()
    if not pdf_bytes.startswith(b"%PDF-"):
        return f"File is not a valid PDF (missing %PDF- header): {display_path}"

    if pages is not None:
        parsed = parse_pdf_page_range(pages)
        if parsed is None:
            return f'Invalid pages parameter: "{pages}". Use formats like "1-5", "3", or "10-20". Pages are 1-indexed.'
        first_page, last_page = parsed
        if last_page != float("inf") and last_page - first_page + 1 > PDF_MAX_PAGES_PER_READ:
            return (
                f'Page range "{pages}" exceeds maximum of {PDF_MAX_PAGES_PER_READ} pages per request. '
                "Please use a smaller range."
            )
        extraction = extract_pdf_pages_data(
            path,
            display_path=display_path,
            first_page=first_page,
            last_page=last_page,
        )
        if isinstance(extraction, str):
            return extraction
        output_dir, images = extraction
        summary = "\n".join(
            [
                f"PDF pages extracted: {len(images)} page(s) from {display_path}",
                f"Output directory: {output_dir}",
                *(page.name for page in images),
            ]
        )
        if not allow_image_blocks:
            return summary
        blocks: list[dict[str, Any]] = [{"type": "text", "text": summary}]
        for image_path in images:
            blocks.append(
                {
                    "type": "image",
                    "base64": base64.b64encode(image_path.read_bytes()).decode("ascii"),
                    "mime_type": "image/jpeg",
                }
            )
        return blocks

    page_count = get_pdf_page_count(path)
    if page_count is not None and page_count > PDF_INLINE_PAGE_THRESHOLD:
        return (
            f"This PDF has {page_count} pages, which is too many to read at once. "
            'Use the pages parameter to read specific page ranges (e.g., pages: "1-5"). '
            f"Maximum {PDF_MAX_PAGES_PER_READ} pages per request."
        )

    parts = [f"PDF file read: {display_path}", f"Size: {_format_file_size(len(pdf_bytes))}"]
    if page_count is not None:
        parts.append(f"Pages: {page_count}")
    summary = "\n".join(parts)
    if not allow_file_blocks:
        return summary
    return [
        {"type": "text", "text": summary},
        {
            "type": "file",
            "base64": base64.b64encode(pdf_bytes).decode("ascii"),
            "mime_type": "application/pdf",
        },
    ]


def get_pdf_page_count(path: Path) -> int | None:
    try:
        result = subprocess.run(
            ["pdfinfo", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None

    if result.returncode != 0:
        return None

    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                return None
    return None


def extract_pdf_pages(
    path: Path,
    *,
    display_path: str,
    first_page: int,
    last_page: float,
) -> str:
    extraction = extract_pdf_pages_data(
        path,
        display_path=display_path,
        first_page=first_page,
        last_page=last_page,
    )
    if isinstance(extraction, str):
        return extraction
    output_dir, image_paths = extraction

    return "\n".join(
        [
            f"PDF pages extracted: {len(image_paths)} page(s) from {display_path}",
            f"Output directory: {output_dir}",
            *(page.name for page in image_paths),
        ]
    )


def extract_pdf_pages_data(
    path: Path,
    *,
    display_path: str,
    first_page: int,
    last_page: float,
) -> str | tuple[Path, list[Path]]:
    output_dir = Path(tempfile.mkdtemp(prefix="ethos-pdf-pages-"))
    prefix = output_dir / "page"
    command = ["pdftoppm", "-jpeg", "-r", "100"]
    command.extend(["-f", str(first_page)])
    if last_page != float("inf"):
        command.extend(["-l", str(int(last_page))])
    command.extend([str(path), str(prefix)])

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=120,
        )
    except FileNotFoundError:
        return (
            "pdftoppm is not installed. Install poppler-utils to enable PDF page rendering "
            f"for '{display_path}'."
        )
    except subprocess.SubprocessError as exc:
        return f"Error extracting PDF pages: {exc}"

    if result.returncode != 0:
        stderr = result.stderr.lower()
        if "password" in stderr:
            return "PDF is password-protected. Please provide an unprotected version."
        if "damaged" in stderr or "corrupt" in stderr or "invalid" in stderr:
            return "PDF file is corrupted or invalid."
        return f"pdftoppm failed: {result.stderr.strip() or result.stdout.strip()}"

    image_paths = sorted(output_dir.glob("*.jpg"))
    if not image_paths:
        return "pdftoppm produced no output pages. The PDF may be invalid."
    return output_dir, image_paths


def parse_pdf_page_range(pages: str) -> tuple[int, float] | None:
    trimmed = pages.strip()
    if not trimmed:
        return None

    if trimmed.endswith("-"):
        first = _parse_positive_int(trimmed[:-1])
        if first is None:
            return None
        return first, float("inf")

    if "-" not in trimmed:
        page = _parse_positive_int(trimmed)
        if page is None:
            return None
        return page, float(page)

    first_part, last_part = trimmed.split("-", 1)
    first = _parse_positive_int(first_part)
    last = _parse_positive_int(last_part)
    if first is None or last is None or last < first:
        return None
    return first, float(last)


def is_blocked_device_path(path: Path) -> bool:
    value = path.as_posix()
    if value in BLOCKED_DEVICE_PATHS:
        return True
    if value.startswith("/proc/") and value.endswith(("/fd/0", "/fd/1", "/fd/2")):
        return True
    return False


def detect_image_media_type(content: bytes, suffix: str) -> str:
    if len(content) >= 4 and content[:4] == b"\x89PNG":
        return "image/png"
    if len(content) >= 3 and content[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(content) >= 3 and content[:3] == b"GIF":
        return "image/gif"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"

    normalized = suffix.lstrip(".").lower() or "png"
    if normalized == "jpg":
        normalized = "jpeg"
    return f"image/{normalized}"


def get_image_dimensions(content: bytes, media_type: str) -> tuple[int, int] | None:
    try:
        if media_type == "image/png" and len(content) >= 24:
            return int.from_bytes(content[16:20], "big"), int.from_bytes(content[20:24], "big")
        if media_type == "image/gif" and len(content) >= 10:
            return int.from_bytes(content[6:8], "little"), int.from_bytes(content[8:10], "little")
        if media_type == "image/webp" and len(content) >= 30:
            if content[12:16] == b"VP8X":
                width = 1 + int.from_bytes(content[24:27], "little")
                height = 1 + int.from_bytes(content[27:30], "little")
                return width, height
        if media_type == "image/jpeg":
            return _get_jpeg_dimensions(content)
    except Exception:
        return None
    return None


def _get_jpeg_dimensions(content: bytes) -> tuple[int, int] | None:
    index = 2
    while index + 9 < len(content):
        if content[index] != 0xFF:
            index += 1
            continue
        marker = content[index + 1]
        index += 2
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > len(content):
            return None
        segment_length = int.from_bytes(content[index:index + 2], "big")
        if segment_length < 2 or index + segment_length > len(content):
            return None
        if marker in {
            0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF
        }:
            height = int.from_bytes(content[index + 3:index + 5], "big")
            width = int.from_bytes(content[index + 5:index + 7], "big")
            return width, height
        index += segment_length
    return None


def _render_notebook_outputs(outputs: Any) -> str:
    if not isinstance(outputs, list):
        return ""

    rendered: list[str] = []
    for output in outputs:
        if not isinstance(output, dict):
            continue
        output_type = str(output.get("output_type", ""))
        if output_type == "stream":
            text = _join_notebook_field(output.get("text"))
            if text:
                rendered.append(text)
        elif output_type in {"execute_result", "display_data"}:
            data = output.get("data", {})
            if isinstance(data, dict):
                text = _join_notebook_field(data.get("text/plain"))
                if text:
                    rendered.append(text)
                if isinstance(data.get("image/png"), str):
                    rendered.append("[image/png output omitted]")
                if isinstance(data.get("image/jpeg"), str):
                    rendered.append("[image/jpeg output omitted]")
        elif output_type == "error":
            ename = output.get("ename", "Error")
            evalue = output.get("evalue", "")
            traceback = output.get("traceback", [])
            traceback_text = "\n".join(traceback) if isinstance(traceback, list) else ""
            rendered.append(f"{ename}: {evalue}\n{traceback_text}".strip())
    return "\n".join(part for part in rendered if part).strip()


def _join_notebook_field(value: Any) -> str:
    if isinstance(value, list):
        return "".join(str(item) for item in value)
    if value is None:
        return ""
    return str(value)


def _format_text_selection(
    selected: list[str],
    *,
    total_lines: int,
    requested_offset: int,
    line_offset: int,
    limit: int | None,
) -> str:
    if not selected and total_lines > 0:
        return f"[File has {total_lines} lines, but offset={requested_offset} is past the end.]"
    if not selected:
        return "(empty file)"

    numbered = [f"{i + line_offset + 1:>6}\t{line}" for i, line in enumerate(selected)]
    result = "\n".join(numbered)
    if limit is not None and line_offset + len(selected) < total_lines:
        next_offset = line_offset + len(selected) + 1
        result += (
            f"\n\n[Showing lines {line_offset + 1}-{line_offset + len(selected)} of {total_lines}. "
            f"Use offset={next_offset} to read more.]"
        )
    return result


def _parse_positive_int(value: str) -> int | None:
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed >= 1 else None


def _file_too_large_message(size_in_bytes: int) -> str:
    return (
        f"File content ({_format_file_size(size_in_bytes)}) exceeds maximum allowed size "
        f"({_format_file_size(MAX_READ_SIZE_BYTES)}). Use offset and limit parameters to read "
        "specific portions of the file, or search for specific content instead of reading the whole file."
    )


def _format_file_size(size_in_bytes: int) -> str:
    if size_in_bytes < 1024:
        return f"{size_in_bytes} B"
    if size_in_bytes < 1024 * 1024:
        return f"{size_in_bytes / 1024:.1f} KB"
    return f"{size_in_bytes / (1024 * 1024):.1f} MB"
