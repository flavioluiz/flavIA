"""Converter registry for managing file and source converters."""

from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .base import BaseConverter


class ConverterRegistry:
    """
    Singleton registry for file format converters.

    Manages converters for both local file extensions and online source types.
    """

    _instance: Optional["ConverterRegistry"] = None

    def __new__(cls) -> "ConverterRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._converters = {}
            cls._instance._source_converters = {}
        return cls._instance

    def __init__(self) -> None:
        # Attributes initialized in __new__ for singleton pattern
        pass

    @property
    def converters(self) -> dict[str, "BaseConverter"]:
        """Get all registered file extension converters."""
        return self._converters

    @property
    def source_converters(self) -> dict[str, "BaseConverter"]:
        """Get all registered source type converters."""
        return self._source_converters

    def register(self, converter: "BaseConverter") -> None:
        """
        Register a converter for file extensions.

        Args:
            converter: Converter instance with supported_extensions defined.
        """
        for ext in converter.supported_extensions:
            self._converters[ext.lower()] = converter

    def register_source_converter(
        self, source_type: str, converter: "BaseConverter"
    ) -> None:
        """
        Register a converter for an online source type.

        Args:
            source_type: Source type identifier (e.g., "youtube", "webpage").
            converter: Converter instance for this source type.
        """
        self._source_converters[source_type.lower()] = converter

    def get_for_file(self, file_path: Path) -> Optional["BaseConverter"]:
        """
        Get a converter for a given file path.

        Args:
            file_path: Path to the file.

        Returns:
            Converter that can handle this file, or None if none registered.
        """
        ext = file_path.suffix.lower()
        return self._converters.get(ext)

    def get_for_extension(self, extension: str) -> Optional["BaseConverter"]:
        """
        Get a converter for a given file extension.

        Args:
            extension: File extension (with or without leading dot).

        Returns:
            Converter that can handle this extension, or None if none registered.
        """
        ext = extension.lower()
        if not ext.startswith("."):
            ext = "." + ext
        return self._converters.get(ext)

    def get_for_source(self, source_type: str) -> Optional["BaseConverter"]:
        """
        Get a converter for a given source type.

        Args:
            source_type: Source type identifier (e.g., "youtube", "webpage").

        Returns:
            Converter for this source type, or None if none registered.
        """
        return self._source_converters.get(source_type.lower())

    def list_supported_extensions(self) -> set[str]:
        """
        List all registered file extensions.

        Returns:
            Set of file extensions that have registered converters.
        """
        return set(self._converters.keys())

    def list_supported_sources(self) -> set[str]:
        """
        List all registered source types.

        Returns:
            Set of source types that have registered converters.
        """
        return set(self._source_converters.keys())

    def clear(self) -> None:
        """Clear all registered converters. Useful for testing."""
        self._converters.clear()
        self._source_converters.clear()


# Global singleton instance
converter_registry = ConverterRegistry()


def register_converter(converter: "BaseConverter") -> None:
    """
    Register a converter in the global registry.

    Args:
        converter: Converter instance to register.
    """
    converter_registry.register(converter)


def register_source_converter(source_type: str, converter: "BaseConverter") -> None:
    """
    Register a source converter in the global registry.

    Args:
        source_type: Source type identifier.
        converter: Converter instance to register.
    """
    converter_registry.register_source_converter(source_type, converter)
