"""Tests for video temporal expansion (Task 11.5)."""

import hashlib
from pathlib import Path
from unittest.mock import Mock

from flavia.content.indexer.video_retrieval import (
    _format_evidence_bundle,
    _get_all_frames_for_doc,
    _get_frames_in_range,
    _get_nearest_frames,
    _parse_timecode,
    _read_frame_from_file,
    _seconds_to_timecode,
    expand_temporal_window,
)
from flavia.content.scanner import FileEntry


def test_parse_timecode():
    """Test timecode parsing in various formats."""
    assert _parse_timecode("00:00:00") == 0.0
    assert _parse_timecode("00:00:30") == 30.0
    assert _parse_timecode("01:00:00") == 3600.0
    assert _parse_timecode("01:23:45") == 5025.0
    assert _parse_timecode("01:30") == 90.0
    assert _parse_timecode("90") == 90.0
    assert _parse_timecode("") is None
    assert _parse_timecode("invalid") is None


def test_seconds_to_timecode():
    """Test conversion from seconds to timecode string."""
    assert _seconds_to_timecode(0) == "00:00:00"
    assert _seconds_to_timecode(30) == "00:00:30"
    assert _seconds_to_timecode(90) == "00:01:30"
    assert _seconds_to_timecode(3600) == "01:00:00"
    assert _seconds_to_timecode(5025) == "01:23:45"
    assert _seconds_to_timecode(3661) == "01:01:01"


def test_read_frame_from_file(tmp_path: Path):
    """Test reading a frame description file."""
    frame_path = tmp_path / "frame_00m30s.md"
    frame_path.write_text(
        "# Visual Frame at 00:30\n\n"
        "## Description\n\n"
        "A diagram showing the convolution operation.\n"
    )

    result = _read_frame_from_file(frame_path)
    assert result is not None
    assert result["time_start"] == 30.0
    assert result["time_end"] == 30.0
    assert "convolution operation" in result["text"]


def test_read_frame_from_file_with_metadata(tmp_path: Path):
    """Test reading a frame file with markdown metadata."""
    frame_path = tmp_path / "frame_01m23s.md"
    frame_path.write_text(
        "# Visual Frame at 01:23\n\n"
        "---\n"
        "video_source: lecture.mp4\n"
        "timestamp: 01:23\n"
        "---\n\n"
        "## Description\n\n"
        "The slide shows the formula.\n"
    )

    result = _read_frame_from_file(frame_path)
    assert result is not None
    assert result["time_start"] == 83.0
    assert "formula" in result["text"]


def test_format_evidence_bundle_transcripts_only():
    """Test formatting a bundle with only transcript items."""
    transcript_items = [
        {
            "time_start": 10.0,
            "time_end": 20.0,
            "text": "First segment.",
            "modality": "video_transcript",
        },
        {
            "time_start": 25.0,
            "time_end": 35.0,
            "text": "Second segment.",
            "modality": "video_transcript",
        },
    ]
    frame_items = []

    result = _format_evidence_bundle(transcript_items, frame_items)
    assert len(result) == 2
    assert result[0]["time_display"] == "00:00:10–00:00:20"
    assert result[0]["modality_label"] == "(Audio)"
    assert result[0]["text"] == "First segment."
    assert result[1]["time_display"] == "00:00:25–00:00:35"
    assert result[1]["text"] == "Second segment."


def test_format_evidence_bundle_both_modalities():
    """Test formatting a bundle with both transcripts and frames.

    Items should be sorted chronologically across modalities.
    """
    transcript_items = [
        {
            "time_start": 5.0,
            "time_end": 10.0,
            "text": "Earlier transcript.",
            "modality": "video_transcript",
        },
        {
            "time_start": 10.0,
            "time_end": 20.0,
            "text": "First transcript.",
            "modality": "video_transcript",
        },
    ]
    frame_items = [
        {"time_start": 8.0, "time_end": 8.0, "text": "Frame B.", "modality": "video_frame"},
        {"time_start": 15.0, "time_end": 15.0, "text": "Frame A.", "modality": "video_frame"},
    ]

    result = _format_evidence_bundle(transcript_items, frame_items)
    assert len(result) == 4

    assert result[0]["time_display"] == "00:00:05–00:00:10"
    assert result[0]["modality_label"] == "(Audio)"
    assert result[0]["text"] == "Earlier transcript."

    assert result[1]["time_display"] == "00:00:08"
    assert result[1]["modality_label"] == "(Screen)"
    assert result[1]["text"] == "Frame B."

    assert result[2]["time_display"] == "00:00:10–00:00:20"
    assert result[2]["modality_label"] == "(Audio)"

    assert result[3]["time_display"] == "00:00:15"
    assert result[3]["modality_label"] == "(Screen)"
    assert result[3]["text"] == "Frame A."


def test_get_frames_in_range(tmp_path: Path):
    """Test getting frames within a time range."""
    frames = []
    for time_sec in [10.0, 30.0, 60.0, 90.0]:
        path = tmp_path / f"frame_{int(time_sec // 60):02d}m{int(time_sec % 60):02d}s.md"
        path.write_text(
            f"# Visual Frame at {_seconds_to_timecode(time_sec)}\n\n## Description\n\nFrame content.\n"
        )
        frames.append((time_sec, path))

    result = _get_frames_in_range(45.0, 8.0, frames)
    assert len(result) == 0

    result = _get_frames_in_range(30.0, 10.0, frames)
    assert len(result) == 1  # Only frame at 30.0 (within 20-40 range)


def test_get_nearest_frames(monkeypatch):
    """Test finding nearest frames before and after a center time."""
    all_frames = [
        (10.0, Path("/fake/frame_00m10s.md")),
        (20.0, Path("/fake/frame_00m20s.md")),
        (40.0, Path("/fake/frame_00m40s.md")),
        (60.0, Path("/fake/frame_01m00s.md")),
    ]

    def _mock_read_frame(p):
        stem = p.stem
        import re

        m = re.match(r"frame_(\d{2})m(\d{2})s", stem)
        if m:
            mins = int(m.group(1))
            secs = int(m.group(2))
            time_val = mins * 60 + secs
        else:
            time_val = 0.0
        return {
            "time_start": time_val,
            "time_end": time_val,
            "text": f"Frame {p.name}",
        }

    monkeypatch.setattr(
        "flavia.content.indexer.video_retrieval._read_frame_from_file", _mock_read_frame
    )

    before, after = _get_nearest_frames(35.0, all_frames, max_distance=30.0)
    assert before is not None
    assert after is not None

    before, after = _get_nearest_frames(5.0, all_frames, max_distance=5.0)
    assert before is None
    assert after is not None


def test_get_all_frames_for_doc_matches_hashed_doc_id(tmp_path: Path, monkeypatch):
    """Catalog lookup should resolve hashed doc_id used by chunker/retrieval."""
    frame_dir = tmp_path / ".converted" / "lecture_frames"
    frame_dir.mkdir(parents=True)

    frame_10 = frame_dir / "frame_00m10s.md"
    frame_10.write_text("# Visual Frame at 00:10\n\n## Description\n\nFrame at 10s.\n")

    frame_45 = frame_dir / "frame_00m45s.md"
    frame_45.write_text("# Visual Frame at 00:45\n\n## Description\n\nFrame at 45s.\n")

    entry = FileEntry(
        path="videos/lecture.mp4",
        name="lecture.mp4",
        extension=".mp4",
        file_type="video",
        category="mp4",
        size_bytes=100,
        created_at="2026-01-01T00:00:00+00:00",
        modified_at="2026-01-01T00:00:00+00:00",
        indexed_at="2026-01-01T00:00:00+00:00",
        checksum_sha256="sha256-video",
        frame_descriptions=[
            ".converted/lecture_frames/frame_00m10s.md",
            ".converted/lecture_frames/frame_00m45s.md",
        ],
    )

    class _CatalogStub:
        def __init__(self, e):
            self.files = {e.path: e}

    monkeypatch.setattr(
        "flavia.content.indexer.video_retrieval.ContentCatalog.load",
        lambda _: _CatalogStub(entry),
    )

    doc_id = hashlib.sha1(f"{tmp_path}:{entry.path}:{entry.checksum_sha256}".encode()).hexdigest()
    frames = _get_all_frames_for_doc(doc_id, tmp_path)

    assert [f[0] for f in frames] == [10, 45]
    assert frames[0][1] == frame_10
    assert frames[1][1] == frame_45


def test_expand_temporal_window_non_video_chunk():
    """Test that non-video chunks return None."""
    mock_chunk = {
        "modality": "text",
        "doc_id": "test_doc",
        "locator": {},
    }
    mock_base_dir = Path("/fake")
    mock_vs = Mock()
    mock_fts = Mock()

    result = expand_temporal_window(mock_chunk, mock_base_dir, mock_vs, mock_fts)
    assert result is None


def test_expand_temporal_window_missing_timecode():
    """Test that chunks without timecode return None."""
    mock_chunk = {
        "modality": "video_transcript",
        "doc_id": "test_doc",
        "locator": {},
    }
    mock_base_dir = Path("/fake")
    mock_vs = Mock()
    mock_fts = Mock()

    result = expand_temporal_window(mock_chunk, mock_base_dir, mock_vs, mock_fts)
    assert result is None


def test_expand_temporal_window_invalid_doc_id():
    """Test that chunks without doc_id return None."""
    mock_chunk = {
        "modality": "video_transcript",
        "doc_id": "",
        "locator": {"time_start": "00:00:30"},
        "time_start": "00:00:30",
    }
    mock_base_dir = Path("/fake")
    mock_vs = Mock()
    mock_fts = Mock()

    result = expand_temporal_window(mock_chunk, mock_base_dir, mock_vs, mock_fts)
    assert result is None


def test_expand_temporal_window_includes_overlapping_transcript(monkeypatch):
    """Transcript chunks overlapping the window should be included even if they start before it."""
    anchor_chunk = {
        "modality": "video_frame",
        "doc_id": "doc_1",
        "locator": {"time_start": "00:00:50"},
    }

    mock_vs = Mock()
    mock_vs.get_chunks_by_doc_id.return_value = [
        {
            "locator": {"time_start": "00:00:00", "time_end": "00:01:00"},
            "text": "Long transcript chunk crossing the anchor window.",
        }
    ]

    monkeypatch.setattr(
        "flavia.content.indexer.video_retrieval._get_all_frames_for_doc",
        lambda doc_id, base_dir: [],
    )

    bundle = expand_temporal_window(anchor_chunk, Path("/fake"), mock_vs, Mock())
    assert bundle is not None
    assert any(
        item["modality"] == "video_transcript"
        and "crossing the anchor window" in item["text"]
        for item in bundle
    )
