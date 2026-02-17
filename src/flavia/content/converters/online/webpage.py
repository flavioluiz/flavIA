"""Web page converter.

Fetches web pages and extracts clean article text using trafilatura,
producing Markdown output with metadata.

Dependencies (optional extras -- ``pip install 'flavia[online]'``):
- trafilatura: main content / article text extraction from HTML
- httpx (already a core dependency): HTTP fetching
"""

import hashlib
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from .base import OnlineSourceConverter

logger = logging.getLogger(__name__)

# Default user-agent for HTTP requests
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Maximum HTML size we'll attempt to process (10 MB)
_MAX_HTML_BYTES = 10 * 1024 * 1024

# Request timeout in seconds
_REQUEST_TIMEOUT = 30


class WebPageConverter(OnlineSourceConverter):
    """Converter for web pages.

    Uses ``trafilatura`` for extracting the main content (article body)
    from HTML pages and outputs clean Markdown.  Falls back to basic
    HTML tag stripping when trafilatura is unavailable or cannot extract
    content.

    ``httpx`` is used for HTTP fetching (already a core dependency of
    flavIA, so always available).
    """

    source_type = "webpage"
    url_patterns = ["http://", "https://"]
    is_implemented = True
    requires_dependencies = ["trafilatura"]
    dependency_import_map: dict[str, str] = {}

    def check_dependencies(self) -> tuple[bool, list[str]]:
        """
        Web page conversion can run without optional extractor deps.

        ``trafilatura`` improves quality, but fallback extraction keeps the
        feature usable when it is not installed.
        """
        return True, []

    # ------------------------------------------------------------------
    # URL helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_url(url: str) -> str:
        """Ensure URL has a scheme and strip whitespace.

        Args:
            url: Raw URL string.

        Returns:
            Cleaned URL with ``https://`` scheme if none present.
        """
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        return url

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Extract the domain/hostname from a URL.

        Args:
            url: Full URL.

        Returns:
            Hostname string (e.g. ``"example.com"``).
        """
        parsed = urlparse(url)
        return (parsed.hostname or "unknown").lower().replace("www.", "")

    def can_handle_source(self, source_url: str) -> bool:
        """Check if this converter can handle the given URL.

        Accepts any HTTP/HTTPS URL that is **not** a YouTube URL (which
        is handled by :class:`YouTubeConverter`).

        Args:
            source_url: URL to check.

        Returns:
            True if URL is HTTP(S) and not YouTube.
        """
        url_lower = source_url.lower().strip()
        if not (url_lower.startswith("http://") or url_lower.startswith("https://")):
            return False

        # Defer YouTube URLs to the YouTube converter
        parsed = urlparse(url_lower)
        hostname = (parsed.hostname or "").replace("www.", "")
        if hostname in ("youtube.com", "m.youtube.com", "youtu.be"):
            return False

        return True

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    def fetch_and_convert(
        self,
        source_url: str,
        output_dir: Path,
    ) -> Optional[Path]:
        """Fetch a web page and convert its content to Markdown.

        Strategy:
        1. Fetch HTML via ``httpx``.
        2. Extract main article text via ``trafilatura`` (with Markdown
           output and metadata).
        3. Fall back to basic HTML stripping if trafilatura fails.

        Args:
            source_url: Web page URL.
            output_dir: Directory to write the output file.

        Returns:
            Path to the generated Markdown file, or None on failure.
        """
        source_url = self._normalise_url(source_url)

        # --- fetch HTML ---------------------------------------------------
        html = self._fetch_html(source_url)
        if html is None:
            return None

        # --- extract content via trafilatura ------------------------------
        article_text, traf_metadata = self._extract_with_trafilatura(html, source_url)

        # --- fallback: basic extraction -----------------------------------
        if not article_text:
            article_text = self._basic_extract(html)

        if not article_text or not article_text.strip():
            logger.error(f"No content could be extracted from {source_url}")
            return None

        # --- fetch page metadata ------------------------------------------
        metadata = self._build_metadata(source_url, traf_metadata)

        # --- write markdown -----------------------------------------------
        markdown = self._format_markdown(
            metadata=metadata,
            content=article_text,
            source_url=source_url,
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        url_hash = hashlib.sha256(source_url.encode()).hexdigest()[:12]
        title_slug = self._slugify(metadata.get("title", self._extract_domain(source_url)))
        filename = f"{title_slug}_{url_hash}.md"
        output_path = output_dir / filename

        output_path.write_text(markdown, encoding="utf-8")
        return output_path

    def get_metadata(self, source_url: str) -> dict:
        """Get metadata for a web page.

        Performs a lightweight fetch (HEAD request for basic info, or
        full GET + trafilatura for title/author/date extraction).

        Args:
            source_url: Web page URL.

        Returns:
            Dict with page metadata.
        """
        source_url = self._normalise_url(source_url)
        html = self._fetch_html(source_url)
        if html is None:
            return {
                "status": "error",
                "source_url": source_url,
                "source_type": self.source_type,
                "message": "Failed to fetch page.",
            }

        _, traf_metadata = self._extract_with_trafilatura(html, source_url)
        metadata = self._build_metadata(source_url, traf_metadata)
        metadata["status"] = "ok"
        metadata["source_type"] = self.source_type
        metadata["source_url"] = source_url
        return metadata

    def get_implementation_status(self) -> dict:
        """Get detailed implementation status."""
        base_status = super().get_implementation_status()
        base_status.update(
            {
                "source_type": self.source_type,
                "url_patterns": self.url_patterns,
                "features": [
                    "HTML fetching via httpx",
                    "Article text extraction via trafilatura",
                    "Metadata extraction (title, author, date)",
                    "Clean Markdown output",
                    "Fallback to basic HTML stripping",
                ],
            }
        )
        return base_status

    # ------------------------------------------------------------------
    # HTML fetching
    # ------------------------------------------------------------------

    @staticmethod
    def _fetch_html(url: str) -> Optional[str]:
        """Fetch the HTML content of a URL via httpx.

        Args:
            url: Fully qualified URL.

        Returns:
            HTML string, or None on failure.
        """
        try:
            import httpx
        except ImportError:
            logger.error("httpx is not installed (should be a core dependency).")
            return None

        try:
            with httpx.Client(
                follow_redirects=True,
                timeout=_REQUEST_TIMEOUT,
                headers={"User-Agent": _USER_AGENT},
            ) as client:
                response = client.get(url)
                response.raise_for_status()

                # Guard against huge pages
                content_length = len(response.content)
                if content_length > _MAX_HTML_BYTES:
                    logger.warning(
                        f"Page too large ({content_length / 1024 / 1024:.1f} MB), "
                        f"truncating to {_MAX_HTML_BYTES / 1024 / 1024:.0f} MB."
                    )
                    return response.text[:_MAX_HTML_BYTES]

                return response.text

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching {url}: {e.response.status_code}")
        except httpx.TimeoutException:
            logger.error(f"Timeout fetching {url}")
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")

        return None

    # ------------------------------------------------------------------
    # Content extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_with_trafilatura(
        html: str,
        url: str,
    ) -> tuple[Optional[str], Optional[dict]]:
        """Extract main article text and metadata using trafilatura.

        Args:
            html: Raw HTML string.
            url: Source URL (used for metadata hints).

        Returns:
            Tuple of (extracted_text, metadata_dict). Either may be None.
        """
        try:
            import trafilatura
        except ImportError:
            logger.debug("trafilatura not installed, skipping.")
            return None, None

        try:
            # Extract text in Markdown format
            text = trafilatura.extract(
                html,
                url=url,
                output_format="markdown",
                include_links=True,
                include_tables=True,
                include_images=False,
                include_comments=False,
                favor_recall=True,
            )

            # Extract metadata separately
            metadata = trafilatura.extract_metadata(html, default_url=url)
            meta_dict: Optional[dict] = None
            if metadata:
                meta_dict = {
                    "title": metadata.title or "",
                    "author": metadata.author or "",
                    "date": str(metadata.date) if metadata.date else "",
                    "description": metadata.description or "",
                    "sitename": metadata.sitename or "",
                    "categories": list(metadata.categories) if metadata.categories else [],
                    "tags": list(metadata.tags) if metadata.tags else [],
                }

            return text, meta_dict

        except Exception as e:
            logger.debug(f"trafilatura extraction failed: {e}")
            return None, None

    @staticmethod
    def _basic_extract(html: str) -> Optional[str]:
        """Very basic fallback: strip HTML tags and collapse whitespace.

        Only used when trafilatura is unavailable or fails.

        Args:
            html: Raw HTML string.

        Returns:
            Plain text extracted from HTML, or None.
        """
        try:
            # Remove script and style blocks
            text = re.sub(
                r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE
            )
            # Remove all HTML tags
            text = re.sub(r"<[^>]+>", " ", text)
            # Decode common HTML entities
            text = text.replace("&amp;", "&")
            text = text.replace("&lt;", "<")
            text = text.replace("&gt;", ">")
            text = text.replace("&quot;", '"')
            text = text.replace("&#39;", "'")
            text = text.replace("&nbsp;", " ")
            # Collapse whitespace
            text = re.sub(r"\s+", " ", text).strip()
            # Try to add paragraph breaks at sentence boundaries (heuristic)
            text = re.sub(r"\. ([A-Z])", r".\n\n\1", text)

            if len(text) < 50:
                return None

            return text

        except Exception as e:
            logger.debug(f"Basic extraction failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Metadata building
    # ------------------------------------------------------------------

    @staticmethod
    def _build_metadata(source_url: str, traf_metadata: Optional[dict] = None) -> dict:
        """Build a unified metadata dict from trafilatura output and URL.

        Args:
            source_url: The source URL.
            traf_metadata: Metadata dict from trafilatura, or None.

        Returns:
            Merged metadata dict.
        """
        parsed = urlparse(source_url)
        domain = (parsed.hostname or "unknown").lower().replace("www.", "")

        metadata: dict = {
            "title": "",
            "author": "",
            "date": "",
            "description": "",
            "sitename": domain,
            "domain": domain,
            "url_path": parsed.path or "/",
        }

        if traf_metadata:
            for key in ("title", "author", "date", "description", "sitename", "categories", "tags"):
                val = traf_metadata.get(key)
                if val:
                    metadata[key] = val

        # Fallback title: use domain + path
        if not metadata.get("title"):
            path_part = parsed.path.rstrip("/").split("/")[-1] if parsed.path else ""
            if path_part:
                # Clean up slug-style paths
                path_part = path_part.replace("-", " ").replace("_", " ")
                path_part = re.sub(r"\.\w+$", "", path_part)  # remove extension
                metadata["title"] = f"{path_part.title()} — {domain}"
            else:
                metadata["title"] = domain

        return metadata

    # ------------------------------------------------------------------
    # Markdown formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _format_markdown(
        metadata: dict,
        content: str,
        source_url: str,
    ) -> str:
        """Format extracted content and metadata as Markdown.

        Args:
            metadata: Page metadata dict.
            content: Extracted article text (may already be Markdown).
            source_url: Original page URL.

        Returns:
            Markdown-formatted string.
        """
        title = metadata.get("title", "Web Page")

        lines: list[str] = []
        lines.append(f"# {title}")
        lines.append("")
        lines.append("---")
        lines.append("source_type: webpage")
        lines.append(f"source_url: `{source_url}`")

        domain = metadata.get("domain", "")
        if domain:
            lines.append(f"domain: {domain}")

        sitename = metadata.get("sitename", "")
        if sitename and sitename != domain:
            lines.append(f"site: {sitename}")

        author = metadata.get("author", "")
        if author:
            lines.append(f"author: {author}")

        date = metadata.get("date", "")
        if date:
            lines.append(f"date: {date}")

        description = metadata.get("description", "")
        if description:
            lines.append(f"description: {description[:200]}")

        categories = metadata.get("categories", [])
        if categories:
            lines.append(f"categories: {', '.join(categories)}")

        tags = metadata.get("tags", [])
        if tags:
            lines.append(f"tags: {', '.join(tags)}")

        lines.append(f"fetched_at: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("---")
        lines.append("")

        # Content body
        lines.append("## Content")
        lines.append("")
        lines.append(content.strip())
        lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _slugify(text: str, max_length: int = 50) -> str:
        """Create a filesystem-safe slug from text.

        Args:
            text: Input text.
            max_length: Maximum slug length.

        Returns:
            Lowercase slug with only alphanumeric and hyphens.
        """
        text = text.lower().strip()
        text = re.sub(r"[^\w\s-]", "", text)
        text = re.sub(r"[\s_]+", "-", text)
        text = re.sub(r"-+", "-", text).strip("-")
        return text[:max_length] if text else "webpage"
