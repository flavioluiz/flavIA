"""Video file to markdown transcription converter.

Extracts the audio track from video files using ffmpeg, then delegates to
:class:`AudioConverter` for transcription via the Mistral API.
"""

import logging
import platform
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Tuple

if TYPE_CHECKING:
    from flavia.config import Settings

from rich.console import Console

from flavia.config import get_settings
from flavia.content.scanner import VIDEO_EXTENSIONS

from .audio_converter import AudioConverter, _format_file_size, _format_timestamp
from .base import BaseConverter
from .image_converter import ImageConverter
from .video_frame_extractor import extract_and_describe_video_frames, _seconds_to_timestamp

logger = logging.getLogger(__name__)
console = Console()


class VideoConverter(BaseConverter):
    """Converts video files to markdown transcriptions.

    The audio track is extracted via ffmpeg into a temporary directory
    (``.flavia/.tmp_audio/``) and then transcribed using the Mistral
    Transcription API (delegated to :class:`AudioConverter`).

    Optionally can extract and describe visual frames using vision models.
    """

    supported_extensions = VIDEO_EXTENSIONS
    requires_dependencies = ["mistralai"]

    def __init__(self, settings: Optional["Settings"] = None) -> None:
        self._audio_converter = AudioConverter()
        self._settings = None
        self.settings = settings

    @property
    def settings(self):
        """Get settings, loading global settings if not provided."""
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    @settings.setter
    def settings(self, value):
        """Set settings."""
        self._settings = value

    @settings.deleter
    def settings(self):
        """Delete settings."""
        self._settings = None

    def convert(
        self,
        source_path: Path,
        output_dir: Path,
        output_format: str = "md",
    ) -> Optional[Path]:
        """Extract audio from a video, transcribe, and write markdown.

        Args:
            source_path: Path to the video file.
            output_dir: Directory to write the output file.
            output_format: "md" or "txt".

        Returns:
            Path to the converted file, or None on failure.
        """
        text = self.extract_text(source_path)
        if not text or not text.strip():
            return None

        content = self._format_as_markdown(text, source_path)

        # Preserve directory structure when source lives under output_dir.parent.
        try:
            relative_source = source_path.resolve().relative_to(output_dir.resolve().parent)
            output_file = output_dir / relative_source.with_suffix(f".{output_format}")
        except ValueError:
            output_file = output_dir / (source_path.stem + f".{output_format}")

        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(content, encoding="utf-8")
        return output_file

    def extract_text(self, source_path: Path) -> Optional[str]:
        """Extract audio from video, transcribe, and return the text.

        Args:
            source_path: Path to the video file.

        Returns:
            Transcribed text with segment timestamps, or None on failure.
        """
        if not self._check_ffmpeg():
            self._print_ffmpeg_instructions()
            return None

        audio_path = self._extract_audio(source_path)
        if audio_path is None:
            return None

        try:
            return self._audio_converter._transcribe_audio(audio_path)
        finally:
            # Clean up temporary audio file
            self._cleanup_temp_audio(audio_path)

    def extract_and_describe_frames(
        self,
        transcript: str,
        video_path: Path,
        base_output_dir: Path,
        interval: int = 10,
        max_frames: int = 20,
    ) -> Tuple[List[Path], List[float]]:
        """Extract and describe visual frames from video.

        Args:
            transcript: Transcript text with timestamp markers
            video_path: Path to the video file
            base_output_dir: Base output directory (.converted/)
            interval: Select 1 frame every N transcript segments
            max_frames: Maximum number of frames to extract

        Returns:
            Tuple of (description_file_paths, selected_timestamps)
        """
        image_converter = ImageConverter(self.settings)
        return extract_and_describe_video_frames(
            video_path=video_path,
            transcript=transcript,
            base_output_dir=base_output_dir,
            image_converter=image_converter,
            interval=interval,
            max_frames=max_frames,
        )

    def _check_ffmpeg(self) -> bool:
        """Check if ffmpeg is available on the system."""
        return shutil.which("ffmpeg") is not None

    def _extract_audio(self, video_path: Path) -> Optional[Path]:
        """Extract audio track from a video file using ffmpeg.

        The extracted audio is saved to ``.flavia/.tmp_audio/`` in the current
        working directory.

        Args:
            video_path: Path to the video file.

        Returns:
            Path to the extracted audio file, or None on failure.
        """
        tmp_dir = Path.cwd() / ".flavia" / ".tmp_audio"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        output_path = tmp_dir / f"{video_path.stem}.mp3"

        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-i",
                    str(video_path),
                    "-vn",  # No video
                    "-acodec",
                    "libmp3lame",
                    "-q:a",
                    "4",  # Good quality, reasonable size
                    "-y",  # Overwrite if exists
                    str(output_path),
                ],
                capture_output=True,
                text=True,
                timeout=600,  # 10 min timeout for large files
            )

            if result.returncode != 0:
                logger.error(
                    f"ffmpeg audio extraction failed for {video_path}: {result.stderr[:500]}"
                )
                return None

            if not output_path.exists() or output_path.stat().st_size == 0:
                logger.error(f"ffmpeg produced empty output for {video_path}")
                return None

            return output_path

        except subprocess.TimeoutExpired:
            logger.error(f"ffmpeg timed out extracting audio from {video_path}")
            return None
        except OSError as e:
            logger.error(f"ffmpeg execution error: {e}")
            return None

    @staticmethod
    def _cleanup_temp_audio(audio_path: Path) -> None:
        """Remove a temporary audio file and clean up the temp directory."""
        try:
            audio_path.unlink(missing_ok=True)
            # Remove temp directory if empty
            tmp_dir = audio_path.parent
            if tmp_dir.exists() and not any(tmp_dir.iterdir()):
                tmp_dir.rmdir()
        except OSError:
            pass

    @staticmethod
    def _print_ffmpeg_instructions() -> None:
        """Print platform-specific ffmpeg installation instructions."""
        console.print()
        console.print("[red]ffmpeg is required for video conversion but was not found.[/red]")
        console.print()

        system = platform.system().lower()

        if system == "darwin":
            console.print("[bold]Install on macOS:[/bold]")
            console.print("  brew install ffmpeg")
        elif system == "linux":
            console.print("[bold]Install on Ubuntu/Debian:[/bold]")
            console.print("  sudo apt update && sudo apt install ffmpeg")
            console.print()
            console.print("[bold]Install on Fedora:[/bold]")
            console.print("  sudo dnf install ffmpeg")
            console.print()
            console.print("[bold]Install on Arch:[/bold]")
            console.print("  sudo pacman -S ffmpeg")
        elif system == "windows":
            console.print("[bold]Install on Windows:[/bold]")
            console.print("  winget install FFmpeg")
            console.print("  [dim]or[/dim]")
            console.print("  choco install ffmpeg")
        else:
            console.print(
                "[bold]Install ffmpeg from:[/bold] "
                "[link=https://ffmpeg.org/download.html]https://ffmpeg.org/download.html[/link]"
            )

        console.print()
        console.print(
            "[dim]After installing, make sure 'ffmpeg' is in your PATH and try again.[/dim]"
        )

    @staticmethod
    def _format_as_markdown(
        transcription: str,
        source_path: Path,
        frame_descriptions: Optional[List[Tuple[Path, float]]] = None,
    ) -> str:
        """Format the transcription as a markdown document.

        Args:
            transcription: Transcribed text (possibly with timestamps).
            source_path: Original video file path.
            frame_descriptions: Optional list of (md_path, timestamp) tuples.

        Returns:
            Markdown-formatted content with metadata header.
        """
        lines: list[str] = []

        # Title
        clean_title = source_path.stem.replace("_", " ").replace("-", " ")
        lines.append(f"# {clean_title}")
        lines.append("")

        # Metadata header
        lines.append("---")
        lines.append(f"source_file: `{source_path.name}`")
        lines.append(f"format: {source_path.suffix.lstrip('.').upper()}")

        file_size = _format_file_size(source_path)
        if file_size:
            lines.append(f"file_size: {file_size}")

        duration = _get_video_duration(source_path)
        if duration:
            lines.append(f"duration: {duration}")

        resolution = _get_video_resolution(source_path)
        if resolution:
            lines.append(f"resolution: {resolution}")

        from .audio_converter import TRANSCRIPTION_MODEL

        lines.append(f"transcription_model: {TRANSCRIPTION_MODEL}")
        lines.append("---")
        lines.append("")

        # Frame descriptions section
        if frame_descriptions:
            lines.append("## Visual Frame Descriptions")
            lines.append("")
            lines.append("The following frames were extracted and described at sampled timestamps:")
            lines.append("")

            for md_path, timestamp in frame_descriptions:
                try:
                    md_name = md_path.name
                    timestamp_str = _seconds_to_timestamp(timestamp)
                    lines.append(f"- [{timestamp_str}] [{md_name}]({md_path})")
                except Exception:
                    pass

            lines.append("")
            lines.append("---")
            lines.append("")

        # Transcription content
        lines.append("## Transcription")
        lines.append("")
        lines.append(transcription)
        lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _get_video_duration(file_path: Path) -> Optional[str]:
    """Get video duration via ffprobe (best-effort)."""
    if not shutil.which("ffprobe"):
        return None

    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(file_path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            duration_secs = float(result.stdout.strip())
            return _format_timestamp(duration_secs)
    except (subprocess.TimeoutExpired, ValueError, OSError):
        pass

    return None


def _get_video_resolution(file_path: Path) -> Optional[str]:
    """Get video resolution via ffprobe (best-effort)."""
    if not shutil.which("ffprobe"):
        return None

    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=p=0:s=x",
                str(file_path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, ValueError, OSError):
        pass

    return None
