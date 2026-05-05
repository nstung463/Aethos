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

    # OpenRouter uses "provider/model" naming — detect from underlying provider prefix
    if normalized_provider == "openrouter":
        if normalized_model.startswith("anthropic/"):
            return MediaBlockSupport(image_blocks=True, file_blocks=True)
        if normalized_model.startswith(("openai/gpt-4", "openai/o1", "openai/o3", "openai/o4")):
            return MediaBlockSupport(image_blocks=True, file_blocks=True)
        if normalized_model.startswith("google/gemini"):
            return MediaBlockSupport(image_blocks=True, file_blocks=False)
        return MediaBlockSupport()

    return MediaBlockSupport()


__all__ = ["MediaBlockSupport", "resolve_media_block_support"]
