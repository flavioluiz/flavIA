"""Image to text description converter using vision-capable LLMs.

Converts image files to markdown descriptions using multimodal models.
"""

import logging
from pathlib import Path
from typing import Optional

from rich.console import Console

from flavia.config import Settings, get_settings
from flavia.content.vision import analyze_image
from flavia.setup.prompt_utils import q_select

from .base import BaseConverter

logger = logging.getLogger(__name__)
console = Console()

# Default vision-capable model for image analysis.
# Format is provider:model_id to integrate with ProviderRegistry resolution.
DEFAULT_VISION_MODEL = "synthetic:hf:moonshotai/Kimi-K2.5"


class ImageConverter(BaseConverter):
    """Converts image files to text descriptions using vision-capable LLMs."""

    supported_extensions = {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".bmp",
        ".webp",
        ".ico",
        ".tiff",
        ".tif",
        ".svg",
    }

    # No required dependencies; cairosvg is optional for SVG conversion
    requires_dependencies = []

    def __init__(self, settings: Optional[Settings] = None):
        """Initialize the image converter.

        Args:
            settings: Optional settings instance. If None, will use global settings.
        """
        self._settings = settings

    @property
    def settings(self) -> Settings:
        """Get settings, loading global settings if not provided."""
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    def convert(
        self,
        source_path: Path,
        output_dir: Path,
        output_format: str = "md",
    ) -> Optional[Path]:
        """Convert an image file to a text description in markdown format.

        Args:
            source_path: Source image path.
            output_dir: Output directory.
            output_format: "md" or "txt".

        Returns:
            Path to the converted file, or None on failure.
        """
        description = self.extract_text(source_path)
        if not description or not description.strip():
            return None

        content = self._format_as_markdown(description, source_path)

        # Preserve directory structure when source lives under output_dir.parent.
        try:
            relative_source = source_path.resolve().relative_to(output_dir.resolve().parent)
            output_file = output_dir / relative_source.with_suffix(f".{output_format}")
        except ValueError:
            output_file = output_dir / (source_path.stem + f".{output_format}")

        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(content, encoding="utf-8")
        return output_file

    def extract_text(self, source_path: Path) -> Optional[str]:
        """Extract text description from an image using a vision-capable LLM.

        Args:
            source_path: Source image path.

        Returns:
            Image description text, or None on failure.
        """
        # Resolve vision model
        model, api_key, api_base_url, headers = self._resolve_vision_model()

        if not api_key:
            logger.warning("No API key available for vision model")
            return None

        description, error = analyze_image(
            image_path=source_path,
            api_key=api_key,
            api_base_url=api_base_url,
            model=model,
            headers=headers,
        )

        if error:
            logger.warning(f"Image analysis failed for {source_path}: {error}")
            # Check if it's a vision-incompatible model error
            if "does not appear to support vision" in error:
                self._suggest_vision_model_switch(error)
            return None

        return description

    def _resolve_vision_model(
        self,
    ) -> tuple[str, str, str, Optional[dict[str, str]]]:
        """Resolve the vision model to use and its credentials.

        Priority:
        1. IMAGE_VISION_MODEL environment variable (via settings)
        2. Default vision model

        Returns:
            Tuple of (model_id, api_key, api_base_url, headers).
        """
        settings = self.settings

        # Check for configured vision model
        vision_model = getattr(settings, "image_vision_model", None)
        if not vision_model:
            vision_model = DEFAULT_VISION_MODEL

        # Resolve model with provider
        provider, model_id = settings.resolve_model_with_provider(vision_model)

        if provider:
            headers = provider.headers if provider.headers else None
            return model_id, provider.api_key, provider.api_base_url, headers

        # Fall back to default settings
        return (
            settings.resolve_model(vision_model),
            settings.api_key,
            settings.api_base_url,
            None,
        )

    def _suggest_vision_model_switch(self, error: str) -> None:
        """Log suggestion to switch to a vision-capable model."""
        logger.info(
            f"Vision model error: {error}\n"
            f"Consider setting IMAGE_VISION_MODEL environment variable to a vision-capable model.\n"
            f"Example: IMAGE_VISION_MODEL={DEFAULT_VISION_MODEL}"
        )

    @staticmethod
    def _format_as_markdown(description: str, source_path: Path) -> str:
        """Format the image description as markdown.

        Args:
            description: The image description text.
            source_path: Original image file path.

        Returns:
            Markdown-formatted content.
        """
        lines = []

        # Add title from filename
        clean_title = source_path.stem.replace("_", " ").replace("-", " ")
        lines.append(f"# {clean_title}")
        lines.append("")

        # Add metadata
        lines.append(f"*Original file: `{source_path.name}`*")
        lines.append(f"*Format: {source_path.suffix.lstrip('.').upper()}*")
        lines.append("")

        # Add description
        lines.append("## Description")
        lines.append("")
        lines.append(description)
        lines.append("")

        return "\n".join(lines)


def prompt_vision_model_selection(settings: Settings) -> Optional[str]:
    """Interactive model selection for vision analysis.

    Args:
        settings: Current settings.

    Returns:
        Selected model reference, or None if cancelled.
    """
    choices = []
    provider_map = getattr(getattr(settings, "providers", None), "providers", {})
    has_provider_map = isinstance(provider_map, dict) and bool(provider_map)

    if has_provider_map:
        for provider in provider_map.values():
            for model in provider.models:
                ref = f"{provider.id}:{model.id}"
                label = f"{provider.name} ({provider.id}) - {model.name} ({model.id})"
                choices.append((label, ref))
    else:
        for model in settings.models:
            choices.append((f"{model.name} ({model.id})", model.id))

    if not choices:
        console.print("[yellow]No models available to select.[/yellow]")
        return None

    # Add default option at the start
    current_vision_model = getattr(settings, "image_vision_model", None) or DEFAULT_VISION_MODEL
    default_label = f"Current/Default ({current_vision_model})"
    choices.insert(0, (default_label, current_vision_model))

    try:
        import questionary as _q

        model_choices = [_q.Choice(title=label, value=ref) for label, ref in choices]
        model_choices.append(_q.Choice(title="Cancel", value="__cancel__"))
    except ImportError:
        model_choices = [label for label, _ in choices] + ["Cancel"]

    selection = q_select(
        "Select a vision model for image analysis:",
        choices=model_choices,
        default=current_vision_model,
    )

    if selection in (None, "__cancel__", "Cancel"):
        return None

    # Map label back to value if needed
    if selection not in {ref for _, ref in choices}:
        reverse = {label: ref for label, ref in choices}
        selection = reverse.get(selection, selection)

    return selection
