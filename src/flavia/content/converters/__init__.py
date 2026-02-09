"""File converters for the content management system."""

from .base import BaseConverter
from .pdf_converter import PdfConverter
from .registry import (
    ConverterRegistry,
    converter_registry,
    register_converter,
    register_source_converter,
)
from .text_reader import TextReader

# Online source converters
from .online import OnlineSourceConverter, WebPageConverter, YouTubeConverter

__all__ = [
    "BaseConverter",
    "PdfConverter",
    "TextReader",
    "ConverterRegistry",
    "converter_registry",
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
    register_converter(TextReader())

    # Online source converters
    register_source_converter("youtube", YouTubeConverter())
    register_source_converter("webpage", WebPageConverter())


# Auto-register converters on import
_register_default_converters()
