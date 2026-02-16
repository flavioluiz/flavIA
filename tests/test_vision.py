"""Tests for vision-capable LLM utilities."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from flavia.content.vision import (
    encode_image_base64,
    convert_svg_to_png,
    analyze_image,
    _prepare_image_content,
    _extract_response_text,
    _is_vision_incompatible_error,
)


class TestEncodeImageBase64:
    """Tests for base64 image encoding."""

    def test_encode_png_image(self, tmp_path: Path):
        """encode_image_base64 properly encodes a PNG image."""
        image_file = tmp_path / "test.png"
        image_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        image_file.write_bytes(image_data)

        encoded, mime_type = encode_image_base64(image_file)

        assert isinstance(encoded, str)
        assert len(encoded) > 0
        assert mime_type == "image/png"

    @pytest.mark.parametrize(
        "ext,expected_mime",
        [
            (".jpg", "image/jpeg"),
            (".jpeg", "image/jpeg"),
            (".gif", "image/gif"),
            (".bmp", "image/bmp"),
            (".webp", "image/webp"),
            (".ico", "image/x-icon"),
            (".tiff", "image/tiff"),
            (".tif", "image/tiff"),
            (".svg", "image/svg+xml"),
        ],
    )
    def test_encode_various_formats(self, ext: str, expected_mime: str, tmp_path: Path):
        """encode_image_base64 handles various image formats."""
        image_file = tmp_path / f"test{ext}"
        minimal_data = b"\x00" * 100
        image_file.write_bytes(minimal_data)

        encoded, mime_type = encode_image_base64(image_file)

        assert isinstance(encoded, str)
        assert len(encoded) > 0
        assert mime_type == expected_mime

    def test_encode_nonexistent_file_raises_error(self, tmp_path: Path):
        """encode_image_base64 raises FileNotFoundError for nonexistent file."""
        image_file = tmp_path / "nonexistent.png"

        with pytest.raises(FileNotFoundError):
            encode_image_base64(image_file)

    def test_encode_unknown_extension_fallback(self, tmp_path: Path):
        """encode_image_base64 raises ValueError for unknown extension."""
        image_file = tmp_path / "test.unknown"
        image_file.write_bytes(b"some data")

        with pytest.raises(ValueError, match="Cannot determine MIME type"):
            encode_image_base64(image_file)

    def test_encode_empty_file_raises_error(self, tmp_path: Path):
        """encode_image_base64 raises ValueError for empty image files."""
        image_file = tmp_path / "empty.jpg"
        image_file.write_bytes(b"")

        with pytest.raises(ValueError, match="Image file is empty"):
            encode_image_base64(image_file)


class TestConvertSvgToPng:
    """Tests for SVG to PNG conversion."""

    def test_convert_svg_without_cairosvg(self, tmp_path: Path):
        """convert_svg_to_png returns None when cairosvg is not available."""
        svg_file = tmp_path / "test.svg"
        svg_file.write_text("<svg></svg>")

        with patch.dict("sys.modules", {"cairosvg": None}):
            result = convert_svg_to_png(svg_file)
            assert result is None

    def test_convert_svg_with_cairosvg_available(self, tmp_path: Path):
        """convert_svg_to_png returns PNG data when cairosvg is available."""
        svg_file = tmp_path / "test.svg"
        svg_file.write_text("<svg width='100' height='100'></svg>")

        mock_png_data = b"fake_png_data"

        with patch("builtins.__import__") as mock_import:
            mock_cairosvg = MagicMock()
            mock_cairosvg.svg2png.return_value = mock_png_data
            mock_import.return_value = mock_cairosvg

            result = convert_svg_to_png(svg_file)

            assert result == mock_png_data

    def test_convert_svg_handles_exceptions(self, tmp_path: Path):
        """convert_svg_to_png returns None on cairosvg exceptions."""
        svg_file = tmp_path / "test.svg"
        svg_file.write_text("<svg></svg>")

        with patch("builtins.__import__") as mock_import:
            mock_cairosvg = MagicMock()
            mock_cairosvg.svg2png.side_effect = Exception("Conversion failed")
            mock_import.return_value = mock_cairosvg

            result = convert_svg_to_png(svg_file)

            assert result is None


class TestPrepareImageContent:
    """Tests for image content preparation."""

    def test_prepare_png_image(self, tmp_path: Path):
        """_prepare_image_content handles PNG images correctly."""
        image_file = tmp_path / "test.png"
        image_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)

        base64_data, mime_type, error = _prepare_image_content(image_file)

        assert base64_data is not None
        assert mime_type == "image/png"
        assert error is None

    def test_prepare_svg_without_cairosvg(self, tmp_path: Path):
        """_prepare_image_content attempts direct SVG encoding when cairosvg unavailable."""
        svg_file = tmp_path / "test.svg"
        svg_file.write_text("<svg></svg>")

        with patch("flavia.content.vision.convert_svg_to_png", return_value=None):
            base64_data, mime_type, error = _prepare_image_content(svg_file)

            # Should fall back to direct encoding
            assert base64_data is not None
            assert mime_type == "image/svg+xml"
            assert error is None

    def test_prepare_svg_with_cairosvg(self, tmp_path: Path):
        """_prepare_image_content converts SVG to PNG when cairosvg available."""
        svg_file = tmp_path / "test.svg"
        svg_file.write_text("<svg></svg>")
        mock_png_data = b"fake_png"

        with patch("flavia.content.vision.convert_svg_to_png", return_value=mock_png_data):
            base64_data, mime_type, error = _prepare_image_content(svg_file)

            assert base64_data is not None
            # When converted, MIME type should be image/png
            assert mime_type == "image/png"
            assert error is None

    def test_prepare_nonexistent_file(self, tmp_path: Path):
        """_prepare_image_content returns error for nonexistent file."""
        image_file = tmp_path / "nonexistent.png"

        base64_data, mime_type, error = _prepare_image_content(image_file)

        assert base64_data is None
        assert mime_type is None
        assert error is not None


class TestExtractResponseText:
    """Tests for extracting text from API responses."""

    def test_extract_from_standard_response(self):
        """_extract_response_text extracts text from standard OpenAI response."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "This is a response"

        result = _extract_response_text(mock_response)

        assert result == "This is a response"

    def test_extract_from_list_content(self):
        """_extract_response_text handles list-type content."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = [
            {"type": "text", "text": "First part"},
            {"type": "text", "text": "Second part"},
        ]

        result = _extract_response_text(mock_response)

        assert result == "First part\nSecond part"

    def test_extract_from_dict_content(self):
        """_extract_response_text handles dict-type content."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = [
            {"text": "Content part 1"},
            {"content": "Content part 2"},
        ]

        result = _extract_response_text(mock_response)

        assert result == "Content part 1\nContent part 2"

    def test_extract_from_auxiliary_text_field(self):
        """_extract_response_text checks auxiliary text fields."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None
        mock_response.choices[0].message.output_text = "Auxiliary text"

        result = _extract_response_text(mock_response)

        assert result == "Auxiliary text"

    def test_extract_from_empty_response(self):
        """_extract_response_text returns None for empty response."""
        mock_response = MagicMock()
        mock_response.choices = []

        result = _extract_response_text(mock_response)

        assert result is None

    def test_extract_strips_whitespace(self):
        """_extract_response_text strips whitespace from content."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "  Whitespace trimmed  "

        result = _extract_response_text(mock_response)

        assert result == "Whitespace trimmed"


class TestVisionIncompatibilityError:
    """Tests for vision model incompatibility detection."""

    @pytest.mark.parametrize(
        "error_string",
        [
            "does not support vision",
            "vision not supported",
            "vision capability missing",
            "image analysis not available",
            "multimodal not supported",
            "unsupported content type: image_url",
            "invalid content type for image input",
            "does not support image",
            "not support images",
        ],
    )
    def test_detect_vision_incompatibility_errors(self, error_string: str):
        """_is_vision_incompatible_error identifies vision-related errors."""
        error = Exception(error_string)

        result = _is_vision_incompatible_error(error)

        assert result is True

    @pytest.mark.parametrize(
        "error_string",
        [
            "API rate limit exceeded",
            "authentication failed",
            "network timeout",
            "invalid API key",
            "some other error",
            "Unsupported parameter: 'temperature'",
            "invalid content type for text input",
        ],
    )
    def test_non_vision_errors(self, error_string: str):
        """_is_vision_incompatible_error returns False for non-vision errors."""
        error = Exception(error_string)

        result = _is_vision_incompatible_error(error)

        assert result is False

    def test_case_insensitive_detection(self):
        """_is_vision_incompatible_error is case-insensitive."""
        error = Exception("VISION NOT SUPPORTED")

        result = _is_vision_incompatible_error(error)

        assert result is True


class TestAnalyzeImage:
    """Tests for the main analyze_image function."""

    @patch("flavia.content.vision._prepare_image_content")
    def test_analyze_image_rejects_oversized_image(self, mock_prepare, tmp_path: Path):
        """analyze_image rejects images larger than the configured limit."""
        image_file = tmp_path / "large.png"
        image_file.write_bytes(b"12345")

        description, error = analyze_image(
            image_path=image_file,
            api_key="test-key",
            api_base_url="https://api.example.com",
            model="test-model",
            max_image_bytes=4,
        )

        assert description is None
        assert error is not None
        assert "too large" in error.lower()
        mock_prepare.assert_not_called()

    @patch("flavia.content.vision._prepare_image_content")
    def test_analyze_image_rejects_empty_file(self, mock_prepare, tmp_path: Path):
        """analyze_image rejects empty image files before API call."""
        image_file = tmp_path / "empty.png"
        image_file.write_bytes(b"")

        description, error = analyze_image(
            image_path=image_file,
            api_key="test-key",
            api_base_url="https://api.example.com",
            model="test-model",
        )

        assert description is None
        assert error is not None
        assert "empty" in error.lower()
        mock_prepare.assert_not_called()

    @patch("flavia.content.vision._prepare_image_content")
    @patch("flavia.content.vision._call_vision_llm")
    def test_analyze_image_success(self, mock_call_llm, mock_prepare, tmp_path: Path):
        """analyze_image returns description on success."""
        image_file = tmp_path / "test.png"
        image_file.write_bytes(b"\x89PNG\r\n\x1a\n")

        mock_prepare.return_value = ("base64data", "image/png", None)
        mock_call_llm.return_value = ("Image shows a sunset", None)

        description, error = analyze_image(
            image_path=image_file,
            api_key="test-key",
            api_base_url="https://api.example.com",
            model="test-model",
        )

        assert description == "Image shows a sunset"
        assert error is None

    @patch("flavia.content.vision._prepare_image_content")
    def test_analyze_image_prep_error(self, mock_prepare, tmp_path: Path):
        """analyze_image returns error when image preparation fails."""
        image_file = tmp_path / "test.png"
        image_file.write_bytes(b"not an image")

        mock_prepare.return_value = (None, None, "Invalid image format")

        description, error = analyze_image(
            image_path=image_file,
            api_key="test-key",
            api_base_url="https://api.example.com",
            model="test-model",
        )

        assert description is None
        assert "Invalid image format" in error

    @patch("flavia.content.vision._prepare_image_content")
    @patch("flavia.content.vision._call_vision_llm")
    def test_analyze_image_llm_error(self, mock_call_llm, mock_prepare, tmp_path: Path):
        """analyze_image returns error when LLM call fails."""
        image_file = tmp_path / "test.png"
        image_file.write_bytes(b"\x89PNG\r\n\x1a\n")

        mock_prepare.return_value = ("base64data", "image/png", None)
        mock_call_llm.return_value = (None, "API error")

        description, error = analyze_image(
            image_path=image_file,
            api_key="test-key",
            api_base_url="https://api.example.com",
            model="test-model",
        )

        assert description is None
        assert error == "API error"

    @patch("flavia.content.vision._prepare_image_content")
    @patch("flavia.content.vision._call_vision_llm")
    def test_analyze_image_custom_prompt(self, mock_call_llm, mock_prepare, tmp_path: Path):
        """analyze_image uses custom prompt when provided."""
        image_file = tmp_path / "test.png"
        image_file.write_bytes(b"\x89PNG\r\n\x1a\n")

        mock_prepare.return_value = ("base64data", "image/png", None)
        mock_call_llm.return_value = ("Response", None)

        custom_prompt = "Custom analysis prompt"
        description, error = analyze_image(
            image_path=image_file,
            api_key="test-key",
            api_base_url="https://api.example.com",
            model="test-model",
            prompt=custom_prompt,
        )

        assert description == "Response"
        assert error is None

        # Check that custom prompt was used
        call_args = mock_call_llm.call_args
        messages = call_args[1]["messages"]
        assert any(custom_prompt in str(msg) for msg in messages)

    @patch("flavia.content.vision._prepare_image_content")
    @patch("flavia.content.vision._call_vision_llm")
    def test_analyze_image_with_headers(self, mock_call_llm, mock_prepare, tmp_path: Path):
        """analyze_image passes custom headers to LLM call."""
        image_file = tmp_path / "test.png"
        image_file.write_bytes(b"\x89PNG\r\n\x1a\n")

        mock_prepare.return_value = ("base64data", "image/png", None)
        mock_call_llm.return_value = ("Response", None)

        custom_headers = {"X-Custom-Header": "value"}
        description, error = analyze_image(
            image_path=image_file,
            api_key="test-key",
            api_base_url="https://api.example.com",
            model="test-model",
            headers=custom_headers,
        )

        assert description == "Response"
        assert error is None

        # Check that headers were passed
        call_args = mock_call_llm.call_args
        assert call_args[1]["headers"] == custom_headers


class TestDefaultPrompt:
    """Tests for the default image analysis prompt."""

    def test_default_prompt_exists(self):
        """Default image analysis prompt is defined."""
        from flavia.content.vision import DEFAULT_IMAGE_ANALYSIS_PROMPT

        assert DEFAULT_IMAGE_ANALYSIS_PROMPT is not None
        assert len(DEFAULT_IMAGE_ANALYSIS_PROMPT) > 0

    def test_default_prompt_content(self):
        """Default prompt asks for detailed image description."""
        from flavia.content.vision import DEFAULT_IMAGE_ANALYSIS_PROMPT

        assert (
            "Describe" in DEFAULT_IMAGE_ANALYSIS_PROMPT
            or "describe" in DEFAULT_IMAGE_ANALYSIS_PROMPT
        )
