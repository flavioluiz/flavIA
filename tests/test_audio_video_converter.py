"""Tests for audio/video transcription converters and Mistral key manager."""

import os
import sys
from types import ModuleType
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from flavia.content.converters.audio_converter import (
    AudioConverter,
    _format_file_size,
    _format_timestamp,
)
from flavia.content.converters.mistral_key_manager import (
    _append_key_to_env,
    _read_key_from_env_file,
    get_mistral_api_key,
)
from flavia.content.converters.video_converter import VideoConverter


# ============================================================================
# Mistral Key Manager tests
# ============================================================================


class TestGetMistralApiKey:
    """Tests for get_mistral_api_key()."""

    def test_returns_key_from_environ(self, monkeypatch):
        monkeypatch.setenv("MISTRAL_API_KEY", "test-key-123")
        assert get_mistral_api_key(interactive=False) == "test-key-123"

    def test_returns_none_when_no_key_and_non_interactive(self, monkeypatch):
        monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
        with patch(
            "flavia.content.converters.mistral_key_manager._scan_env_files",
            return_value=None,
        ):
            assert get_mistral_api_key(interactive=False) is None

    def test_finds_key_in_env_file(self, monkeypatch, tmp_path):
        monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text("MISTRAL_API_KEY=from-file-key\n")

        with patch(
            "flavia.content.converters.mistral_key_manager._scan_env_files",
            return_value="from-file-key",
        ):
            key = get_mistral_api_key(interactive=False)
            assert key == "from-file-key"

    def test_strips_whitespace_from_key(self, monkeypatch):
        monkeypatch.setenv("MISTRAL_API_KEY", "  spaced-key  ")
        assert get_mistral_api_key(interactive=False) == "spaced-key"

    def test_empty_key_treated_as_missing(self, monkeypatch):
        monkeypatch.setenv("MISTRAL_API_KEY", "   ")
        with patch(
            "flavia.content.converters.mistral_key_manager._scan_env_files",
            return_value=None,
        ):
            assert get_mistral_api_key(interactive=False) is None


class TestReadKeyFromEnvFile:
    """Tests for _read_key_from_env_file()."""

    def test_reads_plain_key(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("MISTRAL_API_KEY=abc123\n")
        assert _read_key_from_env_file(env_file) == "abc123"

    def test_reads_quoted_key(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text('MISTRAL_API_KEY="quoted-key"\n')
        assert _read_key_from_env_file(env_file) == "quoted-key"

    def test_reads_single_quoted_key(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("MISTRAL_API_KEY='single-quoted'\n")
        assert _read_key_from_env_file(env_file) == "single-quoted"

    def test_skips_commented_line(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# MISTRAL_API_KEY=commented\n")
        assert _read_key_from_env_file(env_file) is None

    def test_returns_none_for_missing_file(self, tmp_path):
        env_file = tmp_path / "nonexistent.env"
        assert _read_key_from_env_file(env_file) is None

    def test_returns_none_for_empty_value(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("MISTRAL_API_KEY=\n")
        assert _read_key_from_env_file(env_file) is None

    def test_key_among_other_vars(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("OTHER_KEY=foo\nMISTRAL_API_KEY=target-key\nANOTHER=bar\n")
        assert _read_key_from_env_file(env_file) == "target-key"


class TestAppendKeyToEnv:
    """Tests for _append_key_to_env()."""

    def test_creates_new_file(self, tmp_path):
        env_file = tmp_path / ".env"
        _append_key_to_env(env_file, "new-key")
        content = env_file.read_text()
        assert "MISTRAL_API_KEY=new-key" in content

    def test_updates_existing_key(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("MISTRAL_API_KEY=old-key\n")
        _append_key_to_env(env_file, "new-key")
        content = env_file.read_text()
        assert "MISTRAL_API_KEY=new-key" in content
        assert "old-key" not in content

    def test_uncomments_commented_key(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("# MISTRAL_API_KEY=old\nOTHER=val\n")
        _append_key_to_env(env_file, "new-key")
        content = env_file.read_text()
        assert "MISTRAL_API_KEY=new-key" in content
        assert "# MISTRAL_API_KEY" not in content

    def test_appends_when_key_not_present(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("OTHER_VAR=hello\n")
        _append_key_to_env(env_file, "appended-key")
        content = env_file.read_text()
        assert "OTHER_VAR=hello" in content
        assert "MISTRAL_API_KEY=appended-key" in content


# ============================================================================
# AudioConverter tests
# ============================================================================


class TestAudioConverter:
    """Tests for AudioConverter."""

    def test_supported_extensions(self):
        converter = AudioConverter()
        assert ".mp3" in converter.supported_extensions
        assert ".wav" in converter.supported_extensions
        assert ".flac" in converter.supported_extensions
        assert ".m4a" in converter.supported_extensions
        assert ".opus" in converter.supported_extensions
        assert ".amr" in converter.supported_extensions

    def test_can_handle_audio_files(self):
        converter = AudioConverter()
        assert converter.can_handle(Path("song.mp3"))
        assert converter.can_handle(Path("recording.wav"))
        assert converter.can_handle(Path("music.flac"))
        assert not converter.can_handle(Path("document.pdf"))

    def test_convert_writes_markdown(self, monkeypatch, tmp_path):
        source = tmp_path / "lecture.mp3"
        source.write_bytes(b"\xff\xfb\x90\x00")  # Fake MP3 header
        output_dir = tmp_path / ".converted"

        monkeypatch.setattr(
            AudioConverter,
            "_transcribe_audio",
            lambda _self, _path, **kw: "[00:00 - 00:15] Hello world.",
        )

        result = AudioConverter().convert(source, output_dir)

        assert result is not None
        assert result.exists()
        content = result.read_text()
        assert "# lecture" in content
        assert "Hello world" in content
        assert "MP3" in content

    def test_convert_returns_none_on_failure(self, monkeypatch, tmp_path):
        source = tmp_path / "bad.mp3"
        source.write_bytes(b"\x00")
        output_dir = tmp_path / ".converted"

        monkeypatch.setattr(
            AudioConverter,
            "_transcribe_audio",
            lambda _self, _path, **kw: None,
        )

        result = AudioConverter().convert(source, output_dir)
        assert result is None

    def test_extract_text_delegates_to_transcribe(self, monkeypatch, tmp_path):
        source = tmp_path / "clip.wav"
        source.write_bytes(b"RIFF" + b"\x00" * 40)

        monkeypatch.setattr(
            AudioConverter,
            "_transcribe_audio",
            lambda _self, _path, **kw: "Transcribed text here",
        )

        text = AudioConverter().extract_text(source)
        assert text == "Transcribed text here"

    def test_format_transcription_with_segments(self):
        """Test formatting when API returns segments with timestamps."""
        converter = AudioConverter()

        mock_response = MagicMock()
        mock_response.model_dump_json.return_value = (
            '{"text": "Hello world", "segments": ['
            '{"start": 0.0, "end": 5.2, "text": "Hello"},'
            '{"start": 5.2, "end": 10.0, "text": "world"}'
            "]}"
        )

        result = converter._format_transcription_response(mock_response)
        assert "[00:00 - 00:05] Hello" in result
        assert "[00:05 - 00:10] world" in result

    def test_format_transcription_plain_text_fallback(self):
        """Test formatting when API returns only plain text."""
        converter = AudioConverter()

        mock_response = MagicMock()
        mock_response.model_dump_json.return_value = '{"text": "Just plain text", "segments": []}'

        result = converter._format_transcription_response(mock_response)
        assert result == "Just plain text"

    def test_format_transcription_response_attribute(self):
        """Test fallback to .text attribute when model_dump_json fails."""
        converter = AudioConverter()

        mock_response = MagicMock(spec=[])
        mock_response.text = "Fallback text"
        # model_dump_json raises AttributeError because spec=[]
        result = converter._format_transcription_response(mock_response)
        assert result == "Fallback text"

    def test_transcribe_audio_no_api_key(self, monkeypatch):
        converter = AudioConverter()

        monkeypatch.setattr(
            "flavia.content.converters.audio_converter.get_mistral_api_key",
            lambda interactive: None,
        )

        result = converter._transcribe_audio(Path("test.mp3"))
        assert result is None

    def test_transcribe_audio_http_fallback_when_sdk_has_no_audio(self, monkeypatch, tmp_path):
        converter = AudioConverter()
        source = tmp_path / "input.mp3"
        source.write_bytes(b"\xff\xfb\x90\x00")

        monkeypatch.setattr(
            "flavia.content.converters.audio_converter.get_mistral_api_key",
            lambda interactive: "test-key",
        )

        fake_module = ModuleType("mistralai")

        class FakeMistral:
            def __init__(self, api_key):
                self.api_key = api_key

        fake_module.Mistral = FakeMistral
        monkeypatch.setitem(sys.modules, "mistralai", fake_module)

        called = {}

        def fake_http(api_key, audio_file, audio_path):
            called["api_key"] = api_key
            called["audio_path"] = audio_path
            return {
                "text": "fallback",
                "segments": [{"start": 0.0, "end": 1.0, "text": "fallback text"}],
            }

        monkeypatch.setattr(AudioConverter, "_request_transcription_http", staticmethod(fake_http))

        result = converter._transcribe_audio(source, interactive=False)
        assert called["api_key"] == "test-key"
        assert called["audio_path"] == source
        assert "[00:00 - 00:01] fallback text" in result

    def test_format_transcription_with_chunks(self):
        converter = AudioConverter()
        result = converter._format_transcription_response(
            {
                "text": "chunked",
                "chunks": [
                    {"start": 0.0, "end": 2.0, "text": "first chunk"},
                    {"start": 2.0, "end": 4.0, "text": "second chunk"},
                ],
            }
        )
        assert "[00:00 - 00:02] first chunk" in result
        assert "[00:02 - 00:04] second chunk" in result


# ============================================================================
# VideoConverter tests
# ============================================================================


class TestVideoConverter:
    """Tests for VideoConverter."""

    def test_supported_extensions(self):
        converter = VideoConverter()
        assert ".mp4" in converter.supported_extensions
        assert ".avi" in converter.supported_extensions
        assert ".mkv" in converter.supported_extensions
        assert ".mov" in converter.supported_extensions
        assert ".3gp" in converter.supported_extensions
        assert ".ogv" in converter.supported_extensions

    def test_can_handle_video_files(self):
        converter = VideoConverter()
        assert converter.can_handle(Path("movie.mp4"))
        assert converter.can_handle(Path("clip.avi"))
        assert not converter.can_handle(Path("song.mp3"))
        assert not converter.can_handle(Path("doc.pdf"))

    def test_extract_text_without_ffmpeg(self, monkeypatch):
        converter = VideoConverter()

        monkeypatch.setattr(
            VideoConverter,
            "_check_ffmpeg",
            lambda _self: False,
        )

        # Should print instructions and return None
        result = converter.extract_text(Path("video.mp4"))
        assert result is None

    def test_extract_text_with_ffmpeg(self, monkeypatch, tmp_path):
        converter = VideoConverter()

        # Mock ffmpeg check
        monkeypatch.setattr(
            VideoConverter,
            "_check_ffmpeg",
            lambda _self: True,
        )

        # Mock audio extraction
        audio_file = tmp_path / "extracted.mp3"
        audio_file.write_bytes(b"\xff\xfb\x90\x00")
        monkeypatch.setattr(
            VideoConverter,
            "_extract_audio",
            lambda _self, _path: audio_file,
        )

        # Mock transcription
        monkeypatch.setattr(
            AudioConverter,
            "_transcribe_audio",
            lambda _self, _path, **kw: "Transcribed from video",
        )

        result = converter.extract_text(Path("video.mp4"))
        assert result == "Transcribed from video"

    def test_extract_text_cleanup_on_failure(self, monkeypatch, tmp_path):
        converter = VideoConverter()

        monkeypatch.setattr(VideoConverter, "_check_ffmpeg", lambda _self: True)

        audio_file = tmp_path / ".tmp_audio" / "test.mp3"
        audio_file.parent.mkdir(parents=True)
        audio_file.write_bytes(b"\xff\xfb\x90\x00")

        monkeypatch.setattr(VideoConverter, "_extract_audio", lambda _self, _path: audio_file)
        monkeypatch.setattr(
            AudioConverter,
            "_transcribe_audio",
            lambda _self, _path, **kw: None,
        )

        converter.extract_text(Path("video.mp4"))
        # Temp file should be cleaned up
        assert not audio_file.exists()

    def test_convert_writes_markdown(self, monkeypatch, tmp_path):
        source = tmp_path / "lecture.mp4"
        source.write_bytes(b"\x00" * 100)
        output_dir = tmp_path / ".converted"

        monkeypatch.setattr(
            VideoConverter,
            "extract_text",
            lambda _self, _path: "[00:00 - 01:00] Video transcription.",
        )

        result = VideoConverter().convert(source, output_dir)

        assert result is not None
        assert result.exists()
        content = result.read_text()
        assert "# lecture" in content
        assert "Video transcription" in content
        assert "MP4" in content

    def test_convert_returns_none_on_failure(self, monkeypatch, tmp_path):
        source = tmp_path / "bad.mp4"
        source.write_bytes(b"\x00")
        output_dir = tmp_path / ".converted"

        monkeypatch.setattr(VideoConverter, "extract_text", lambda _self, _path: None)

        result = VideoConverter().convert(source, output_dir)
        assert result is None

    def test_cleanup_temp_audio(self, tmp_path):
        tmp_dir = tmp_path / ".tmp_audio"
        tmp_dir.mkdir()
        audio_file = tmp_dir / "temp.mp3"
        audio_file.write_bytes(b"\x00")

        VideoConverter._cleanup_temp_audio(audio_file)

        assert not audio_file.exists()
        # Directory should also be removed if empty
        assert not tmp_dir.exists()

    def test_cleanup_temp_audio_dir_not_empty(self, tmp_path):
        tmp_dir = tmp_path / ".tmp_audio"
        tmp_dir.mkdir()
        audio_file = tmp_dir / "temp.mp3"
        audio_file.write_bytes(b"\x00")
        other_file = tmp_dir / "other.mp3"
        other_file.write_bytes(b"\x00")

        VideoConverter._cleanup_temp_audio(audio_file)

        assert not audio_file.exists()
        # Directory should remain because other_file is still there
        assert tmp_dir.exists()


# ============================================================================
# Utility tests
# ============================================================================


class TestUtilities:
    """Tests for utility helper functions."""

    def test_format_timestamp_seconds_only(self):
        assert _format_timestamp(5.0) == "00:05"

    def test_format_timestamp_minutes(self):
        assert _format_timestamp(65.0) == "01:05"

    def test_format_timestamp_hours(self):
        assert _format_timestamp(3665.0) == "01:01:05"

    def test_format_timestamp_zero(self):
        assert _format_timestamp(0.0) == "00:00"

    def test_format_file_size_bytes(self, tmp_path):
        f = tmp_path / "tiny.mp3"
        f.write_bytes(b"\x00" * 500)
        result = _format_file_size(f)
        assert "500.0 B" == result

    def test_format_file_size_kb(self, tmp_path):
        f = tmp_path / "small.mp3"
        f.write_bytes(b"\x00" * 2048)
        result = _format_file_size(f)
        assert "KB" in result

    def test_format_file_size_missing_file(self, tmp_path):
        f = tmp_path / "missing.mp3"
        assert _format_file_size(f) is None


# ============================================================================
# Registration tests
# ============================================================================


class TestRegistration:
    """Tests that audio/video converters are properly registered."""

    def test_audio_converter_registered(self):
        from flavia.content.converters import converter_registry

        assert converter_registry.get_for_extension(".mp3") is not None
        assert isinstance(converter_registry.get_for_extension(".mp3"), AudioConverter)

    def test_video_converter_registered(self):
        from flavia.content.converters import converter_registry

        assert converter_registry.get_for_extension(".mp4") is not None
        assert isinstance(converter_registry.get_for_extension(".mp4"), VideoConverter)

    def test_all_audio_extensions_registered(self):
        from flavia.content.converters import converter_registry
        from flavia.content.scanner import AUDIO_EXTENSIONS

        for ext in AUDIO_EXTENSIONS:
            converter = converter_registry.get_for_extension(ext)
            assert converter is not None, f"No converter for {ext}"
            assert isinstance(converter, AudioConverter)

    def test_all_video_extensions_registered(self):
        from flavia.content.converters import converter_registry
        from flavia.content.scanner import VIDEO_EXTENSIONS

        for ext in VIDEO_EXTENSIONS:
            converter = converter_registry.get_for_extension(ext)
            assert converter is not None, f"No converter for {ext}"
            assert isinstance(converter, VideoConverter)
