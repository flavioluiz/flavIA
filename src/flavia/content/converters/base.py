"""Base converter interface."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class BaseConverter(ABC):
    """Abstract base class for file format converters."""

    # Subclasses must define which extensions they handle
    supported_extensions: set[str] = set()

    @abstractmethod
    def convert(
        self,
        source_path: Path,
        output_dir: Path,
        output_format: str = "md",
    ) -> Optional[Path]:
        """
        Convert a file to text/markdown.

        Args:
            source_path: Path to the source file.
            output_dir: Directory to write the output file.
            output_format: "md" or "txt".

        Returns:
            Path to the converted file, or None on failure.
        """
        pass

    @abstractmethod
    def extract_text(self, source_path: Path) -> Optional[str]:
        """
        Extract text content from a file without writing to disk.

        Args:
            source_path: Path to the source file.

        Returns:
            Extracted text, or None on failure.
        """
        pass

    def can_handle(self, file_path: Path) -> bool:
        """Check if this converter can handle the given file."""
        return file_path.suffix.lower() in self.supported_extensions
