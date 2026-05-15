from __future__ import annotations

DESCRIPTION = "Read a PDF or image file from the local filesystem."


def render_read_media_tool_description() -> str:
    return (
        f"{DESCRIPTION}\n"
        "Use this tool for media files inside the current workspace when the model should inspect the media itself.\n"
        "Supported formats in this phase are PNG, JPG, JPEG, GIF, and WEBP.\n"
        "Paths are relative to the workspace root.\n"
        "- This tool is only for local workspace files, not http:// or https:// URLs.\n"
        "- Prefer this tool for screenshots, images, and PDFs when visual inspection or multimodal/file blocks would help.\n"
        "- If the PDF or image is hosted on the web, use web_fetch instead of this tool.\n"
        "- When the active model supports multimodal tool results, this tool may return image or file blocks.\n"
        "- Otherwise it falls back to a textual summary instead of failing.\n"
        "- Use read_file instead for code, text, notebooks, or when you only need extracted text from a PDF.\n"
        "- This tool can only read files, not directories."
    )


__all__ = ["DESCRIPTION", "render_read_media_tool_description"]
