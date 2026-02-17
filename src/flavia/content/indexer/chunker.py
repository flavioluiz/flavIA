"""Chunk converted markdown documents into retrievable fragments.

Produces a stream of chunk dicts compatible with the JSONL schema.
Two special streams exist for video documents:
- video_transcript: timed transcript segments
- video_frame: frame description blocks with timecodes
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Iterator, Optional


# Approximate token count: 1 token ≈ 4 characters
_CHARS_PER_TOKEN = 4
_CHUNK_MIN_CHARS = 300 * _CHARS_PER_TOKEN   # ~300 tokens
_CHUNK_MAX_CHARS = 800 * _CHARS_PER_TOKEN   # ~800 tokens


def _chunk_id(doc_id: str, modality: str, offset: int) -> str:
    """Generate a stable chunk ID from doc_id, modality, and offset."""
    raw = f"{doc_id}:{modality}:{offset}"
    return hashlib.sha1(raw.encode()).hexdigest()


def _doc_id(base_dir: Path, path: str, checksum: str) -> str:
    """Generate a stable doc ID from base_dir, path, and checksum."""
    raw = f"{base_dir}:{path}:{checksum}"
    return hashlib.sha1(raw.encode()).hexdigest()


def _file_checksum(file_path: Path) -> str:
    """SHA-256 checksum of a file."""
    h = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for block in iter(lambda: f.read(65536), b""):
                h.update(block)
    except OSError:
        return ""
    return h.hexdigest()


def _heading_path_from_text(text: str, current_headings: list[str]) -> list[str]:
    """Extract heading path from a markdown line if it is a heading."""
    m = re.match(r"^(#{1,6})\s+(.+)", text.strip())
    if m:
        level = len(m.group(1))
        title = m.group(2).strip()
        # Keep headings up to this level, then add the new one
        new_path = current_headings[: level - 1] + [title]
        return new_path
    return current_headings


def _split_into_paragraphs(text: str) -> list[str]:
    """Split text on blank lines, preserving non-empty paragraphs."""
    paragraphs = []
    current: list[str] = []
    for line in text.splitlines():
        if line.strip() == "":
            if current:
                paragraphs.append("\n".join(current))
                current = []
        else:
            current.append(line)
    if current:
        paragraphs.append("\n".join(current))
    return paragraphs


def _merge_paragraphs(paragraphs: list[str], min_chars: int, max_chars: int) -> list[str]:
    """Merge short paragraphs and split oversized ones into chunks."""
    chunks: list[str] = []
    buffer = ""

    def flush():
        nonlocal buffer
        if buffer.strip():
            chunks.append(buffer.strip())
        buffer = ""

    for para in paragraphs:
        # If para alone exceeds max, split by sentences
        if len(para) > max_chars:
            # Split oversized paragraph by sentence boundaries
            sentences = re.split(r"(?<=[.!?])\s+", para)
            for sent in sentences:
                if len(buffer) + len(sent) + 1 > max_chars and buffer:
                    flush()
                buffer += (" " if buffer else "") + sent
                if len(buffer) >= min_chars:
                    flush()
            if buffer:
                flush()
        else:
            if len(buffer) + len(para) + 2 > max_chars and buffer:
                flush()
            buffer += ("\n\n" if buffer else "") + para
            if len(buffer) >= min_chars:
                flush()

    flush()
    return chunks


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


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def chunk_text_document(
    converted_path: Path,
    source_name: str,
    file_type: str,
    base_dir: Path,
    original_path: str,
) -> list[dict]:
    """Chunk a plain text/markdown converted document.

    Args:
        converted_path: Path to the .md/.txt converted file.
        source_name: Human-readable document name.
        file_type: Original file type (pdf, image, audio, ...).
        base_dir: Vault base directory (for doc_id generation).
        original_path: Relative path of original file.

    Returns:
        List of chunk dicts (JSONL-compatible).
    """
    try:
        text = converted_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    checksum = _file_checksum(converted_path)
    doc = _doc_id(base_dir, original_path, checksum)

    # Detect modality from file_type
    modality_map = {
        "audio": "audio_transcript",
        "video": "video_transcript",
        "image": "image_caption",
    }
    modality = modality_map.get(file_type, "text")

    current_headings: list[str] = []
    paragraphs = _split_into_paragraphs(text)

    # Track heading context alongside each paragraph
    para_with_context: list[tuple[list[str], str]] = []
    for para in paragraphs:
        # Update heading path based on first line of paragraph
        first_line = para.splitlines()[0] if para else ""
        updated = _heading_path_from_text(first_line, current_headings)
        if updated != current_headings:
            current_headings = updated
            # Don't include the heading line itself as a content paragraph
            rest = "\n".join(para.splitlines()[1:]).strip()
            if rest:
                para_with_context.append((list(current_headings), rest))
        else:
            para_with_context.append((list(current_headings), para))

    # Now merge paragraphs within same heading section
    section_groups: dict[str, list[str]] = {}
    section_order: list[str] = []
    heading_map: dict[str, list[str]] = {}

    for headings, para in para_with_context:
        key = json.dumps(headings)
        if key not in section_groups:
            section_groups[key] = []
            section_order.append(key)
            heading_map[key] = headings
        section_groups[key].append(para)

    chunks = []
    offset = 0
    for key in section_order:
        headings = heading_map[key]
        paras = section_groups[key]
        merged = _merge_paragraphs(paras, _CHUNK_MIN_CHARS, _CHUNK_MAX_CHARS)
        for chunk_text in merged:
            if not chunk_text.strip():
                continue
            cid = _chunk_id(doc, modality, offset)
            chunks.append({
                "chunk_id": cid,
                "doc_id": doc,
                "modality": modality,
                "source": {
                    "converted_path": str(converted_path.relative_to(base_dir)),
                    "name": source_name,
                    "file_type": file_type,
                    "locator": {
                        "line_start": offset,
                        "line_end": offset + len(chunk_text.splitlines()),
                    },
                },
                "heading_path": headings,
                "text": chunk_text,
            })
            offset += len(chunk_text.splitlines()) + 1

    return chunks


def chunk_video_document(
    converted_path: Path,
    source_name: str,
    base_dir: Path,
    original_path: str,
    frame_desc_paths: Optional[list[str]] = None,
) -> list[dict]:
    """Chunk a video document: transcript stream + frame description stream.

    Args:
        converted_path: Path to the audio transcript .md file.
        source_name: Human-readable video name.
        base_dir: Vault base directory.
        original_path: Relative path of original video file.
        frame_desc_paths: List of frame description .md file paths.

    Returns:
        List of chunk dicts with modality video_transcript or video_frame.
    """
    chunks = []

    checksum = _file_checksum(converted_path)
    doc = _doc_id(base_dir, original_path, checksum)

    # --- Transcript stream ---
    try:
        transcript_text = converted_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        transcript_text = ""

    if transcript_text.strip():
        chunks.extend(_chunk_video_transcript(transcript_text, doc, source_name, base_dir, converted_path))

    # --- Frame description stream ---
    if frame_desc_paths:
        for frame_path_str in frame_desc_paths:
            frame_path = base_dir / frame_path_str if not Path(frame_path_str).is_absolute() else Path(frame_path_str)
            try:
                frame_text = frame_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            chunks.extend(_chunk_frame_descriptions(frame_text, doc, source_name, base_dir, frame_path))

    return chunks


def _chunk_video_transcript(
    text: str,
    doc_id: str,
    source_name: str,
    base_dir: Path,
    converted_path: Path,
) -> list[dict]:
    """Produce video_transcript chunks grouped into ~60-second windows."""
    # Parse lines looking for timecode patterns like [00:01:05] or 00:01:05 ...
    # Group segments into ~60s windows
    segments: list[tuple[float, str]] = []  # (time_start_sec, text)

    tc_pattern = re.compile(r"\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s*(.*)")

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = tc_pattern.match(line)
        if m:
            tc = m.group(1)
            content = m.group(2).strip()
            t = _parse_timecode(tc)
            if t is not None and content:
                segments.append((t, content))
        else:
            # No timecode — append to last segment or start a new one
            if segments:
                segments[-1] = (segments[-1][0], segments[-1][1] + " " + line)
            else:
                segments.append((0.0, line))

    if not segments:
        # Fall back to plain text chunking
        return chunk_text_document(
            converted_path, source_name, "video", base_dir, str(converted_path.relative_to(base_dir))
        )

    # Group into ~60-second windows
    window_secs = 60.0
    chunks = []
    window_start = segments[0][0]
    window_parts: list[tuple[float, str]] = []

    def flush_window():
        nonlocal window_start, window_parts
        if not window_parts:
            return
        t_start = window_parts[0][0]
        t_end = window_parts[-1][0]
        combined = " ".join(p for _, p in window_parts)
        cid = _chunk_id(doc_id, "video_transcript", int(t_start))
        chunks.append({
            "chunk_id": cid,
            "doc_id": doc_id,
            "modality": "video_transcript",
            "source": {
                "converted_path": str(converted_path.relative_to(base_dir)),
                "name": source_name,
                "file_type": "video",
                "locator": {
                    "time_start": _seconds_to_timecode(t_start),
                    "time_end": _seconds_to_timecode(t_end),
                },
            },
            "heading_path": [],
            "text": combined,
        })
        window_parts = []
        window_start = t_end

    for t, content in segments:
        if window_parts and (t - window_start) >= window_secs:
            flush_window()
            window_start = t
        window_parts.append((t, content))

    flush_window()
    return chunks


def _chunk_frame_descriptions(
    text: str,
    doc_id: str,
    source_name: str,
    base_dir: Path,
    frame_path: Path,
) -> list[dict]:
    """Produce video_frame chunks from a frame description markdown file."""
    # Frame descriptions are typically structured as:
    # ## Frame at HH:MM:SS
    # <description>
    chunks = []
    frame_pattern = re.compile(r"^##\s+Frame\s+at\s+(\d{1,2}:\d{2}(?::\d{2})?)", re.IGNORECASE)

    current_tc: Optional[str] = None
    current_lines: list[str] = []

    def flush_frame():
        nonlocal current_tc, current_lines
        if current_tc is None or not current_lines:
            return
        description = "\n".join(current_lines).strip()
        if not description:
            return
        t = _parse_timecode(current_tc)
        if t is None:
            t = 0.0
        cid = _chunk_id(doc_id, "video_frame", int(t))
        chunks.append({
            "chunk_id": cid,
            "doc_id": doc_id,
            "modality": "video_frame",
            "source": {
                "converted_path": str(frame_path.relative_to(base_dir)),
                "name": source_name,
                "file_type": "video",
                "locator": {
                    "time_start": _seconds_to_timecode(t),
                    "time_end": _seconds_to_timecode(t),
                },
            },
            "heading_path": [f"Frame at {current_tc}"],
            "text": description,
        })
        current_lines = []
        current_tc = None

    for line in text.splitlines():
        m = frame_pattern.match(line.strip())
        if m:
            flush_frame()
            current_tc = m.group(1)
        elif current_tc is not None:
            current_lines.append(line)

    flush_frame()
    return chunks


def chunk_document(
    entry,
    base_dir: Path,
) -> list[dict]:
    """Dispatch to the right chunker based on a catalog FileEntry.

    Args:
        entry: A FileEntry (or compatible dict) from the content catalog.
        base_dir: Vault base directory.

    Returns:
        List of chunk dicts.
    """
    # Normalise to attribute access
    if isinstance(entry, dict):
        path = entry.get("path", "")
        name = entry.get("name", path)
        file_type = entry.get("file_type", "text")
        converted_to = entry.get("converted_to", "")
        frame_descriptions = entry.get("frame_descriptions", [])
    else:
        path = getattr(entry, "path", "")
        name = getattr(entry, "name", path)
        file_type = getattr(entry, "file_type", "text")
        converted_to = getattr(entry, "converted_to", "") or ""
        frame_descriptions = getattr(entry, "frame_descriptions", []) or []

    if not converted_to:
        return []

    converted_path = base_dir / converted_to if not Path(converted_to).is_absolute() else Path(converted_to)
    if not converted_path.exists():
        return []

    if file_type == "video":
        return chunk_video_document(
            converted_path=converted_path,
            source_name=name,
            base_dir=base_dir,
            original_path=path,
            frame_desc_paths=frame_descriptions if frame_descriptions else None,
        )

    return chunk_text_document(
        converted_path=converted_path,
        source_name=name,
        file_type=file_type,
        base_dir=base_dir,
        original_path=path,
    )
