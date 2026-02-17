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
from typing import Optional


# Approximate token count: 1 token ≈ 4 characters
_CHARS_PER_TOKEN = 4
_CHUNK_MIN_CHARS = 300 * _CHARS_PER_TOKEN  # ~300 tokens
_CHUNK_MAX_CHARS = 800 * _CHARS_PER_TOKEN  # ~800 tokens


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


def _path_for_output(base_dir: Path, path: Path) -> str:
    """Return a path string for serialized chunk source metadata."""
    try:
        return str(path.resolve().relative_to(base_dir.resolve()))
    except ValueError:
        return str(path)


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


def _split_into_paragraphs(text: str) -> list[tuple[int, int, str]]:
    """Split text on blank lines, preserving non-empty paragraphs and line spans."""
    paragraphs: list[tuple[int, int, str]] = []
    current: list[str] = []
    para_start_line: Optional[int] = None
    lines = text.splitlines()

    for line_no, line in enumerate(lines, start=1):
        if line.strip() == "":
            if current and para_start_line is not None:
                paragraphs.append((para_start_line, line_no - 1, "\n".join(current)))
                current = []
                para_start_line = None
        else:
            if para_start_line is None:
                para_start_line = line_no
            current.append(line)

    if current and para_start_line is not None:
        paragraphs.append((para_start_line, len(lines), "\n".join(current)))

    return paragraphs


def _merge_paragraphs(
    paragraphs: list[tuple[int, int, str]],
    min_chars: int,
    max_chars: int,
) -> list[tuple[str, int, int]]:
    """Merge short paragraphs and split oversized ones into chunks with line spans."""
    chunks: list[tuple[str, int, int]] = []
    buffer = ""
    buffer_start: Optional[int] = None
    buffer_end: Optional[int] = None

    def flush() -> None:
        nonlocal buffer, buffer_start, buffer_end
        if buffer.strip() and buffer_start is not None and buffer_end is not None:
            chunks.append((buffer.strip(), buffer_start, buffer_end))
        buffer = ""
        buffer_start = None
        buffer_end = None

    for para_start, para_end, para in paragraphs:
        # If para alone exceeds max, split by sentences
        if len(para) > max_chars:
            flush()
            # Split oversized paragraph by sentence boundaries
            sentences = re.split(r"(?<=[.!?])\s+", para)
            sentence_buffer = ""
            for sent in sentences:
                if len(sentence_buffer) + len(sent) + 1 > max_chars and sentence_buffer:
                    chunks.append((sentence_buffer.strip(), para_start, para_end))
                    sentence_buffer = ""
                sentence_buffer += (" " if sentence_buffer else "") + sent
                if len(sentence_buffer) >= min_chars:
                    chunks.append((sentence_buffer.strip(), para_start, para_end))
                    sentence_buffer = ""
            if sentence_buffer.strip():
                chunks.append((sentence_buffer.strip(), para_start, para_end))
        else:
            if len(buffer) + len(para) + 2 > max_chars and buffer:
                flush()
            if buffer_start is None:
                buffer_start = para_start
            buffer += ("\n\n" if buffer else "") + para
            buffer_end = para_end
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


def _extract_transcription_body(text: str) -> str:
    """Return content after '## Transcription' heading when present."""
    match = re.search(r"^##\s+Transcription\s*$", text, re.IGNORECASE | re.MULTILINE)
    if not match:
        return text
    return text[match.end() :]


def _extract_frame_description(lines: list[str]) -> str:
    """Extract the human description text from frame markdown body lines."""
    text = "\n".join(lines).strip()
    if not text:
        return ""

    desc_match = re.search(r"^##\s+Description\s*$", text, re.IGNORECASE | re.MULTILINE)
    if desc_match:
        return text[desc_match.end() :].strip()

    # Handle front-matter style metadata if the description lacks an explicit section heading.
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4 :].strip()

    return text


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
    safe_converted_path = _safe_resolve(base_dir, converted_path)
    if safe_converted_path is None:
        return []
    converted_path = safe_converted_path

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
    para_with_context: list[tuple[list[str], int, int, str]] = []
    for para_start, para_end, para in paragraphs:
        # Update heading path based on first line of paragraph
        first_line = para.splitlines()[0] if para else ""
        updated = _heading_path_from_text(first_line, current_headings)
        if updated != current_headings:
            current_headings = updated
            # Don't include the heading line itself as a content paragraph
            rest_lines = para.splitlines()[1:]
            rest = "\n".join(rest_lines).strip()
            if rest:
                para_with_context.append((list(current_headings), para_start + 1, para_end, rest))
        else:
            para_with_context.append((list(current_headings), para_start, para_end, para))

    # Merge paragraphs per contiguous heading section to preserve order.
    section_runs: list[tuple[list[str], list[tuple[int, int, str]]]] = []
    current_key: Optional[str] = None
    current_headings_run: list[str] = []
    current_run: list[tuple[int, int, str]] = []

    for headings, para_start, para_end, para_text in para_with_context:
        key = json.dumps(headings)
        if key != current_key:
            if current_key is not None and current_run:
                section_runs.append((current_headings_run, current_run))
            current_key = key
            current_headings_run = headings
            current_run = []
        current_run.append((para_start, para_end, para_text))

    if current_key is not None and current_run:
        section_runs.append((current_headings_run, current_run))

    chunks = []
    offset = 0
    for headings, paras in section_runs:
        merged = _merge_paragraphs(paras, _CHUNK_MIN_CHARS, _CHUNK_MAX_CHARS)
        for chunk_text, line_start, line_end in merged:
            if not chunk_text.strip():
                continue
            cid = _chunk_id(doc, modality, offset)
            chunks.append(
                {
                    "chunk_id": cid,
                    "doc_id": doc,
                    "modality": modality,
                    "source": {
                        "converted_path": _path_for_output(base_dir, converted_path),
                        "name": source_name,
                        "file_type": file_type,
                        "locator": {
                            "line_start": line_start,
                            "line_end": line_end,
                        },
                    },
                    "heading_path": headings,
                    "text": chunk_text,
                }
            )
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
    safe_converted_path = _safe_resolve(base_dir, converted_path)
    if safe_converted_path is None:
        return []
    converted_path = safe_converted_path

    chunks = []

    checksum = _file_checksum(converted_path)
    doc = _doc_id(base_dir, original_path, checksum)

    # --- Transcript stream ---
    try:
        transcript_text = converted_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        transcript_text = ""

    if transcript_text.strip():
        chunks.extend(
            _chunk_video_transcript(
                transcript_text,
                doc,
                source_name,
                base_dir,
                converted_path,
                original_path,
            )
        )

    # --- Frame description stream ---
    if frame_desc_paths:
        for frame_path_str in frame_desc_paths:
            frame_path = _safe_resolve(base_dir, frame_path_str)
            if frame_path is None:
                continue
            try:
                frame_text = frame_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            chunks.extend(
                _chunk_frame_descriptions(frame_text, doc, source_name, base_dir, frame_path)
            )

    return chunks


def _chunk_video_transcript(
    text: str,
    doc_id: str,
    source_name: str,
    base_dir: Path,
    converted_path: Path,
    original_path: str,
) -> list[dict]:
    """Produce video_transcript chunks grouped into ~60-second windows."""
    body = _extract_transcription_body(text)

    # Parse lines looking for timecode patterns like:
    # [00:01:05] text
    # [00:01:05 - 00:01:18] text
    # 00:01:05 text
    segments: list[tuple[float, float, str]] = []  # (time_start_sec, time_end_sec, text)

    tc_pattern = re.compile(
        r"^\[?\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*(?:-\s*(\d{1,2}:\d{2}(?::\d{2})?))?\s*\]?\s*(.*)$"
    )

    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        m = tc_pattern.match(line)
        if m:
            start_tc = m.group(1)
            end_tc = m.group(2)
            content = m.group(3).strip()
            start = _parse_timecode(start_tc)
            end = _parse_timecode(end_tc) if end_tc else start
            if start is not None and end is not None and content:
                segments.append((start, end, content))
        else:
            # No timecode: append to the previous segment (if any).
            if segments:
                prev_start, prev_end, prev_text = segments[-1]
                segments[-1] = (prev_start, prev_end, f"{prev_text} {line}")

    if not segments:
        # Fall back to plain text chunking
        return chunk_text_document(converted_path, source_name, "video", base_dir, original_path)

    # Group into ~60-second windows
    window_secs = 60.0
    chunks = []
    window_start = segments[0][0]
    window_parts: list[tuple[float, float, str]] = []

    def flush_window():
        nonlocal window_start, window_parts
        if not window_parts:
            return
        t_start = window_parts[0][0]
        t_end = window_parts[-1][1]
        combined = " ".join(p for _, _, p in window_parts)
        cid = _chunk_id(doc_id, "video_transcript", int(t_start))
        chunks.append(
            {
                "chunk_id": cid,
                "doc_id": doc_id,
                "modality": "video_transcript",
                "source": {
                    "converted_path": _path_for_output(base_dir, converted_path),
                    "name": source_name,
                    "file_type": "video",
                    "locator": {
                        "time_start": _seconds_to_timecode(t_start),
                        "time_end": _seconds_to_timecode(t_end),
                    },
                },
                "heading_path": [],
                "text": combined,
            }
        )
        window_parts = []
        window_start = t_end

    for t_start, t_end, content in segments:
        if window_parts and (t_start - window_start) >= window_secs:
            flush_window()
            window_start = t_start
        window_parts.append((t_start, t_end, content))

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
    chunks = []
    frame_pattern = re.compile(
        r"^#{1,2}\s+(?:Visual\s+)?Frame\s+at\s+(\d{1,2}:\d{2}(?::\d{2})?)\s*$",
        re.IGNORECASE,
    )

    current_tc: Optional[str] = None
    current_lines: list[str] = []

    def flush_frame():
        nonlocal current_tc, current_lines
        if current_tc is None or not current_lines:
            return
        description = _extract_frame_description(current_lines)
        if not description:
            return
        t = _parse_timecode(current_tc)
        if t is None:
            t = 0.0
        cid = _chunk_id(doc_id, "video_frame", int(t))
        chunks.append(
            {
                "chunk_id": cid,
                "doc_id": doc_id,
                "modality": "video_frame",
                "source": {
                    "converted_path": _path_for_output(base_dir, frame_path),
                    "name": source_name,
                    "file_type": "video",
                    "locator": {
                        "time_start": _seconds_to_timecode(t),
                        "time_end": _seconds_to_timecode(t),
                    },
                },
                "heading_path": [f"Frame at {current_tc}"],
                "text": description,
            }
        )
        current_lines = []
        current_tc = None

    for line in text.splitlines():
        stripped = line.strip()
        m = frame_pattern.match(stripped)
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

    converted_path = _safe_resolve(base_dir, converted_to)
    if converted_path is None:
        return []
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
