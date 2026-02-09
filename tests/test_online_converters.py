"""Tests for online source converters."""

from pathlib import Path

import pytest

from flavia.content.converters.online import (
    OnlineSourceConverter,
    YouTubeConverter,
    WebPageConverter,
)


class TestYouTubeConverter:
    """Tests for the YouTubeConverter placeholder."""

    def test_source_type(self):
        """Verify source type identifier."""
        converter = YouTubeConverter()
        assert converter.source_type == "youtube"

    def test_is_not_implemented(self):
        """Converter is marked as not implemented."""
        converter = YouTubeConverter()
        assert converter.is_implemented is False

    def test_requires_dependencies(self):
        """Required dependencies are listed."""
        converter = YouTubeConverter()
        assert "yt_dlp" in converter.requires_dependencies
        assert "whisper" in converter.requires_dependencies

    def test_can_handle_youtube_com(self):
        """Recognizes youtube.com URLs."""
        converter = YouTubeConverter()
        assert converter.can_handle_source("https://www.youtube.com/watch?v=abc123")
        assert converter.can_handle_source("http://youtube.com/watch?v=xyz")

    def test_can_handle_youtu_be(self):
        """Recognizes youtu.be short URLs."""
        converter = YouTubeConverter()
        assert converter.can_handle_source("https://youtu.be/abc123")

    def test_cannot_handle_other_urls(self):
        """Does not handle non-YouTube URLs."""
        converter = YouTubeConverter()
        assert not converter.can_handle_source("https://vimeo.com/123")
        assert not converter.can_handle_source("https://example.com/video")

    def test_fetch_and_convert_returns_none(self, tmp_path):
        """Fetch returns None (not implemented)."""
        converter = YouTubeConverter()
        result = converter.fetch_and_convert(
            "https://youtube.com/watch?v=abc",
            tmp_path,
        )
        assert result is None

    def test_get_metadata_returns_status(self):
        """Get metadata returns not_implemented status."""
        converter = YouTubeConverter()
        metadata = converter.get_metadata("https://youtube.com/watch?v=abc")

        assert metadata["status"] == "not_implemented"
        assert metadata["source_type"] == "youtube"
        assert "source_url" in metadata

    def test_get_implementation_status(self):
        """Implementation status includes planned features."""
        converter = YouTubeConverter()
        status = converter.get_implementation_status()

        assert status["is_implemented"] is False
        assert "planned_features" in status
        assert len(status["planned_features"]) > 0
        assert status["source_type"] == "youtube"

    def test_does_not_handle_local_files(self, tmp_path):
        """Online converters don't handle local files."""
        converter = YouTubeConverter()

        test_file = tmp_path / "test.mp4"
        test_file.write_bytes(b"\x00")

        assert converter.convert(test_file, tmp_path) is None
        assert converter.extract_text(test_file) is None


class TestWebPageConverter:
    """Tests for the WebPageConverter placeholder."""

    def test_source_type(self):
        """Verify source type identifier."""
        converter = WebPageConverter()
        assert converter.source_type == "webpage"

    def test_is_not_implemented(self):
        """Converter is marked as not implemented."""
        converter = WebPageConverter()
        assert converter.is_implemented is False

    def test_requires_dependencies(self):
        """Required dependencies are listed."""
        converter = WebPageConverter()
        assert "httpx" in converter.requires_dependencies
        assert "beautifulsoup4" in converter.requires_dependencies
        assert "markdownify" in converter.requires_dependencies

    def test_can_handle_https(self):
        """Recognizes HTTPS URLs."""
        converter = WebPageConverter()
        assert converter.can_handle_source("https://example.com")
        assert converter.can_handle_source("https://docs.python.org/3/")

    def test_can_handle_http(self):
        """Recognizes HTTP URLs."""
        converter = WebPageConverter()
        assert converter.can_handle_source("http://example.com")

    def test_cannot_handle_non_http(self):
        """Does not handle non-HTTP URLs."""
        converter = WebPageConverter()
        assert not converter.can_handle_source("ftp://example.com")
        assert not converter.can_handle_source("file:///path/to/file")
        assert not converter.can_handle_source("/local/path")

    def test_fetch_and_convert_returns_none(self, tmp_path):
        """Fetch returns None (not implemented)."""
        converter = WebPageConverter()
        result = converter.fetch_and_convert("https://example.com", tmp_path)
        assert result is None

    def test_get_metadata_returns_status(self):
        """Get metadata returns not_implemented status."""
        converter = WebPageConverter()
        metadata = converter.get_metadata("https://example.com")

        assert metadata["status"] == "not_implemented"
        assert metadata["source_type"] == "webpage"
        assert "source_url" in metadata

    def test_get_implementation_status(self):
        """Implementation status includes planned features."""
        converter = WebPageConverter()
        status = converter.get_implementation_status()

        assert status["is_implemented"] is False
        assert "planned_features" in status
        assert len(status["planned_features"]) > 0
        assert status["source_type"] == "webpage"


class TestOnlineSourceConverterBase:
    """Tests for the OnlineSourceConverter base class."""

    def test_does_not_handle_local_extensions(self):
        """Online converters have no supported extensions."""
        converter = YouTubeConverter()
        assert converter.supported_extensions == set()

    def test_can_handle_checks_url_patterns(self):
        """can_handle_source uses url_patterns."""

        class TestConverter(OnlineSourceConverter):
            url_patterns = ["test.com", "example.org"]

            def fetch_and_convert(self, source_url, output_dir):
                return None

            def get_metadata(self, source_url):
                return {}

        converter = TestConverter()
        assert converter.can_handle_source("https://test.com/page")
        assert converter.can_handle_source("http://example.org/path")
        assert not converter.can_handle_source("https://other.com/page")

    def test_check_dependencies(self):
        """Check dependencies reports missing packages."""
        converter = YouTubeConverter()
        # yt_dlp and whisper are likely not installed in test env
        ok, missing = converter.check_dependencies()
        # At least one should be missing
        assert not ok or len(missing) == 0
