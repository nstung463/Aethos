from __future__ import annotations

from src.ai.filesystem.read import MAX_LINES_TO_READ

DESCRIPTION = "Read a file from the local filesystem."

LINE_FORMAT_INSTRUCTION = (
    "- Results are returned using cat -n format, with line numbers starting at 1."
)

OFFSET_INSTRUCTION_DEFAULT = (
    "- You can optionally specify a line offset and limit (especially handy for long files), "
    "but it's recommended to read the whole file by not providing these parameters."
)

OFFSET_INSTRUCTION_TARGETED = (
    "- When you already know which part of the file you need, only read that part. "
    "This can be important for larger files."
)


def render_read_tool_description() -> str:
    return (
        f"{DESCRIPTION}\n"
        "You can access files inside the current workspace directly by using this tool.\n"
        "Use this tool first for text-like files and for reading file contents as text.\n"
        "It is okay to read a file that does not exist; an error will be returned.\n\n"
        "Usage:\n"
        "- Paths are relative to the workspace root.\n"
        f"- By default, it reads up to {MAX_LINES_TO_READ} lines starting from the beginning of the file.\n"
        f"{OFFSET_INSTRUCTION_DEFAULT}\n"
        f"{OFFSET_INSTRUCTION_TARGETED}\n"
        f"{LINE_FORMAT_INSTRUCTION}\n"
        "- Prefer this tool for code, text, JSON, Markdown, logs, notebooks, and PDFs when you want extracted text or a textual summary.\n"
        "- This tool can read common image files (for example PNG, JPG, GIF, and WEBP). "
        "Image reads here return structured textual metadata rather than visual blocks.\n"
        "- This tool can read PDF files (.pdf). For large PDFs (more than 10 pages), you must provide the pages "
        'parameter to read specific page ranges (for example, pages: "1-5"). Maximum 20 pages per request.\n'
        "- This tool can read Jupyter notebooks (.ipynb files) and returns cells with their outputs in a textual rendering.\n"
        "- If you need the model to inspect an image, screenshot, or PDF as media content instead of text, use read_media_file.\n"
        "- This tool can only read files, not directories. To inspect a directory, use the ls tool.\n"
        "- If you read a file that exists but has empty contents, the result will indicate that the file is empty."
    )


__all__ = [
    "DESCRIPTION",
    "LINE_FORMAT_INSTRUCTION",
    "MAX_LINES_TO_READ",
    "OFFSET_INSTRUCTION_DEFAULT",
    "OFFSET_INSTRUCTION_TARGETED",
    "render_read_tool_description",
]
