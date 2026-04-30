from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MediaBlockSupport:
    image_blocks: bool = False
    file_blocks: bool = False


def resolve_media_block_support(provider: str, model_name: str) -> MediaBlockSupport:
    normalized_provider = provider.strip().lower()
    normalized_model = model_name.strip().lower()

    if normalized_provider == "anthropic" and "claude" in normalized_model:
        return MediaBlockSupport(image_blocks=True, file_blocks=True)

    if normalized_provider in {"openai", "azure_openai"}:
        return MediaBlockSupport(image_blocks=True, file_blocks=True)

    return MediaBlockSupport()


__all__ = ["MediaBlockSupport", "resolve_media_block_support"]
