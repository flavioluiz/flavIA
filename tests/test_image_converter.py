"""Tests for the image converter."""

from collections.abc import Generator
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from flavia.content.converters import ImageConverter, converter_registry


class TestImageConverterBasics:
    """Basic tests for ImageConverter class."""

    def test_supported_extensions(self):
        """ImageConverter supports expected extensions."""
        converter = ImageConverter()
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
        assert converter.supported_extensions == expected

    def test_can_handle_png(self, tmp_path: Path):
        """ImageConverter can handle .png files."""
        converter = ImageConverter()
        png_file = tmp_path / "test.png"
        png_file.write_bytes(b"\x89PNG\r\n\x1a\n")
        assert converter.can_handle(png_file) is True

    def test_can_handle_jpg(self, tmp_path: Path):
        """ImageConverter can handle .jpg files."""
        converter = ImageConverter()
        jpg_file = tmp_path / "test.jpg"
        jpg_file.write_bytes(b"\xff\xd8\xff")
        assert converter.can_handle(jpg_file) is True

    def test_can_handle_jpeg(self, tmp_path: Path):
        """ImageConverter can handle .jpeg files."""
        converter = ImageConverter()
        jpeg_file = tmp_path / "test.jpeg"
        jpeg_file.write_bytes(b"\xff\xd8\xff")
        assert converter.can_handle(jpeg_file) is True

    def test_can_handle_gif(self, tmp_path: Path):
        """ImageConverter can handle .gif files."""
        converter = ImageConverter()
        gif_file = tmp_path / "test.gif"
        gif_file.write_bytes(b"GIF89a")
        assert converter.can_handle(gif_file) is True

    def test_can_handle_bmp(self, tmp_path: Path):
        """ImageConverter can handle .bmp files."""
        converter = ImageConverter()
        bmp_file = tmp_path / "test.bmp"
        bmp_file.write_bytes(b"BM")
        assert converter.can_handle(bmp_file) is True

    def test_can_handle_webp(self, tmp_path: Path):
        """ImageConverter can handle .webp files."""
        converter = ImageConverter()
        webp_file = tmp_path / "test.webp"
        webp_file.write_bytes(b"RIFF")
        assert converter.can_handle(webp_file) is True

    def test_can_handle_svg(self, tmp_path: Path):
        """ImageConverter can handle .svg files."""
        converter = ImageConverter()
        svg_file = tmp_path / "test.svg"
        svg_file.write_text("<svg></svg>")
        assert converter.can_handle(svg_file) is True

    def test_cannot_handle_unsupported(self, tmp_path: Path):
        """ImageConverter does not handle unsupported extensions."""
        converter = ImageConverter()
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("hello")
        assert converter.can_handle(txt_file) is False

    def test_no_required_dependencies(self):
        """ImageConverter has no required dependencies list."""
        converter = ImageConverter()
        assert converter.requires_dependencies == []


class TestImageConverterRegistration:
    """Tests for ImageConverter registry integration."""

    def test_image_converter_registered(self):
        """ImageConverter is auto-registered in the global registry."""
        converter = converter_registry.get_for_extension(".png")
        assert converter is not None
        assert isinstance(converter, ImageConverter)

    def test_jpg_registered(self):
        """ImageConverter is registered for .jpg."""
        converter = converter_registry.get_for_extension(".jpg")
        assert converter is not None
        assert isinstance(converter, ImageConverter)

    def test_jpeg_registered(self):
        """ImageConverter is registered for .jpeg."""
        converter = converter_registry.get_for_extension(".jpeg")
        assert converter is not None
        assert isinstance(converter, ImageConverter)

    def test_gif_registered(self):
        """ImageConverter is registered for .gif."""
        converter = converter_registry.get_for_extension(".gif")
        assert converter is not None
        assert isinstance(converter, ImageConverter)

    def test_bmp_registered(self):
        """ImageConverter is registered for .bmp."""
        converter = converter_registry.get_for_extension(".bmp")
        assert converter is not None
        assert isinstance(converter, ImageConverter)

    def test_webp_registered(self):
        """ImageConverter is registered for .webp."""
        converter = converter_registry.get_for_extension(".webp")
        assert converter is not None
        assert isinstance(converter, ImageConverter)

    def test_ico_registered(self):
        """ImageConverter is registered for .ico."""
        converter = converter_registry.get_for_extension(".ico")
        assert converter is not None
        assert isinstance(converter, ImageConverter)

    def test_tiff_registered(self):
        """ImageConverter is registered for .tiff."""
        converter = converter_registry.get_for_extension(".tiff")
        assert converter is not None
        assert isinstance(converter, ImageConverter)

    def test_tif_registered(self):
        """ImageConverter is registered for .tif."""
        converter = converter_registry.get_for_extension(".tif")
        assert converter is not None
        assert isinstance(converter, ImageConverter)


class TestImageConverterConversion:
    """Tests for image conversion functionality."""

    @pytest.fixture
    def sample_image(self, tmp_path: Path) -> Generator[Path, None, None]:
        """Create a sample image file for testing."""
        image_file = tmp_path / "test_image.png"
        image_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00")
        yield image_file

    def test_extract_text_with_no_api_key_returns_none(
        self, sample_image: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """extract_text returns None when no API key is available."""
        settings_mock = Mock()
        settings_mock.api_key = ""
        settings_mock.api_base_url = "https://api.example.com"
        settings_mock.resolve_model_with_provider.return_value = (None, "test-model")

        converter = ImageConverter(settings_mock)
        result = converter.extract_text(sample_image)
        assert result is None

    @patch("flavia.content.converters.image_converter.analyze_image")
    def test_extract_text_success(
        self, mock_analyze, sample_image: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """extract_text returns description when vision analysis succeeds."""
        mock_analyze.return_value = ("A beautiful sunset over mountains.", None)

        settings_mock = Mock()
        settings_mock.api_key = "test-key"
        settings_mock.api_base_url = "https://api.example.com"
        settings_mock.resolve_model_with_provider.return_value = (
            Mock(api_key="test-key", api_base_url="https://api.example.com", headers=None),
            "test-model",
        )

        converter = ImageConverter(settings_mock)
        result = converter.extract_text(sample_image)

        assert result == "A beautiful sunset over mountains."
        mock_analyze.assert_called_once()

    @patch("flavia.content.converters.image_converter.analyze_image")
    def test_convert_creates_markdown_file(
        self, mock_analyze, sample_image: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """convert creates a markdown file with image description."""
        mock_analyze.return_value = ("A test image description.", None)

        settings_mock = Mock()
        settings_mock.api_key = "test-key"
        settings_mock.api_base_url = "https://api.example.com"
        settings_mock.resolve_model_with_provider.return_value = (
            Mock(api_key="test-key", api_base_url="https://api.example.com", headers=None),
            "test-model",
        )

        converter = ImageConverter(settings_mock)
        output_dir = tmp_path / ".converted"

        result = converter.convert(sample_image, output_dir)

        assert result is not None
        assert result.exists()
        assert result.suffix == ".md"
        assert "test image description" in result.read_text().lower()

    @patch("flavia.content.converters.image_converter.analyze_image")
    def test_convert_preserves_directory_structure(
        self, mock_analyze, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """convert preserves directory structure of source files."""
        nested_dir = tmp_path / "images" / "photos"
        nested_dir.mkdir(parents=True)

        image_file = nested_dir / "photo.png"
        image_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00")

        settings_mock = Mock()
        settings_mock.api_key = "test-key"
        settings_mock.api_base_url = "https://api.example.com"
        settings_mock.resolve_model_with_provider.return_value = (
            Mock(api_key="test-key", api_base_url="https://api.example.com", headers=None),
            "test-model",
        )

        mock_analyze.return_value = ("Description", None)
        converter = ImageConverter(settings_mock)
        output_dir = tmp_path / ".converted"

        result = converter.convert(image_file, output_dir)

        assert result is not None
        # The output should preserve the nested structure
        result_str = str(result)
        assert "images" in result_str or "photos" in result_str


class TestMarkdownFormatting:
    """Tests for markdown formatting utilities."""

    def test_format_as_markdown_includes_title(self, tmp_path: Path):
        """_format_as_markdown includes title from filename."""
        image_file = tmp_path / "test_image.jpg"
        description = "A test image"
        result = ImageConverter._format_as_markdown(description, image_file)
        assert "# test image" in result

    @pytest.mark.parametrize(
        "filename,expected_title",
        [
            ("my-photo.png", "# my photo"),
            ("screenshot_2024.png", "# screenshot 2024"),
            ("chart_image-v2.png", "# chart image v2"),
        ],
    )
    def test_format_title_cleaning(self, filename, expected_title, tmp_path: Path):
        """_format_as_markdown cleans underscores and dashes in title."""
        image_file = tmp_path / filename
        description = "Description"
        result = ImageConverter._format_as_markdown(description, image_file)
        assert expected_title in result

    def test_format_as_markdown_includes_metadata(self, tmp_path: Path):
        """_format_as_markdown includes metadata about the image."""
        image_file = tmp_path / "test.png"
        description = "A description"
        result = ImageConverter._format_as_markdown(description, image_file)
        assert "Original file:" in result
        assert "test.png" in result
        assert "Format:" in result
        assert "PNG" in result

    def test_format_as_markdown_includes_description_section(self, tmp_path: Path):
        """_format_as_markdown includes description section header."""
        image_file = tmp_path / "test.jpg"
        description = "A wonderful image"
        result = ImageConverter._format_as_markdown(description, image_file)
        assert "## Description" in result
        assert "A wonderful image" in result


class TestVisionModelResolution:
    """Tests for vision model resolution."""

    def test_resolve_vision_model_returns_tuple(self, monkeypatch: pytest.MonkeyPatch):
        """_resolve_vision_model returns a tuple with 4 elements."""
        from flavia.config import Settings

        settings = Settings()
        converter = ImageConverter(settings)
        result = converter._resolve_vision_model()
        assert isinstance(result, tuple)
        assert len(result) == 4

    def test_resolve_vision_model_uses_default_when_not_configured(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """_resolve_vision_model uses default model when image_vision_model is not configured."""
        from flavia.config import Settings

        settings = Settings()
        assert not hasattr(settings, "image_vision_model") or settings.image_vision_model is None

        converter = ImageConverter(settings)
        model_id, api_key, api_base_url, headers = converter._resolve_vision_model()

        # Should use default vision model format
        assert model_id is not None

    def test_resolve_vision_model_uses_configured_model(self, monkeypatch: pytest.MonkeyPatch):
        """_resolve_vision_model uses configured image_vision_model when available."""
        from flavia.config import Settings

        settings = Settings()
        settings.image_vision_model = "custom:vision-model"

        converter = ImageConverter(settings)
        model_id, api_key, api_base_url, headers = converter._resolve_vision_model()

        assert "vision-model" in model_id or "custom" in model_id
