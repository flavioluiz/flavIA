"""Video frame extraction and description using vision LLM.

Extracts frames from video files at specific timestamps and generates
text descriptions using vision-capable models.
"""

import logging
import re
import shutil
import subprocess
from hashlib import sha256
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


DEFAULT_FRAME_SAMPLE_INTERVAL = 10
DEFAULT_MAX_FRAMES = 10
DEFAULT_FRAME_MAX_WIDTH = 768
_DEFAULT_FRAME_QUALITY = 12
_DEFAULT_VISUAL_SIMILARITY_THRESHOLD = 0.97
_VISUAL_SIGNATURE_SIZE = 16


def _timestamp_to_seconds(timestamp: str) -> Optional[float]:
    """Convert HH:MM:SS or MM:SS timestamp string to seconds.

    Args:
        timestamp: Timestamp string like "01:30:45" or "05:23"

    Returns:
        Seconds as float, or None if parsing fails
    """
    parts = timestamp.strip().split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        try:
            m = int(minutes)
            s = int(seconds)
            return float(m * 60 + s)
        except ValueError:
            return None
    elif len(parts) == 3:
        hours, minutes, seconds = parts
        try:
            h = int(hours)
            m = int(minutes)
            s = int(seconds)
            return float(h * 3600 + m * 60 + s)
        except ValueError:
            return None
    return None


def _seconds_to_timestamp(seconds: float) -> str:
    """Convert seconds to MM:SS timestamp string.

    Args:
        seconds: Seconds as float

    Returns:
        Timestamp string like "05:23"
    """
    total = int(seconds)
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _format_frame_filename(seconds: float) -> str:
    """Format frame filename using timestamp.

    Args:
        seconds: Seconds as float

    Returns:
        Filename like "frame_05m23s.jpg"
    """
    total = int(seconds)
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"frame_{h:02d}h{m:02d}m{s:02d}s.jpg"
    return f"frame_{m:02d}m{s:02d}s.jpg"


def parse_transcript_timestamps(transcript: str) -> List[Tuple[float, float]]:
    """Extract timestamp ranges from transcription text.

    Looks for patterns like "[05:23 - 07:45]" in the transcript.

    Args:
        transcript: Transcript text with timestamp markers

    Returns:
        List of (start_seconds, end_seconds) tuples
    """
    pattern = r"\[\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*-\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*\]"
    matches = re.findall(pattern, transcript)

    timestamps = []
    for start_str, end_str in matches:
        start = _timestamp_to_seconds(start_str)
        end = _timestamp_to_seconds(end_str)
        if start is not None and end is not None:
            timestamps.append((start, end))

    return timestamps


def select_timestamps(
    timestamps: List[Tuple[float, float]],
    interval: int = DEFAULT_FRAME_SAMPLE_INTERVAL,
    max_frames: int = DEFAULT_MAX_FRAMES,
) -> List[float]:
    """Select timestamps for frame extraction.

    Selects 1 timestamp every 'interval' segment, up to 'max_frames' total.

    Args:
        timestamps: List of (start, end) timestamp tuples
        interval: Select 1 frame every N segments
        max_frames: Maximum number of frames to extract

    Returns:
        List of selected start timestamps (in seconds)
    """
    if not timestamps:
        return []
    if max_frames <= 0:
        return []

    safe_interval = max(1, interval)
    selectable_count = (len(timestamps) + safe_interval - 1) // safe_interval
    if selectable_count >= max_frames:
        return _select_uniform_segment_starts(timestamps, max_frames)

    selected = []
    for i, (start, _) in enumerate(timestamps):
        if i % safe_interval == 0 and len(selected) < max_frames:
            selected.append(start)

    return selected


def _select_uniform_segment_starts(
    timestamps: List[Tuple[float, float]],
    count: int,
) -> List[float]:
    """Select segment starts uniformly across the transcript timeline."""
    if not timestamps or count <= 0:
        return []
    if count == 1:
        return [timestamps[0][0]]

    max_index = len(timestamps) - 1
    raw_indices = [round(i * max_index / (count - 1)) for i in range(count)]

    # Guard against rounding collisions for small lists by keeping order and
    # filling with remaining indices.
    unique_indices: List[int] = []
    seen = set()
    for idx in raw_indices:
        if idx not in seen:
            unique_indices.append(idx)
            seen.add(idx)
    if len(unique_indices) < count:
        for idx in range(len(timestamps)):
            if idx in seen:
                continue
            unique_indices.append(idx)
            seen.add(idx)
            if len(unique_indices) == count:
                break

    unique_indices.sort()
    return [timestamps[idx][0] for idx in unique_indices[:count]]


def extract_frames_at_timestamps(
    video_path: Path,
    timestamps: List[float],
    output_dir: Path,
    quality: int = _DEFAULT_FRAME_QUALITY,
    max_width: int = DEFAULT_FRAME_MAX_WIDTH,
) -> List[Tuple[Path, float]]:
    """Extract frames from video at specific timestamps using ffmpeg.

    Args:
        video_path: Path to the video file
        timestamps: List of timestamps (in seconds) to extract
        output_dir: Directory to save extracted frames
        quality: JPEG quality (1-31, lower=better)
        max_width: Maximum frame width in pixels (maintains aspect ratio)

    Returns:
        List of tuples (frame_path, timestamp) for successfully extracted frames

    Raises:
        RuntimeError: If ffmpeg is not available
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required for frame extraction")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    extracted_files: List[Tuple[Path, float]] = []
    jpeg_quality = max(1, min(31, int(quality)))
    max_width_px = max(128, int(max_width))

    for timestamp in timestamps:
        filename = _format_frame_filename(timestamp)
        output_path = output_dir / filename

        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-ss",
                    str(timestamp),
                    "-i",
                    str(video_path),
                    "-vframes",
                    "1",
                    "-vf",
                    f"scale=w={max_width_px}:h=-2:force_original_aspect_ratio=decrease",
                    "-q:v",
                    str(jpeg_quality),
                    "-map_metadata",
                    "-1",
                    "-y",
                    str(output_path),
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.returncode != 0:
                logger.warning(
                    f"Failed to extract frame at {timestamp:.2f}s: {result.stderr[:200]}"
                )
                continue

            if output_path.exists() and output_path.stat().st_size > 0:
                extracted_files.append((output_path, timestamp))
                logger.debug(f"Extracted frame: {output_path}")

        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout extracting frame at {timestamp:.2f}s")
        except OSError as e:
            logger.warning(f"Error extracting frame at {timestamp:.2f}s: {e}")

    return extracted_files


def _deduplicate_frame_items(
    frame_items: List[Tuple[Path, float]],
) -> List[Tuple[Path, float]]:
    """Remove duplicate/similar adjacent frames, preserving the latest frame."""
    unique_items: List[Tuple[Path, float]] = []
    unique_hashes: List[str] = []
    unique_signatures: List[Optional[bytes]] = []

    for frame_path, timestamp in frame_items:
        try:
            file_hash = sha256(frame_path.read_bytes()).hexdigest()
        except OSError as e:
            logger.warning(f"Failed to hash frame {frame_path}: {e}")
            continue

        signature = _compute_visual_signature(frame_path)

        should_replace_last = False
        if unique_items:
            last_hash = unique_hashes[-1]
            last_signature = unique_signatures[-1]
            is_exact_duplicate = file_hash == last_hash
            is_visually_similar = (
                signature is not None
                and last_signature is not None
                and _visual_similarity(signature, last_signature)
                >= _DEFAULT_VISUAL_SIMILARITY_THRESHOLD
            )
            should_replace_last = is_exact_duplicate or is_visually_similar

        if should_replace_last:
            previous_path = unique_items[-1][0]
            if previous_path != frame_path:
                try:
                    previous_path.unlink(missing_ok=True)
                except OSError:
                    pass
            unique_items[-1] = (frame_path, timestamp)
            unique_hashes[-1] = file_hash
            unique_signatures[-1] = signature
            logger.debug(f"Skipping similar frame, keeping latest: {frame_path.name}")
            continue

        unique_items.append((frame_path, timestamp))
        unique_hashes.append(file_hash)
        unique_signatures.append(signature)

    return unique_items


def _compute_visual_signature(frame_path: Path) -> Optional[bytes]:
    """Compute a compact grayscale signature for visual similarity checks."""
    if not shutil.which("ffmpeg"):
        return None

    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                "-i",
                str(frame_path),
                "-vf",
                f"scale={_VISUAL_SIGNATURE_SIZE}:{_VISUAL_SIGNATURE_SIZE},format=gray",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "gray",
                "-vframes",
                "1",
                "-",
            ],
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if result.returncode != 0:
        return None

    expected_size = _VISUAL_SIGNATURE_SIZE * _VISUAL_SIGNATURE_SIZE
    if len(result.stdout) != expected_size:
        return None

    return result.stdout


def _visual_similarity(signature_a: bytes, signature_b: bytes) -> float:
    """Return normalized similarity [0.0, 1.0] between grayscale signatures."""
    if len(signature_a) != len(signature_b) or not signature_a:
        return 0.0

    total_diff = 0
    for a, b in zip(signature_a, signature_b):
        total_diff += abs(a - b)

    max_diff = len(signature_a) * 255
    return 1.0 - (total_diff / max_diff)


def format_frame_description_markdown(
    frame_path: Path,
    video_path: Path,
    timestamp: float,
    description: str,
    vision_model: str,
) -> str:
    """Format frame description as markdown with metadata.

    Args:
        frame_path: Path to the frame image file
        video_path: Path to the original video file
        timestamp: Timestamp in seconds
        description: Frame description text
        vision_model: Model used for vision analysis

    Returns:
        Markdown-formatted content
    """
    timestamp_str = _seconds_to_timestamp(timestamp)

    lines = []
    lines.append(f"# Visual Frame at {timestamp_str}")
    lines.append("")
    lines.append("---")
    lines.append(f"video_source: `{video_path.name}`")
    lines.append(f"frame_file: `{frame_path.name}`")
    lines.append(f"timestamp: {timestamp_str}")
    lines.append(f"vision_model: {vision_model}")
    lines.append("---")
    lines.append("")
    lines.append("## Description")
    lines.append("")
    lines.append(description)
    lines.append("")

    return "\n".join(lines)


def describe_frames(
    frame_items: List[Tuple[Path, float]],
    output_dir: Path,
    video_path: Path,
    image_converter,
) -> List[Tuple[Path, float]]:
    """Generate descriptions for extracted video frames.

    Args:
        frame_items: List of tuples (frame image path, timestamp)
        output_dir: Directory to save description markdown files
        video_path: Path to the original video file
        image_converter: ImageConverter instance for vision analysis

    Returns:
        List of tuples (description markdown path, timestamp)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    description_files: List[Tuple[Path, float]] = []

    for frame_path, timestamp in frame_items:
        stem = frame_path.stem
        output_path = output_dir / f"{stem}.md"

        try:
            description = image_converter.extract_text(frame_path)
            if not description or not description.strip():
                logger.warning(f"No description generated for {frame_path.name}")
                continue

            vision_model = getattr(
                image_converter.settings,
                "image_vision_model",
                "unknown",
            )

            formatted_md = format_frame_description_markdown(
                frame_path=frame_path,
                video_path=video_path,
                timestamp=timestamp,
                description=description,
                vision_model=vision_model,
            )

            output_path.write_text(formatted_md, encoding="utf-8")
            description_files.append((output_path, timestamp))
            logger.debug(f"Generated description: {output_path}")

        except Exception as e:
            logger.warning(f"Failed to describe frame {frame_path.name}: {e}")

    return description_files


def extract_and_describe_video_frames(
    video_path: Path,
    transcript: str,
    base_output_dir: Path,
    image_converter,
    interval: int = DEFAULT_FRAME_SAMPLE_INTERVAL,
    max_frames: int = DEFAULT_MAX_FRAMES,
) -> Tuple[List[Path], List[float]]:
    """Extract frames and generate descriptions for a video.

    Args:
        video_path: Path to the video file
        transcript: Transcript text with timestamp markers
        base_output_dir: Base output directory (.converted/)
        image_converter: ImageConverter instance for vision analysis
        interval: Select 1 frame every N transcript segments
        max_frames: Maximum number of frames to extract

    Returns:
        Tuple of (description_file_paths, selected_timestamps)
    """
    timestamps = parse_transcript_timestamps(transcript)
    selected_timestamps = select_timestamps(timestamps, interval=interval, max_frames=max_frames)

    if not selected_timestamps:
        logger.info(f"No frames selected for {video_path.name}")
        return [], []

    frames_dir = base_output_dir / f"{video_path.stem}_frames"
    extracted_frames = extract_frames_at_timestamps(video_path, selected_timestamps, frames_dir)

    if not extracted_frames:
        logger.warning(f"No frames extracted from {video_path.name}")
        return [], []

    deduplicated_frames = _deduplicate_frame_items(extracted_frames)
    if not deduplicated_frames:
        logger.warning(f"All extracted frames were duplicates for {video_path.name}")
        return [], []

    descriptions = describe_frames(deduplicated_frames, frames_dir, video_path, image_converter)

    logger.info(
        f"Extracted {len(extracted_frames)} frames "
        f"({len(deduplicated_frames)} unique) and generated "
        f"{len(descriptions)} descriptions for {video_path.name}"
    )

    description_paths = [desc_path for desc_path, _ in descriptions]
    description_timestamps = [timestamp for _, timestamp in descriptions]
    return description_paths, description_timestamps
