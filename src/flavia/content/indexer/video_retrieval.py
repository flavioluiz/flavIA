"""Video temporal expansion for retrieved chunks.

This module provides functionality to expand retrieved video chunks
(temporal) around an anchor timecode and return a chronological
evidence bundle with transcript and frame descriptions.
"""

import json
import re
from pathlib import Path
from typing import Any, Optional

from flavia.config import Settings

from ..catalog import ContentCatalog
from .fts import FTSIndex
from .vector_store import VectorStore


def _parse_timecode(tc: str) -> Optional[float]:
    """Parse 'HH:MM:SS' or 'MM:SS' or 'SS' to seconds. Returns None on failure."""
    try:
        parts = tc.strip().split(":")
        parts = [float(p) for p in parts]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        return parts[0]
    except (ValueError, IndexError):
        return None


def _seconds_to_timecode(seconds: float) -> str:
    """Convert seconds to HH:MM:SS string."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _read_frame_from_file(frame_path: Path) -> Optional[dict[str, Any]]:
    """Read a frame description file and extract key information.

    Args:
        frame_path: Path to the frame markdown file.

    Returns:
        Dict with time_start, time_end, and text, or None on error.
    """
    if not frame_path.exists():
        return None

    try:
        text = frame_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    pattern = re.compile(
        r"^#{1,2}\s+(?:Visual\s+)?Frame\s+at\s+(\d{1,2}:\d{2}(?::\d{2})?)\s*$",
        re.IGNORECASE,
    )
    time_str = None

    for line in text.splitlines():
        m = pattern.match(line.strip())
        if m:
            time_str = m.group(1)
            break

    if not time_str:
        time_str = "00:00:00"

    time = _parse_timecode(time_str)
    if time is None:
        time = 0.0

    desc_match = re.search(r"^##\s+Description\s*$", text, re.IGNORECASE | re.MULTILINE)
    if desc_match:
        description = text[desc_match.end() :].strip()
    else:
        if text.startswith("---"):
            end = text.find("\n---", 3)
            if end != -1:
                description = text[end + 4 :].strip()
            else:
                description = text.strip()
        else:
            description = text.strip()

    return {
        "time_start": time,
        "time_end": time,
        "text": description,
    }


def _safe_resolve(base_dir: Path, path_value: str | Path) -> Optional[Path]:
    """Resolve a path and ensure it stays inside base_dir."""
    candidate = path_value if isinstance(path_value, Path) else Path(path_value)
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    try:
        resolved = candidate.resolve()
        resolved.relative_to(base_dir.resolve())
    except (OSError, ValueError):
        return None
    return resolved


def _get_all_frames_for_doc(
    doc_id: str,
    base_dir: Path,
) -> list[tuple[float, Path]]:
    """Get all frame description files for a document, sorted by timecode.

    Args:
        doc_id: Document ID.
        base_dir: Vault base directory.

    Returns:
        List of tuples (time_seconds, frame_path) sorted by time.
    """
    catalog = ContentCatalog.load(base_dir / ".flavia")
    if catalog is None:
        return []

    entry = None
    for file_entry in catalog.files.values():
        current_doc_id = file_entry.path
        if current_doc_id == doc_id or file_entry.checksum_sha256 == doc_id:
            entry = file_entry
            break

    if entry is None or not hasattr(entry, "frame_descriptions") or not entry.frame_descriptions:
        return []

    frames = []
    for frame_path_str in entry.frame_descriptions:
        frame_path = _safe_resolve(base_dir, frame_path_str)
        if frame_path is None or not frame_path.exists():
            continue

        _, filename = frame_path.name.replace(".md", ""), frame_path
        pattern = re.match(r"frame_(\d{2})m(\d{2})s", frame_path.stem)
        if pattern:
            minutes = int(pattern.group(1))
            seconds = int(pattern.group(2))
            time_sec = minutes * 60 + seconds
            frames.append((time_sec, frame_path))

    frames.sort(key=lambda x: x[0])
    return frames


def _get_nearest_frames(
    center_time: float,
    all_frames: list[tuple[float, Path]],
    max_distance: float = 30.0,
) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    """Get the nearest frames before and after center_time.

    Args:
        center_time: Target time in seconds.
        all_frames: List of (time_seconds, frame_path) tuples sorted by time.
        max_distance: Maximum distance in seconds to search for nearest frames.

    Returns:
        Tuple of (nearest_before_frame, nearest_after_frame) as dicts,
        or (None, None) if not found within max_distance.
    """
    nearest_before = None
    nearest_after = None
    min_before_dist = max_distance
    min_after_dist = max_distance

    for time_sec, frame_path in all_frames:
        dist = time_sec - center_time

        if dist <= 0 and -dist <= min_before_dist:
            min_before_dist = -dist
            frame_data = _read_frame_from_file(frame_path)
            if frame_data:
                nearest_before = frame_data

        if dist > 0 and dist <= min_after_dist:
            min_after_dist = dist
            frame_data = _read_frame_from_file(frame_path)
            if frame_data:
                nearest_after = frame_data

    return nearest_before, nearest_after


def _get_frames_in_range(
    center_time: float,
    window_seconds: float,
    all_frames: list[tuple[float, Path]],
) -> list[dict[str, Any]]:
    """Get all frames within a time range.

    Args:
        center_time: Center time in seconds.
        window_seconds: Window size (half-width) in seconds.
        all_frames: List of (time_seconds, frame_path) tuples sorted by time.

    Returns:
        List of frame dicts sorted by time.
    """
    range_start = center_time - window_seconds
    range_end = center_time + window_seconds

    frames_in_range = []
    for time_sec, frame_path in all_frames:
        if range_start <= time_sec <= range_end:
            frame_data = _read_frame_from_file(frame_path)
            if frame_data:
                frames_in_range.append(frame_data)

    return frames_in_range


def _format_evidence_bundle(
    transcript_items: list[dict[str, Any]],
    frame_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Format evidence bundle with proper time display and modality labels.

    Args:
        transcript_items: List of transcript chunks with time_start, time_end, text.
        frame_items: List of frame chunks with time_start, time_end, text.

    Returns:
        List of formatted bundle items sorted by time (transcripts first, then frames).
    """
    formatted = []

    for item in transcript_items:
        time_start = item["time_start"]
        time_end = item["time_end"]

        if time_start == time_end:
            time_display = _seconds_to_timecode(time_start)
        else:
            time_display = f"{_seconds_to_timecode(time_start)}–{_seconds_to_timecode(time_end)}"

        formatted.append(
            {
                "time_display": time_display,
                "modality_label": "(Audio)",
                "text": item["text"],
                "modality": "video_transcript",
            }
        )

    for item in frame_items:
        time_start = item["time_start"]
        time_end = item["time_end"]

        if time_start == time_end:
            time_display = _seconds_to_timecode(time_start)
        else:
            time_display = f"{_seconds_to_timecode(time_start)}–{_seconds_to_timecode(time_end)}"

        formatted.append(
            {
                "time_display": time_display,
                "modality_label": "(Screen)",
                "text": item["text"],
                "modality": "video_frame",
            }
        )

    return formatted


def expand_temporal_window(
    anchor_chunk: dict[str, Any],
    base_dir: Path,
    vector_store: VectorStore,
    fts_index: FTSIndex,
) -> Optional[list[dict[str, Any]]]:
    """Expand a video chunk into a chronological evidence bundle.

    Args:
        anchor_chunk: The retrieved video chunk with locator containing timecode.
        base_dir: Vault base directory.
        vector_store: VectorStore instance for retrieving transcript chunks.
        fts_index: FTSIndex instance for retrieving text content.

    Returns:
        List of formatted bundle items (transcripts first, then frames),
        or None if expansion fails or chunk is not video temporal.
    """
    modality = anchor_chunk.get("modality", "")
    if modality not in ("video_transcript", "video_frame"):
        return None

    locator = anchor_chunk.get("locator", {})
    time_str = locator.get("time_start", "")
    anchor_time = _parse_timecode(time_str)

    if anchor_time is None:
        return None

    doc_id = anchor_chunk.get("doc_id")
    if not doc_id:
        return None

    window_size = 15.0 if modality == "video_transcript" else 10.0
    range_start = anchor_time - window_size
    range_end = anchor_time + window_size

    all_frames = _get_all_frames_for_doc(doc_id, base_dir)
    frames_in_range = _get_frames_in_range(anchor_time, window_size, all_frames)

    if not frames_in_range:
        nearest_before, nearest_after = _get_nearest_frames(
            anchor_time, all_frames, max_distance=30.0
        )
        if nearest_before:
            frames_in_range.append(nearest_before)
        if nearest_after:
            frames_in_range.append(nearest_after)
        frames_in_range.sort(key=lambda f: f["time_start"])

    transcript_chunks = vector_store.get_chunks_by_doc_id(doc_id, modalities=["video_transcript"])

    transcripts_in_range = []
    for chunk in transcript_chunks:
        chunk_locator = chunk.get("locator", {})
        chunk_time_str = chunk_locator.get("time_start", "")
        chunk_time = _parse_timecode(chunk_time_str)

        if chunk_time is not None and range_start <= chunk_time <= range_end:
            chunk_time_end_str = chunk_locator.get("time_end", chunk_time_str)
            chunk_time_end = _parse_timecode(chunk_time_end_str)
            if chunk_time_end is None:
                chunk_time_end = chunk_time

            transcripts_in_range.append(
                {
                    "time_start": chunk_time,
                    "time_end": chunk_time_end,
                    "text": chunk.get("text", ""),
                    "modality": "video_transcript",
                }
            )

    transcripts_in_range.sort(key=lambda t: t["time_start"])

    bundle_items = _format_evidence_bundle(transcripts_in_range, frames_in_range)

    return bundle_items


def expand_video_chunks(
    results: list[dict[str, Any]],
    base_dir: Path,
    vector_store: VectorStore,
    fts_index: FTSIndex,
) -> list[dict[str, Any]]:
    """Expand all video temporal chunks in results with evidence bundles.

    Args:
        results: List of retrieved chunks from hybrid retrieval.
        base_dir: Vault base directory.
        vector_store: VectorStore instance (must already be opened as context manager).
        fts_index: FTSIndex instance (must already be opened as context manager).

    Returns:
        Modified results with temporal_bundle field added to video chunks.
    """
    for result in results:
        modality = result.get("modality", "")
        if modality in ("video_transcript", "video_frame"):
            bundle = expand_temporal_window(result, base_dir, vector_store, fts_index)
            if bundle:
                result["temporal_bundle"] = bundle

    return results
