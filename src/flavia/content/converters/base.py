"""Base converter interface."""

import importlib.util
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class BaseConverter(ABC):
    """Abstract base class for file format converters."""

    # Subclasses must define which extensions they handle
    supported_extensions: set[str] = set()

    # Implementation status for placeholder converters
    is_implemented: bool = True

    # Dependencies required for this converter
    requires_dependencies: list[str] = []

    # Optional mapping of package names to import module names
    dependency_import_map: dict[str, str] = {}

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

    def can_handle_source(self, source_url: str) -> bool:
        """
        Check if this converter can handle the given source URL.

        Override in subclasses for online source converters.

        Args:
            source_url: URL to check.

        Returns:
            True if this converter can handle the URL.
        """
        return False

    def fetch_and_convert(
        self,
        source_url: str,
        output_dir: Path,
    ) -> Optional[Path]:
        """
        Fetch content from a URL and convert to text/markdown.

        Override in subclasses for online source converters.

        Args:
            source_url: URL to fetch content from.
            output_dir: Directory to write the output file.

        Returns:
            Path to the converted file, or None if not implemented/failed.
        """
        return None

    def check_dependencies(self) -> tuple[bool, list[str]]:
        """
        Check if required dependencies are installed.

        Returns:
            Tuple of (all_installed, list_of_missing_dependencies).
        """
        if not self.requires_dependencies:
            return True, []

        missing = []
        for dep in self.requires_dependencies:
            module_name = self.dependency_import_map.get(dep, dep).replace("-", "_")
            try:
                if importlib.util.find_spec(module_name) is None:
                    missing.append(dep)
            except (ImportError, ModuleNotFoundError, ValueError):
                missing.append(dep)

        return len(missing) == 0, missing

    def get_implementation_status(self) -> dict:
        """
        Get status information about this converter.

        Returns:
            Dict with implementation status, dependencies, and feature info.
        """
        deps_ok, missing = self.check_dependencies()
        return {
            "is_implemented": self.is_implemented,
            "requires_dependencies": self.requires_dependencies,
            "dependencies_installed": deps_ok,
            "missing_dependencies": missing,
        }
