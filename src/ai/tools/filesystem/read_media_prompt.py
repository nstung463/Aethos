from __future__ import annotations

DESCRIPTION = "Read a PDF or image file from the local filesystem."


def render_read_media_tool_description() -> str:
    return (
        f"{DESCRIPTION}\n"
        "Use this tool only for media files inside the current workspace.\n"
        "Supported formats in this phase are PDF, PNG, JPG, JPEG, GIF, and WEBP.\n"
        "Paths are relative to the workspace root.\n"
        "- For PDFs larger than 10 pages, you must provide the pages parameter to read a specific range.\n"
        '- Valid pages examples: "3", "1-5", "10-20". Maximum 20 PDF pages per request.\n'
        "- When the active model supports multimodal tool results, this tool may return image or file blocks.\n"
        "- Otherwise it falls back to a textual summary instead of failing.\n"
        "- If the target is not a supported media file, use read_file instead.\n"
        "- This tool can only read files, not directories."
    )


__all__ = ["DESCRIPTION", "render_read_media_tool_description"]
