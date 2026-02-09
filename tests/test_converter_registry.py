"""Tests for the converter registry."""

from pathlib import Path

import pytest

from flavia.content.converters import (
    BaseConverter,
    ConverterRegistry,
    PdfConverter,
    TextReader,
    converter_registry,
    register_converter,
    register_source_converter,
)
from flavia.content.converters.online import YouTubeConverter, WebPageConverter


class TestConverterRegistry:
    """Tests for the ConverterRegistry class."""

    def test_singleton_pattern(self):
        """Registry is a singleton."""
        reg1 = ConverterRegistry()
        reg2 = ConverterRegistry()
        assert reg1 is reg2

    def test_global_registry_is_singleton(self):
        """Global converter_registry is the same instance."""
        reg = ConverterRegistry()
        assert converter_registry is reg

    def test_register_converter(self):
        """Register a converter for file extensions."""
        registry = ConverterRegistry()
        initial_count = len(registry.converters)

        # PDF converter is auto-registered, so it should already be there
        pdf_converter = registry.get_for_extension(".pdf")
        assert pdf_converter is not None
        assert isinstance(pdf_converter, PdfConverter)

    def test_get_for_file(self, tmp_path):
        """Get converter for a file path."""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF")

        converter = converter_registry.get_for_file(test_file)
        assert converter is not None
        assert isinstance(converter, PdfConverter)

    def test_get_for_extension_with_dot(self):
        """Get converter by extension with leading dot."""
        converter = converter_registry.get_for_extension(".pdf")
        assert converter is not None
        assert isinstance(converter, PdfConverter)

    def test_get_for_extension_without_dot(self):
        """Get converter by extension without leading dot."""
        converter = converter_registry.get_for_extension("pdf")
        assert converter is not None
        assert isinstance(converter, PdfConverter)

    def test_get_for_nonexistent_extension(self):
        """Get converter for unknown extension returns None."""
        converter = converter_registry.get_for_extension(".xyz123")
        assert converter is None

    def test_register_source_converter(self):
        """Register a source converter."""
        # YouTube converter is auto-registered
        youtube = converter_registry.get_for_source("youtube")
        assert youtube is not None
        assert isinstance(youtube, YouTubeConverter)

    def test_get_for_source(self):
        """Get converter by source type."""
        webpage = converter_registry.get_for_source("webpage")
        assert webpage is not None
        assert isinstance(webpage, WebPageConverter)

    def test_get_for_source_case_insensitive(self):
        """Source type lookup is case-insensitive."""
        youtube1 = converter_registry.get_for_source("youtube")
        youtube2 = converter_registry.get_for_source("YOUTUBE")
        youtube3 = converter_registry.get_for_source("YouTube")
        assert youtube1 is youtube2 is youtube3

    def test_get_for_nonexistent_source(self):
        """Get converter for unknown source returns None."""
        converter = converter_registry.get_for_source("unknown_source")
        assert converter is None

    def test_list_supported_extensions(self):
        """List all supported extensions."""
        extensions = converter_registry.list_supported_extensions()
        assert ".pdf" in extensions
        # TextReader supports many extensions
        assert ".py" in extensions or ".txt" in extensions

    def test_list_supported_sources(self):
        """List all supported source types."""
        sources = converter_registry.list_supported_sources()
        assert "youtube" in sources
        assert "webpage" in sources


class TestDefaultConverterRegistration:
    """Tests for default converter auto-registration."""

    def test_pdf_converter_registered(self):
        """PdfConverter is auto-registered."""
        converter = converter_registry.get_for_extension(".pdf")
        assert converter is not None
        assert isinstance(converter, PdfConverter)

    def test_text_reader_registered(self):
        """TextReader is auto-registered for text extensions."""
        converter = converter_registry.get_for_extension(".py")
        assert converter is not None
        assert isinstance(converter, TextReader)

    def test_youtube_converter_registered(self):
        """YouTubeConverter is auto-registered."""
        converter = converter_registry.get_for_source("youtube")
        assert converter is not None
        assert isinstance(converter, YouTubeConverter)

    def test_webpage_converter_registered(self):
        """WebPageConverter is auto-registered."""
        converter = converter_registry.get_for_source("webpage")
        assert converter is not None
        assert isinstance(converter, WebPageConverter)
