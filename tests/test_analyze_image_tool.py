"""Tests for the AnalyzeImageTool."""

from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from flavia.agent.context import AgentContext
from flavia.tools.content.analyze_image import (
    AnalyzeImageTool,
    SUPPORTED_EXTENSIONS,
)


class TestAnalyzeImageToolBasics:
    """Basic tests for AnalyzeImageTool."""

    def test_tool_name(self):
        """Tool has correct name."""
        tool = AnalyzeImageTool()
        assert tool.name == "analyze_image"

    def test_tool_description(self):
        """Tool has description mentioning image analysis."""
        tool = AnalyzeImageTool()
        assert "image" in tool.description.lower()
        assert "vision" in tool.description.lower() or "llm" in tool.description.lower()

    def test_tool_category(self):
        """Tool is categorized as a read tool."""
        tool = AnalyzeImageTool()
        assert tool.category == "read"

    def test_supported_extensions(self):
        """Supported extensions include common image formats."""
        expected = {
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
        assert SUPPORTED_EXTENSIONS == expected


class TestToolSchema:
    """Tests for tool schema generation."""

    def test_schema_structure(self):
        """get_schema returns proper structure."""
        from flavia.tools.base import ToolSchema, ToolParameter

        tool = AnalyzeImageTool()
        schema = tool.get_schema()

        assert isinstance(schema, ToolSchema)
        assert schema.name == "analyze_image"
        assert len(schema.parameters) >= 1

    def test_file_path_parameter(self):
        """Schema includes file_path parameter."""
        tool = AnalyzeImageTool()
        schema = tool.get_schema()

        file_param = next((p for p in schema.parameters if p.name == "file_path"), None)
        assert file_param is not None
        assert file_param.type == "string"
        assert file_param.required is True

    def test_prompt_parameter(self):
        """Schema includes optional prompt parameter."""
        tool = AnalyzeImageTool()
        schema = tool.get_schema()

        prompt_param = next((p for p in schema.parameters if p.name == "prompt"), None)
        assert prompt_param is not None
        assert prompt_param.type == "string"
        assert prompt_param.required is False


class TestToolExecution:
    """Tests for tool execution."""

    @pytest.fixture
    def sample_context(self, tmp_path: Path) -> Generator[AgentContext, None, None]:
        """Create a sample agent context for testing."""
        context = AgentContext(base_dir=tmp_path)
        yield context

    @pytest.fixture
    def sample_image(self, tmp_path: Path) -> Generator[Path, None, None]:
        """Create a sample image file."""
        image_file = tmp_path / "test_image.png"
        image_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        yield image_file

    def test_execute_missing_file_path(self, sample_context: AgentContext):
        """execute returns error when file_path is missing."""
        tool = AnalyzeImageTool()
        result = tool.execute({}, sample_context)

        assert "Error" in result
        assert "file_path" in result.lower()

    def test_execute_file_not_found(self, sample_context: AgentContext):
        """execute returns error when file doesn't exist."""
        tool = AnalyzeImageTool()
        args = {"file_path": "nonexistent.png"}
        result = tool.execute(args, sample_context)

        assert "Error" in result
        assert "not found" in result.lower()

    def test_execute_with_directory_path(self, sample_context: AgentContext, tmp_path: Path):
        """execute returns error when path is a directory."""
        tool = AnalyzeImageTool()
        args = {"file_path": str(tmp_path)}
        result = tool.execute(args, sample_context)

        assert "Error" in result
        assert "not a file" in result.lower()

    def test_execute_unsupported_format(self, sample_context: AgentContext, tmp_path: Path):
        """execute returns error for unsupported file format."""
        text_file = tmp_path / "test.txt"
        text_file.write_text("Not an image")

        tool = AnalyzeImageTool()
        args = {"file_path": "test.txt"}
        result = tool.execute(args, sample_context)

        assert "Error" in result
        assert "unsupported" in result.lower()

    @patch("flavia.content.vision.analyze_image")
    @patch("flavia.config.get_settings")
    def test_execute_no_api_key(
        self, mock_get_settings, mock_analyze, sample_context: AgentContext, sample_image: Path
    ):
        """execute returns error when no API key is available."""
        mock_settings = MagicMock()
        mock_settings.api_key = ""
        mock_settings.api_base_url = "https://api.example.com"
        mock_settings.resolve_model_with_provider.return_value = (None, "test-model")
        mock_settings.image_vision_model = None
        mock_get_settings.return_value = mock_settings

        tool = AnalyzeImageTool()
        args = {"file_path": "test_image.png"}
        result = tool.execute(args, sample_context)

        assert "Error" in result
        assert "api key" in result.lower()

    @patch("flavia.content.vision.analyze_image")
    @patch("flavia.config.get_settings")
    def test_execute_success(
        self, mock_get_settings, mock_analyze, sample_context: AgentContext, sample_image: Path
    ):
        """execute returns image description on success."""
        mock_settings = MagicMock()
        mock_settings.api_key = "test-key"
        mock_settings.api_base_url = "https://api.example.com"
        mock_settings.resolve_model_with_provider.return_value = (
            MagicMock(api_key="test-key", api_base_url="https://api.example.com", headers=None),
            "test-model",
        )
        mock_settings.image_vision_model = None
        mock_get_settings.return_value = mock_settings
        mock_analyze.return_value = ("A beautiful sunset", None)

        tool = AnalyzeImageTool()
        args = {"file_path": "test_image.png"}
        result = tool.execute(args, sample_context)

        assert "Error" not in result
        assert "sunset" in result.lower()

    @patch("flavia.content.vision.analyze_image")
    @patch("flavia.config.get_settings")
    def test_execute_with_custom_prompt(
        self, mock_get_settings, mock_analyze, sample_context: AgentContext, sample_image: Path
    ):
        """execute passes custom prompt to analysis."""
        mock_settings = MagicMock()
        mock_settings.api_key = "test-key"
        mock_settings.api_base_url = "https://api.example.com"
        mock_settings.resolve_model_with_provider.return_value = (
            MagicMock(api_key="test-key", api_base_url="https://api.example.com", headers=None),
            "test-model",
        )
        mock_settings.image_vision_model = None
        mock_get_settings.return_value = mock_settings
        mock_analyze.return_value = ("Analysis result", None)

        tool = AnalyzeImageTool()
        custom_prompt = "Describe the colors in detail"
        args = {"file_path": "test_image.png", "prompt": custom_prompt}
        result = tool.execute(args, sample_context)

        assert "Error" not in result
        # Verify the custom prompt was passed
        mock_analyze.assert_called_once()
        call_kwargs = mock_analyze.call_args[1]
        assert call_kwargs["prompt"] == custom_prompt

    @patch("flavia.content.vision.analyze_image")
    @patch("flavia.config.get_settings")
    def test_execute_formatting(
        self, mock_get_settings, mock_analyze, sample_context: AgentContext, sample_image: Path
    ):
        """execute formats the response properly."""
        mock_settings = MagicMock()
        mock_settings.api_key = "test-key"
        mock_settings.api_base_url = "https://api.example.com"
        mock_settings.resolve_model_with_provider.return_value = (
            MagicMock(api_key="test-key", api_base_url="https://api.example.com", headers=None),
            "test-model",
        )
        mock_settings.image_vision_model = None
        mock_get_settings.return_value = mock_settings
        mock_analyze.return_value = ("Image description", None)

        tool = AnalyzeImageTool()
        args = {"file_path": "test_image.png"}
        result = tool.execute(args, sample_context)

        assert "Image Analysis" in result
        assert "test_image.png" in result
        assert "Format:" in result
        assert "PNG" in result
        assert "Size:" in result
        assert "Model:" in result
        assert "Image description" in result


class TestResolveVisionModel:
    """Tests for vision model resolution."""

    def test_resolve_uses_default_when_not_configured(self):
        """_resolve_vision_model uses default model when image_vision_model is None."""
        from flavia.content.converters.image_converter import DEFAULT_VISION_MODEL

        mock_settings = MagicMock()
        mock_settings.api_key = "test-key"
        mock_settings.api_base_url = "https://api.example.com"
        mock_settings.image_vision_model = None
        mock_settings.resolve_model_with_provider.return_value = (None, None)
        mock_settings.resolve_model.return_value = "default-model"

        tool = AnalyzeImageTool()
        model_id, api_key, api_base_url, headers = tool._resolve_vision_model(mock_settings)

        assert model_id is not None
        assert api_key == "test-key"
        mock_settings.resolve_model.assert_called_once_with(DEFAULT_VISION_MODEL)

    def test_resolve_uses_configured_model(self):
        """_resolve_vision_model uses configured image_vision_model when available."""
        mock_settings = MagicMock()
        mock_settings.api_key = "test-key"
        mock_settings.api_base_url = "https://api.example.com"
        mock_settings.image_vision_model = "custom:vision-model"
        mock_settings.resolve_model_with_provider.return_value = (
            MagicMock(api_key="test-key", api_base_url="https://api.example.com", headers=None),
            "vision-model",
        )

        tool = AnalyzeImageTool()
        model_id, api_key, api_base_url, headers = tool._resolve_vision_model(mock_settings)

        assert "vision-model" in model_id


class TestFormatResponse:
    """Tests for response formatting."""

    @pytest.mark.parametrize(
        "size_bytes,expected_size_str",
        [
            (500, "500 bytes"),
            (1024, "1.0 KB"),
            (524288, "512.0 KB"),
            (1048576, "1.0 MB"),
            (10485760, "10.0 MB"),
        ],
    )
    def test_format_size(self, size_bytes: int, expected_size_str: str, tmp_path: Path):
        """_format_response correctly formats file size."""
        image_file = tmp_path / "test.jpg"
        image_file.write_bytes(b"\x00" * size_bytes)

        result = AnalyzeImageTool._format_response(
            file_path="test.jpg",
            full_path=image_file,
            description="Test description",
            model="test-model",
        )

        assert expected_size_str in result

    def test_format_response_includes_format(self, tmp_path: Path):
        """_format_response includes image format."""
        image_file = tmp_path / "test.png"
        image_file.write_bytes(b"\x00" * 100)

        result = AnalyzeImageTool._format_response(
            file_path="test.png",
            full_path=image_file,
            description="Test description",
            model="test-model",
        )

        assert "PNG" in result

    def test_format_response_includes_model(self, tmp_path: Path):
        """_format_response includes model name."""
        image_file = tmp_path / "test.jpg"
        image_file.write_bytes(b"\x00" * 100)

        result = AnalyzeImageTool._format_response(
            file_path="test.jpg",
            full_path=image_file,
            description="Test description",
            model="vision-model-v2",
        )

        assert "vision-model-v2" in result

    def test_format_response_handles_size_errors(self, tmp_path: Path):
        """_format_response handles FileNotFoundError when getting size."""
        image_file = tmp_path / "test.jpg"
        image_file.write_bytes(b"\x00" * 100)

        # Remove file after creating it to trigger stat() error path.
        image_file.unlink()

        result = AnalyzeImageTool._format_response(
            file_path="test.jpg",
            full_path=image_file,
            description="Test description",
            model="test-model",
        )

        assert "unknown" in result.lower()


class TestToolAvailability:
    """Tests for tool availability."""

    def test_is_available_returns_true(self, tmp_path: Path):
        """is_available always returns True when tool is registered."""
        context = AgentContext(base_dir=tmp_path)
        tool = AnalyzeImageTool()

        result = tool.is_available(context)

        assert result is True


class TestSecurity:
    """Tests for security-related behavior."""

    @pytest.fixture
    def sample_context(self, tmp_path: Path) -> Generator[AgentContext, None, None]:
        """Create a sample agent context for testing."""
        context = AgentContext(base_dir=tmp_path)
        yield context

    def test_blocks_path_traversal(self, sample_context: AgentContext, tmp_path: Path):
        """execute blocks path traversal attempts."""
        image_file = tmp_path / "test.png"
        image_file.write_bytes(b"\x00" * 100)

        tool = AnalyzeImageTool()
        args = {"file_path": "../test.png"}
        result = tool.execute(args, sample_context)

        assert "Error" in result
        assert "outside allowed directory" in result

    def test_absolute_path_outside_base_dir(self, sample_context: AgentContext, tmp_path: Path):
        """execute blocks absolute paths outside base directory."""
        outside_dir = tmp_path.parent / "outside"
        outside_dir.mkdir(exist_ok=True)
        image_file = outside_dir / "test.png"
        image_file.write_bytes(b"\x00" * 100)

        tool = AnalyzeImageTool()
        args = {"file_path": str(image_file)}
        result = tool.execute(args, sample_context)

        # Should return an error for files outside base dir
        assert "Error" in result
