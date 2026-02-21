"""Tests for online source converters."""

import importlib.util
import json
import httpx

from flavia.content.converters.online import (
    OnlineSourceConverter,
    WebPageConverter,
    YouTubeConverter,
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
        assert (
            converter.parse_video_id("https://music.youtube.com/watch?v=dQw4w9WgXcQ")
            == "dQw4w9WgXcQ"
        )
        assert converter.parse_video_id("not-a-url") is None

    def test_excludes_youtube_from_webpage(self):
        """WebPageConverter does not handle YouTube URLs."""
        webpage = WebPageConverter()
        assert not webpage.can_handle_source("https://www.youtube.com/watch?v=abc123")
        assert not webpage.can_handle_source("https://youtu.be/abc123")

    def test_parse_json3_captions(self):
        """Parses JSON3 captions into timestamped transcript."""
        payload = json.dumps(
            {
                "events": [
                    {
                        "tStartMs": 0,
                        "dDurationMs": 1200,
                        "segs": [{"utf8": "Singular "}, {"utf8": "value decomposition"}],
                    }
                ]
            }
        )
        transcript = YouTubeConverter._parse_json3_captions(payload)
        assert transcript is not None
        assert "[00:00 - 00:01] Singular value decomposition" in transcript

    def test_parse_text_captions(self):
        """Parses VTT/SRT-like captions into timestamped transcript."""
        payload = """WEBVTT

00:00.000 --> 00:02.000
First line

00:02.000 --> 00:04.000
Second line
"""
        transcript = YouTubeConverter._parse_text_captions(payload)
        assert transcript is not None
        assert "[00:00 - 00:02] First line" in transcript
        assert "[00:02 - 00:04] Second line" in transcript

    def test_fetch_and_convert_prefers_ytdlp_captions_before_audio(self, tmp_path, monkeypatch):
        """Caption-track fallback should run before audio transcription fallback."""
        converter = YouTubeConverter()
        source_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

        monkeypatch.setattr(
            YouTubeConverter,
            "_get_transcript_api",
            staticmethod(lambda _video_id: None),
        )
        monkeypatch.setattr(
            YouTubeConverter,
            "_get_transcript_ytdlp_captions",
            staticmethod(lambda _source_url: "[00:00 - 00:02] Caption transcript"),
        )
        monkeypatch.setattr(
            YouTubeConverter,
            "_download_and_transcribe_audio",
            staticmethod(
                lambda _source_url: (_ for _ in ()).throw(AssertionError("Should not run"))
            ),
        )
        monkeypatch.setattr(
            YouTubeConverter,
            "_fetch_metadata_ytdlp",
            staticmethod(lambda _source_url: {"title": "SVD Overview"}),
        )

        output = converter.fetch_and_convert(source_url, tmp_path)
        assert output is not None
        content = output.read_text(encoding="utf-8")
        assert "transcript_source: yt-dlp subtitle track" in content
        assert "Caption transcript" in content

    def test_extract_and_describe_frames_uses_video_converter(self, tmp_path, monkeypatch):
        """YouTube frame extraction should delegate to VideoConverter and cleanup temp video."""
        converter = YouTubeConverter()
        source_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        temp_video = tmp_path / "video_dQw4w9WgXcQ.mp4"
        temp_video.write_bytes(b"video-bytes")
        desc_file = tmp_path / "frame_00m00s.md"
        desc_file.write_text("frame description")

        monkeypatch.setattr(
            converter,
            "download_video",
            lambda _source_url, _output_dir: temp_video,
        )

        class _FakeVideoConverter:
            def __init__(self, _settings=None):
                pass

            def extract_and_describe_frames(
                self,
                transcript,
                video_path,
                base_output_dir,
                interval,
                max_frames,
            ):
                assert transcript == "[00:00 - 00:02] test"
                assert video_path == temp_video
                assert base_output_dir == tmp_path
                assert interval > 0
                assert max_frames > 0
                return [desc_file], [0.0]

        monkeypatch.setattr(
            "flavia.content.converters.video_converter.VideoConverter",
            _FakeVideoConverter,
        )

        result_paths, result_timestamps = converter.extract_and_describe_frames(
            source_url=source_url,
            transcript="[00:00 - 00:02] test",
            base_output_dir=tmp_path,
        )

        assert result_paths == [desc_file]
        assert result_timestamps == [0.0]
        assert not temp_video.exists()


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

    def test_fetch_html_blocks_localhost(self, monkeypatch):
        """Fetching localhost URLs is blocked before any network request."""
        converter = WebPageConverter()

        class _NoNetworkClient:
            def __init__(self, *args, **kwargs):
                raise AssertionError("httpx.Client should not be instantiated")

        monkeypatch.setattr(httpx, "Client", _NoNetworkClient)

        assert converter._fetch_html("http://localhost:8000/private") is None

    def test_fetch_html_blocks_private_ip(self, monkeypatch):
        """Fetching private/link-local IP URLs is blocked before network request."""
        converter = WebPageConverter()

        class _NoNetworkClient:
            def __init__(self, *args, **kwargs):
                raise AssertionError("httpx.Client should not be instantiated")

        monkeypatch.setattr(httpx, "Client", _NoNetworkClient)

        assert converter._fetch_html("http://169.254.169.254/latest/meta-data") is None

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

    def test_youtube_cookie_options_from_env(self, monkeypatch):
        """yt-dlp cookie options can be injected from environment variables."""
        opts = {}
        monkeypatch.setenv("FLAVIA_YTDLP_COOKIEFILE", "/tmp/cookies.txt")
        monkeypatch.setenv("FLAVIA_YTDLP_COOKIES_FROM_BROWSER", "chrome")

        YouTubeConverter._apply_ytdlp_cookie_options(opts)

        assert opts["cookiefile"] == "/tmp/cookies.txt"
        assert opts["cookiesfrombrowser"] == ("chrome",)
