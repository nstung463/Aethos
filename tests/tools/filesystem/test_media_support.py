from __future__ import annotations

from src.ai.tools.filesystem.media_support import resolve_media_block_support


def test_resolve_media_block_support_enables_anthropic_claude() -> None:
    support = resolve_media_block_support("anthropic", "claude-sonnet-4-5")
    assert support.image_blocks is True
    assert support.file_blocks is True


def test_resolve_media_block_support_enables_openai() -> None:
    support = resolve_media_block_support("openai", "gpt-4.1-mini")
    assert support.image_blocks is True
    assert support.file_blocks is True


def test_resolve_media_block_support_enables_azure_openai() -> None:
    support = resolve_media_block_support("azure_openai", "gpt-4.1")
    assert support.image_blocks is True
    assert support.file_blocks is True


def test_resolve_media_block_support_keeps_google_disabled_for_now() -> None:
    support = resolve_media_block_support("google_genai", "gemini-2.5-pro")
    assert support.image_blocks is False
    assert support.file_blocks is False


def test_resolve_media_block_support_keeps_openai_compatible_disabled() -> None:
    support = resolve_media_block_support("openrouter", "openai/gpt-4o")
    assert support.image_blocks is False
    assert support.file_blocks is False
