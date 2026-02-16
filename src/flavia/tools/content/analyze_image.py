"""Tool for analyzing images using vision-capable LLMs."""

from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..base import BaseTool, ToolSchema, ToolParameter
from ..permissions import check_read_permission, resolve_path

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext


# Supported image extensions
SUPPORTED_EXTENSIONS = {
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


class AnalyzeImageTool(BaseTool):
    """Analyze an image file using a vision-capable LLM model.

    This tool uses multimodal AI to generate detailed text descriptions
    of images, including the main subject, colors, text, context, and
    technical details.
    """

    name = "analyze_image"
    description = (
        "Analyze an image file using a vision-capable LLM to generate a detailed "
        "text description. Supports PNG, JPG, GIF, BMP, WEBP, ICO, TIFF, and SVG formats. "
        "Use this to understand the contents of images in the project."
    )
    category = "read"

    def get_schema(self, **context) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="file_path",
                    type="string",
                    description=(
                        "Path to the image file to analyze (relative to base directory or absolute)"
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="prompt",
                    type="string",
                    description=(
                        "Optional custom prompt for the analysis. "
                        "If not provided, uses a default prompt that requests "
                        "a comprehensive description including subject, colors, text, and context."
                    ),
                    required=False,
                ),
            ],
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        from flavia.config import get_settings
        from flavia.content.vision import analyze_image

        file_path = args.get("file_path", "")
        custom_prompt = args.get("prompt")

        if not file_path:
            return "Error: file_path is required"

        # Resolve and validate path
        full_path = resolve_path(file_path, agent_context.base_dir)

        # Security check: path must be within allowed areas
        allowed, error_msg = check_read_permission(full_path, agent_context)
        if not allowed:
            return f"Error: {error_msg}"

        if not full_path.exists():
            return f"Error: File not found: {file_path}"

        if not full_path.is_file():
            return f"Error: '{file_path}' is not a file"

        # Check if it's a supported image format
        if full_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return (
                f"Error: Unsupported image format '{full_path.suffix}'. "
                f"Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )

        # Get settings and resolve vision model
        settings = get_settings()
        model, api_key, api_base_url, headers = self._resolve_vision_model(settings)

        if not api_key:
            return (
                "Error: No API key available for vision model. "
                "Configure SYNTHETIC_API_KEY or set up providers in providers.yaml."
            )

        # Analyze the image
        description, error = analyze_image(
            image_path=full_path,
            api_key=api_key,
            api_base_url=api_base_url,
            model=model,
            prompt=custom_prompt,
            headers=headers,
        )

        if error:
            return f"Error analyzing image: {error}"

        if not description:
            return "Error: Image analysis returned no description"

        # Format the response
        return self._format_response(file_path, full_path, description, model)

    def _resolve_vision_model(
        self, settings
    ) -> tuple[str, str, str, dict[str, str] | None]:
        """Resolve the vision model to use and its credentials.

        Args:
            settings: Application settings.

        Returns:
            Tuple of (model_id, api_key, api_base_url, headers).
        """
        from flavia.content.converters.image_converter import DEFAULT_VISION_MODEL

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

    @staticmethod
    def _format_response(
        file_path: str,
        full_path: Path,
        description: str,
        model: str,
    ) -> str:
        """Format the analysis response.

        Args:
            file_path: Original file path argument.
            full_path: Resolved full path.
            description: Generated image description.
            model: Model used for analysis.

        Returns:
            Formatted response string.
        """
        ext = full_path.suffix.lstrip(".").upper()
        try:
            size_bytes = full_path.stat().st_size
            if size_bytes >= 1_048_576:
                size_str = f"{size_bytes / 1_048_576:.1f} MB"
            elif size_bytes >= 1024:
                size_str = f"{size_bytes / 1024:.1f} KB"
            else:
                size_str = f"{size_bytes} bytes"
        except OSError:
            size_str = "unknown"

        return (
            f"Image Analysis: {file_path}\n"
            f"Format: {ext} | Size: {size_str} | Model: {model}\n"
            f"\n"
            f"{description}"
        )

    def is_available(self, agent_context: "AgentContext") -> bool:
        """Always available if the tool is registered."""
        return True
