"""Image provider factory with fallback support."""
import logging
import os
from collections.abc import Sequence
from typing import Any

from .base import ImageGenerationError, ImageProvider

logger = logging.getLogger(__name__)


def _get_provider_registry() -> dict[str, type[ImageProvider]]:
    """Build provider registry with lazy imports to avoid requiring all SDKs."""
    from .providers.gemini import GeminiProvider
    from .providers.grok import GrokProvider
    from .providers.openai import OpenAIProvider

    return {
        "openai": OpenAIProvider,
        "gemini": GeminiProvider,
        "grok": GrokProvider,
    }


class FallbackImageGenerator(ImageProvider):
    """Tries providers in order until one succeeds."""

    provider_name = "fallback-chain"

    def __init__(self, generators: list[ImageProvider]):
        if not generators:
            raise ValueError("FallbackImageGenerator requires at least one provider")
        self.generators = generators
        self.provider_name = f"fallback({', '.join(g.provider_name for g in generators)})"

    def generate(
        self,
        input_image_path: str,
        output_path: str,
        prompt: str,
        output_size: str = "1024x1536",
        **provider_options: Any,
    ) -> str:
        errors: list[str] = []

        for generator in self.generators:
            try:
                logger.info(f"Trying image provider: {generator.provider_name}")
                return generator.generate(
                    input_image_path, output_path, prompt, output_size, **provider_options
                )
            except ImageGenerationError as exc:
                logger.warning(f"Provider {generator.provider_name} failed: {exc}")
                errors.append(f"{generator.provider_name}: {exc}")

        raise ImageGenerationError(
            "All providers failed. " + " | ".join(errors)
        )


def _parse_fallbacks(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def create_image_generator(
    provider: str | None = None,
    *,
    fallbacks: Sequence[str] | None = None,
) -> ImageProvider:
    """Create an image generator with optional fallback chain.

    Selection precedence:
        1. Explicit `provider` arg
        2. IMAGE_PROVIDER env var
        3. Default: "openai"
    """
    registry = _get_provider_registry()

    primary = (provider or os.getenv("IMAGE_PROVIDER") or "openai").lower()
    fallback_names = list(
        fallbacks or _parse_fallbacks(os.getenv("IMAGE_PROVIDER_FALLBACKS"))
    )

    # Build ordered unique list
    ordered_names: list[str] = []
    for name in [primary, *fallback_names]:
        if name not in ordered_names:
            ordered_names.append(name)

    generators: list[ImageProvider] = []
    for name in ordered_names:
        cls = registry.get(name)
        if cls is None:
            raise ValueError(
                f"Unknown image provider '{name}'. Available: {', '.join(registry)}"
            )
        try:
            generators.append(cls())
        except (ImageGenerationError, ImportError) as e:
            if name == primary and not fallback_names:
                raise
            logger.warning(f"Skipping unavailable provider '{name}': {e}")

    if not generators:
        raise ImageGenerationError("Could not initialize any image providers.")

    if len(generators) == 1:
        return generators[0]

    return FallbackImageGenerator(generators)
