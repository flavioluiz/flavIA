"""Video frame extraction and description using vision LLM.

Extracts frames from video files at specific timestamps and generates
text descriptions using vision-capable models.
"""

import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


DEFAULT_FRAME_SAMPLE_INTERVAL = 10
DEFAULT_MAX_FRAMES = 20
_DEFAULT_FRAME_QUALITY = 2


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

    selected = []
    total_segments = len(timestamps)

    for i, (start, _) in enumerate(timestamps):
        if i % interval == 0 and len(selected) < max_frames:
            selected.append(start)

    return selected


def extract_frames_at_timestamps(
    video_path: Path,
    timestamps: List[float],
    output_dir: Path,
    quality: int = _DEFAULT_FRAME_QUALITY,
) -> List[Path]:
    """Extract frames from video at specific timestamps using ffmpeg.

    Args:
        video_path: Path to the video file
        timestamps: List of timestamps (in seconds) to extract
        output_dir: Directory to save extracted frames
        quality: JPEG quality (1-31, lower=better)

    Returns:
        List of paths to extracted frame files

    Raises:
        RuntimeError: If ffmpeg is not available
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required for frame extraction")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    extracted_files = []

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
                    "-q:v",
                    str(quality),
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
                extracted_files.append(output_path)
                logger.debug(f"Extracted frame: {output_path}")

        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout extracting frame at {timestamp:.2f}s")
        except OSError as e:
            logger.warning(f"Error extracting frame at {timestamp:.2f}s: {e}")

    return extracted_files


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
    frame_paths: List[Path],
    output_dir: Path,
    video_path: Path,
    timestamps: List[float],
    image_converter,
) -> List[Path]:
    """Generate descriptions for extracted video frames.

    Args:
        frame_paths: List of frame image paths
        output_dir: Directory to save description markdown files
        video_path: Path to the original video file
        timestamps: Timestamps corresponding to each frame
        image_converter: ImageConverter instance for vision analysis

    Returns:
        List of paths to generated description markdown files
    """
    if len(frame_paths) != len(timestamps):
        raise ValueError("frame_paths and timestamps must have same length")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    description_files = []

    for frame_path, timestamp in zip(frame_paths, timestamps):
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
            description_files.append(output_path)
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
        return [], selected_timestamps

    descriptions = describe_frames(
        extracted_frames, frames_dir, video_path, selected_timestamps, image_converter
    )

    logger.info(
        f"Extracted {len(extracted_frames)} frames and generated "
        f"{len(descriptions)} descriptions for {video_path.name}"
    )

    return descriptions, selected_timestamps
