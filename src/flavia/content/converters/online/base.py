"""Base class for online source converters."""

from abc import abstractmethod
from pathlib import Path
from typing import Optional

from ..base import BaseConverter


class OnlineSourceConverter(BaseConverter):
    """
    Base class for converters that fetch and process online content.

    Subclasses should implement fetch_and_convert and can_handle_source.
    """

    # Source type identifier (e.g., "youtube", "webpage")
    source_type: str = ""

    # URL patterns this converter recognizes
    url_patterns: list[str] = []

    # Online converters don't handle local file extensions
    supported_extensions: set[str] = set()

    def convert(
        self,
        source_path: Path,
        output_dir: Path,
        output_format: str = "md",
    ) -> Optional[Path]:
        """
        Online converters don't convert local files.

        Returns:
            Always None for online source converters.
        """
        return None

    def extract_text(self, source_path: Path) -> Optional[str]:
        """
        Online converters don't extract from local files.

        Returns:
            Always None for online source converters.
        """
        return None

    def can_handle_source(self, source_url: str) -> bool:
        """
        Check if this converter can handle the given source URL.

        Args:
            source_url: URL to check.

        Returns:
            True if URL matches any of the url_patterns.
        """
        url_lower = source_url.lower()
        return any(pattern.lower() in url_lower for pattern in self.url_patterns)

    @abstractmethod
    def fetch_and_convert(
        self,
        source_url: str,
        output_dir: Path,
    ) -> Optional[Path]:
        """
        Fetch content from a URL and convert to text/markdown.

        Args:
            source_url: URL to fetch content from.
            output_dir: Directory to write the output file.

        Returns:
            Path to the converted file, or None if not implemented/failed.
        """
        pass

    @abstractmethod
    def get_metadata(self, source_url: str) -> dict:
        """
        Get metadata for a source URL without fetching full content.

        Args:
            source_url: URL to get metadata for.

        Returns:
            Dict with metadata (title, duration, author, etc.) or status info.
        """
        pass
