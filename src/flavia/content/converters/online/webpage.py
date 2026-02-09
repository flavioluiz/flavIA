"""Web page converter (placeholder implementation)."""

from pathlib import Path
from typing import Optional

from .base import OnlineSourceConverter


class WebPageConverter(OnlineSourceConverter):
    """
    Converter for web pages.

    This is a placeholder implementation. Full functionality requires:
    - httpx for HTTP requests
    - beautifulsoup4 for HTML parsing
    - markdownify for HTML to Markdown conversion

    Future capabilities:
    - Fetch web page content
    - Convert HTML to clean Markdown
    - Extract metadata (title, author, date, etc.)
    - Handle various content types (articles, documentation, etc.)
    """

    source_type = "webpage"
    url_patterns = ["http://", "https://"]
    is_implemented = False
    requires_dependencies = ["httpx", "beautifulsoup4", "markdownify"]
    dependency_import_map = {"beautifulsoup4": "bs4"}

    def can_handle_source(self, source_url: str) -> bool:
        """
        Check if this converter can handle the given URL.

        Accepts any HTTP/HTTPS URL that is not handled by other converters.

        Args:
            source_url: URL to check.

        Returns:
            True if URL starts with http:// or https://.
        """
        url_lower = source_url.lower().strip()
        return url_lower.startswith("http://") or url_lower.startswith("https://")

    def fetch_and_convert(
        self,
        source_url: str,
        output_dir: Path,
    ) -> Optional[Path]:
        """
        Fetch and convert a web page to Markdown.

        Not yet implemented. Returns None.

        Args:
            source_url: Web page URL.
            output_dir: Directory to write the output file.

        Returns:
            None (not implemented).
        """
        return None

    def get_metadata(self, source_url: str) -> dict:
        """
        Get metadata for a web page.

        Not yet implemented. Returns status information.

        Args:
            source_url: Web page URL.

        Returns:
            Dict with not_implemented status.
        """
        return {
            "status": "not_implemented",
            "source_url": source_url,
            "source_type": self.source_type,
            "message": "Web page converter not yet implemented. "
            "Requires httpx, beautifulsoup4, and markdownify dependencies.",
        }

    def get_implementation_status(self) -> dict:
        """
        Get detailed implementation status.

        Returns:
            Dict with implementation status and planned features.
        """
        base_status = super().get_implementation_status()
        base_status.update(
            {
                "source_type": self.source_type,
                "url_patterns": self.url_patterns,
                "planned_features": [
                    "HTTP/HTTPS page fetching",
                    "HTML to Markdown conversion",
                    "Metadata extraction (title, author, date)",
                    "Image handling (download or link)",
                    "Table preservation",
                    "Code block detection",
                    "Reading mode / content extraction",
                ],
            }
        )
        return base_status
