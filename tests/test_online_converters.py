"""Tests for online source converters."""

import importlib.util
from pathlib import Path

import pytest

from flavia.content.converters.online import (
    OnlineSourceConverter,
    YouTubeConverter,
    WebPageConverter,
)


class TestYouTubeConverter:
    """Tests for the YouTubeConverter."""

    def test_source_type(self):
        """Verify source type identifier."""
        converter = YouTubeConverter()
        assert converter.source_type == "youtube"

    def test_is_implemented(self):
        """Converter is marked as implemented."""
        converter = YouTubeConverter()
        assert converter.is_implemented is True

    def test_requires_dependencies(self):
        """Required dependencies are listed."""
        converter = YouTubeConverter()
        assert "yt_dlp" in converter.requires_dependencies
        assert "youtube_transcript_api" in converter.requires_dependencies

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
        assert not converter.can_handle_source("https://notyoutube.com/watch?v=dQw4w9WgXcQ")
        assert not converter.can_handle_source(
            "https://example.com/path/youtube.com/watch?v=dQw4w9WgXcQ"
        )

    def test_get_metadata_returns_source_info(self):
        """Get metadata returns source type and URL."""
        converter = YouTubeConverter()
        metadata = converter.get_metadata("https://youtube.com/watch?v=abc")

        assert metadata["source_type"] == "youtube"
        assert "source_url" in metadata

    def test_get_implementation_status(self):
        """Implementation status includes features."""
        converter = YouTubeConverter()
        status = converter.get_implementation_status()

        assert status["is_implemented"] is True
        assert "features" in status
        assert len(status["features"]) > 0
        assert status["source_type"] == "youtube"

    def test_does_not_handle_local_files(self, tmp_path):
        """Online converters don't handle local files."""
        converter = YouTubeConverter()

        test_file = tmp_path / "test.mp4"
        test_file.write_bytes(b"\x00")

        assert converter.convert(test_file, tmp_path) is None
        assert converter.extract_text(test_file) is None

    def test_extract_video_id(self):
        """Extracts video ID from various YouTube URL formats."""
        converter = YouTubeConverter()
        assert (
            converter.parse_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        )
        assert converter.parse_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        assert converter.parse_video_id("https://youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        assert converter.parse_video_id("not-a-url") is None

    def test_excludes_youtube_from_webpage(self):
        """WebPageConverter does not handle YouTube URLs."""
        webpage = WebPageConverter()
        assert not webpage.can_handle_source("https://www.youtube.com/watch?v=abc123")
        assert not webpage.can_handle_source("https://youtu.be/abc123")


class TestWebPageConverter:
    """Tests for the WebPageConverter."""

    def test_source_type(self):
        """Verify source type identifier."""
        converter = WebPageConverter()
        assert converter.source_type == "webpage"

    def test_is_implemented(self):
        """Converter is marked as implemented."""
        converter = WebPageConverter()
        assert converter.is_implemented is True

    def test_requires_dependencies(self):
        """Required dependencies are listed."""
        converter = WebPageConverter()
        assert "trafilatura" in converter.requires_dependencies

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

    def test_get_metadata_returns_source_info(self):
        """Get metadata returns source type and URL."""
        converter = WebPageConverter()
        metadata = converter.get_metadata("https://example.com")

        assert metadata["source_type"] == "webpage"
        assert "source_url" in metadata

    def test_get_implementation_status(self):
        """Implementation status includes features."""
        converter = WebPageConverter()
        status = converter.get_implementation_status()

        assert status["is_implemented"] is True
        assert "features" in status
        assert len(status["features"]) > 0
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
        """YouTube converter accepts at least one transcript backend."""
        converter = YouTubeConverter()
        ok, missing = converter.check_dependencies()
        assert ok is True or missing == ["youtube_transcript_api", "yt_dlp"]

    def test_check_dependencies_uses_import_map(self, monkeypatch):
        """YouTube dependency check passes when either backend is present."""
        converter = YouTubeConverter()

        def fake_find_spec(module_name):
            if module_name == "youtube_transcript_api":
                return object()
            return None

        monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
        ok, missing = converter.check_dependencies()

        assert ok is True
        assert missing == []

    def test_youtube_check_dependencies_fails_when_none_available(self, monkeypatch):
        """YouTube dependency check fails when both backends are unavailable."""
        converter = YouTubeConverter()

        monkeypatch.setattr(importlib.util, "find_spec", lambda _module_name: None)
        ok, missing = converter.check_dependencies()

        assert ok is False
        assert missing == ["youtube_transcript_api", "yt_dlp"]

    def test_webpage_check_dependencies_is_optional(self, monkeypatch):
        """WebPage converter remains usable without trafilatura."""
        converter = WebPageConverter()

        monkeypatch.setattr(importlib.util, "find_spec", lambda _module_name: None)
        ok, missing = converter.check_dependencies()

        assert ok is True
        assert missing == []
