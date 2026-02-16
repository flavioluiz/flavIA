"""File converters for the content management system."""

from .base import BaseConverter
from .audio_converter import AudioConverter
from .image_converter import ImageConverter
from .mistral_key_manager import get_mistral_api_key
from .mistral_ocr_converter import MistralOcrConverter
from .office_converter import OfficeConverter
from .pdf_converter import PdfConverter
from .registry import (
    ConverterRegistry,
    converter_registry,
    register_converter,
    register_source_converter,
)
from .text_reader import TextReader
from .video_converter import VideoConverter

# Online source converters
from .online import OnlineSourceConverter, WebPageConverter, YouTubeConverter

__all__ = [
    "BaseConverter",
    "AudioConverter",
    "ImageConverter",
    "MistralOcrConverter",
    "OfficeConverter",
    "PdfConverter",
    "TextReader",
    "VideoConverter",
    "ConverterRegistry",
    "converter_registry",
    "get_mistral_api_key",
    "register_converter",
    "register_source_converter",
    "OnlineSourceConverter",
    "YouTubeConverter",
    "WebPageConverter",
]


def _register_default_converters() -> None:
    """Register all default converters with the global registry."""
    # File extension converters
    register_converter(PdfConverter())
    register_converter(OfficeConverter())
    register_converter(ImageConverter())
    register_converter(TextReader())
    register_converter(AudioConverter())
    register_converter(VideoConverter())

    # Online source converters
    register_source_converter("youtube", YouTubeConverter())
    register_source_converter("webpage", WebPageConverter())


# Auto-register converters on import
_register_default_converters()
