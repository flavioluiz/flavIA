"""Tests for video frame extraction and description functionality."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from flavia.content.converters.video_frame_extractor import (
    _format_frame_filename,
    _seconds_to_timestamp,
    _timestamp_to_seconds,
    describe_frames,
    extract_and_describe_video_frames,
    extract_frames_at_timestamps,
    format_frame_description_markdown,
    parse_transcript_timestamps,
    select_timestamps,
)


class TestTimestampConversions:
    """Test timestamp conversion utilities."""

    def test_timestamp_to_seconds_mmss(self):
        assert _timestamp_to_seconds("05:30") == 330.0
        assert _timestamp_to_seconds("00:30") == 30.0
        assert _timestamp_to_seconds("60:00") == 3600.0

    def test_timestamp_to_seconds_hhmmss(self):
        assert _timestamp_to_seconds("01:30:45") == 5445.0
        assert _timestamp_to_seconds("00:01:30") == 90.0

    def test_timestamp_to_seconds_invalid(self):
        assert _timestamp_to_seconds("") is None
        assert _timestamp_to_seconds("invalid") is None

    def test_seconds_to_timestamp(self):
        assert _seconds_to_timestamp(330.0) == "05:30"
        assert _seconds_to_timestamp(30.0) == "00:30"
        assert _seconds_to_timestamp(3665.0) == "01:01:05"

    def test_format_frame_filename(self):
        assert _format_frame_filename(330.0) == "frame_05m30s.jpg"
        assert _format_frame_filename(30.0) == "frame_00m30s.jpg"
        assert _format_frame_filename(3665.0) == "frame_01h01m05s.jpg"


class TestParseTranscriptTimestamps:
    """Test parsing of transcript timestamps."""

    def test_parse_basic_timestamps(self):
        transcript = "[0:30 - 2:45] Hello world\n[5:00 - 7:30] Another segment\n"
        timestamps = parse_transcript_timestamps(transcript)
        assert len(timestamps) == 2
        assert timestamps[0] == (30.0, 165.0)
        assert timestamps[1] == (300.0, 450.0)

    def test_parse_timestamps_with_hours(self):
        transcript = "[1:30:45 - 02:00:00] Long video content"
        timestamps = parse_transcript_timestamps(transcript)
        assert len(timestamps) == 1
        assert timestamps[0] == (5445.0, 7200.0)

    def test_parse_no_timestamps(self):
        transcript = "No timestamps here"
        timestamps = parse_transcript_timestamps(transcript)
        assert len(timestamps) == 0

    def test_parse_malformed_timestamps(self):
        transcript = "[invalid - also_invalid] Text"
        timestamps = parse_transcript_timestamps(transcript)
        assert len(timestamps) == 0


class TestSelectTimestamps:
    """Test timestamp selection for frame extraction."""

    def test_select_every_n(self):
        timestamps = [(30, 60), (60, 90), (90, 120), (120, 150), (150, 180)]
        selected = select_timestamps(timestamps, interval=2, max_frames=20)
        assert len(selected) == 3
        assert selected == [30.0, 90.0, 150.0]

    def test_select_with_max_frames_limit(self):
        timestamps = [(30, 60), (60, 90), (90, 120), (120, 150), (150, 180)]
        selected = select_timestamps(timestamps, interval=1, max_frames=3)
        assert len(selected) == 3
        assert selected == [30.0, 60.0, 90.0]

    def test_select_empty_list(self):
        selected = select_timestamps([], interval=10, max_frames=20)
        assert len(selected) == 0

    def test_select_interval_larger_than_list(self):
        timestamps = [(30, 60), (60, 90), (90, 120)]
        selected = select_timestamps(timestamps, interval=10, max_frames=20)
        assert len(selected) == 1
        assert selected == [30.0]


class TestFormatFrameDescriptionMarkdown:
    """Test markdown formatting for frame descriptions."""

    def test_basic_formatting(self, tmp_path):
        frame_path = tmp_path / "frame_05m30s.jpg"
        video_path = tmp_path / "video.mp4"
        timestamp = 330.0
        description = "A person speaking in a classroom setting."

        md = format_frame_description_markdown(
            frame_path, video_path, timestamp, description, "test-model"
        )

        assert "# Visual Frame at 05:30" in md
        assert f"video_source: `{video_path.name}`" in md
        assert f"frame_file: `{frame_path.name}`" in md
        assert "timestamp: 05:30" in md
        assert "vision_model: test-model" in md
        assert "## Description" in md
        assert description in md


class TestExtractFramesAtTimestamps:
    """Test frame extraction from videos."""

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_extract_frames_success(self, mock_run, mock_which, tmp_path):
        mock_which.return_value = True
        video_path = tmp_path / "test.mp4"
        timestamps = [30.0, 60.0]

        def _fake_run(cmd, capture_output, text, timeout):
            Path(cmd[-1]).write_bytes(b"frame")
            return MagicMock(returncode=0, stderr="")

        mock_run.side_effect = _fake_run

        frame_dir = tmp_path / "frames"
        extracted = extract_frames_at_timestamps(video_path, timestamps, frame_dir)

        assert len(extracted) == 2
        assert extracted[0][1] == 30.0
        assert extracted[1][1] == 60.0
        assert extracted[0][0].exists()
        assert extracted[1][0].exists()
        assert mock_run.call_count == 2

    @patch("shutil.which")
    def test_extract_frames_no_ffmpeg(self, mock_which, tmp_path):
        mock_which.return_value = None
        video_path = tmp_path / "test.mp4"
        timestamps = [30.0]

        with pytest.raises(RuntimeError, match="ffmpeg is required"):
            extract_frames_at_timestamps(video_path, timestamps, tmp_path)

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_extract_frames_partial_failure(self, mock_run, mock_which, tmp_path):
        mock_which.return_value = True
        video_path = tmp_path / "test.mp4"
        timestamps = [30.0, 60.0, 90.0]

        results = [0, 1, 0]

        def _fake_run(cmd, capture_output, text, timeout):
            return_code = results.pop(0)
            if return_code == 0:
                Path(cmd[-1]).write_bytes(b"frame")
            return MagicMock(returncode=return_code, stderr="ffmpeg error")

        mock_run.side_effect = _fake_run

        frame_dir = tmp_path / "frames"
        extracted = extract_frames_at_timestamps(video_path, timestamps, frame_dir)

        assert len(extracted) == 2
        assert extracted[0][1] == 30.0
        assert extracted[1][1] == 90.0


class TestDescribeFrames:
    """Test frame description generation."""

    def test_describe_frames_success(self, tmp_path):
        mock_image_converter = MagicMock()
        mock_image_converter.extract_text.return_value = "A person talking."
        mock_image_converter.settings = MagicMock()
        mock_image_converter.settings.image_vision_model = "test-model"

        frame_paths = [tmp_path / "frame_05m30s.jpg", tmp_path / "frame_10m00s.jpg"]
        timestamps = [330.0, 600.0]
        frame_items = list(zip(frame_paths, timestamps))
        video_path = tmp_path / "video.mp4"

        for frame_path in frame_paths:
            frame_path.write_text("dummy image data")

        description_dir = tmp_path / "descriptions"
        description_files = describe_frames(
            frame_items, description_dir, video_path, mock_image_converter
        )

        assert len(description_files) == 2
        assert all(path.exists() for path, _ in description_files)
        assert [timestamp for _, timestamp in description_files] == timestamps

        first_desc = description_files[0][0].read_text()
        assert "# Visual Frame at 05:30" in first_desc
        assert "A person talking." in first_desc

    def test_describe_frames_mixed_success(self, tmp_path):
        mock_image_converter = MagicMock()
        mock_image_converter.extract_text.side_effect = [
            "First description.",
            None,
            "Third description.",
        ]
        mock_image_converter.settings = MagicMock()
        mock_image_converter.settings.image_vision_model = "test-model"

        frame_paths = [tmp_path / f"frame_{i}.jpg" for i in range(3)]
        timestamps = [30.0, 60.0, 90.0]
        frame_items = list(zip(frame_paths, timestamps))
        video_path = tmp_path / "video.mp4"

        for frame_path in frame_paths:
            frame_path.write_text("dummy image data")

        description_dir = tmp_path / "descriptions"
        description_files = describe_frames(
            frame_items, description_dir, video_path, mock_image_converter
        )

        assert len(description_files) == 2
        assert [timestamp for _, timestamp in description_files] == [30.0, 90.0]


class TestExtractAndDescribeVideoFrames:
    """Test end-to-end frame extraction and description."""

    def test_empty_transcript(self, tmp_path):
        mock_image_converter = MagicMock()
        video_path = tmp_path / "video.mp4"
        transcript = "No timestamps here"

        result, timestamps = extract_and_describe_video_frames(
            video_path, transcript, tmp_path, mock_image_converter
        )

        assert len(result) == 0
        assert len(timestamps) == 0

    @patch("flavia.content.converters.video_frame_extractor.extract_frames_at_timestamps")
    def test_end_to_end_success(self, mock_extract, tmp_path):
        mock_image_converter = MagicMock()
        video_path = tmp_path / "video.mp4"
        transcript = (
            "[0:30 - 2:00] Introduction\n[5:00 - 7:00] Main topic\n[10:00 - 12:00] Conclusion\n"
        )

        frame1 = tmp_path / "frame_05m00s.jpg"
        frame2 = tmp_path / "frame_10m00s.jpg"
        frame1.write_text("dummy1")
        frame2.write_text("dummy2")
        mock_extract.return_value = [(frame1, 300.0), (frame2, 600.0)]

        mock_image_converter.extract_text.side_effect = [
            "First frame content",
            "Second frame content",
        ]
        mock_image_converter.settings = MagicMock()
        mock_image_converter.settings.image_vision_model = "test-model"

        result, timestamps = extract_and_describe_video_frames(
            video_path, transcript, tmp_path, mock_image_converter, interval=1, max_frames=20
        )

        assert len(result) == 2
        assert timestamps == [300.0, 600.0]
        assert all(f.exists() for f in result)

        first_desc = result[0].read_text()
        assert "First frame content" in first_desc

    @patch("flavia.content.converters.video_frame_extractor.extract_frames_at_timestamps")
    def test_preserves_timestamp_mapping_on_partial_extraction(self, mock_extract, tmp_path):
        mock_image_converter = MagicMock()
        video_path = tmp_path / "video.mp4"
        transcript = "[0:30 - 2:00] A\n[5:00 - 7:00] B\n[10:00 - 12:00] C\n"

        frame1 = tmp_path / "frame_00m30s.jpg"
        frame3 = tmp_path / "frame_10m00s.jpg"
        frame1.write_text("dummy1")
        frame3.write_text("dummy3")
        mock_extract.return_value = [(frame1, 30.0), (frame3, 600.0)]

        mock_image_converter.extract_text.side_effect = [
            "Frame A",
            "Frame C",
        ]
        mock_image_converter.settings = MagicMock()
        mock_image_converter.settings.image_vision_model = "test-model"

        _, timestamps = extract_and_describe_video_frames(
            video_path, transcript, tmp_path, mock_image_converter, interval=1, max_frames=20
        )

        assert timestamps == [30.0, 600.0]
