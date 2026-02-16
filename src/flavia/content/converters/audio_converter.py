"""Audio file to markdown transcription converter.

Uses the Mistral Transcription API (voxtral-mini-latest) to transcribe audio
files and produce markdown output with segment-level timestamps.
"""

import json
import logging
from pathlib import Path
from typing import Optional

import httpx
from rich.console import Console

from flavia.content.scanner import AUDIO_EXTENSIONS

from .base import BaseConverter
from .mistral_key_manager import get_mistral_api_key

logger = logging.getLogger(__name__)
console = Console()

# Mistral transcription model
TRANSCRIPTION_MODEL = "voxtral-mini-latest"


class AudioConverter(BaseConverter):
    """Converts audio files to markdown transcriptions via Mistral API."""

    supported_extensions = AUDIO_EXTENSIONS
    requires_dependencies = ["mistralai"]

    def convert(
        self,
        source_path: Path,
        output_dir: Path,
        output_format: str = "md",
    ) -> Optional[Path]:
        """Transcribe an audio file and write the result as markdown.

        Args:
            source_path: Path to the audio file.
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
        """Transcribe an audio file and return the text.

        Args:
            source_path: Path to the audio file.

        Returns:
            Transcribed text with segment timestamps, or None on failure.
        """
        result = self._transcribe_audio(source_path)
        if result is None:
            return None
        return result

    def _transcribe_audio(
        self,
        audio_path: Path,
        interactive: bool = True,
    ) -> Optional[str]:
        """Run the Mistral transcription API on an audio file.

        Args:
            audio_path: Path to the audio file.
            interactive: Whether to allow interactive API key prompt.

        Returns:
            Transcribed text with segment timestamps, or None on failure.
        """
        api_key = get_mistral_api_key(interactive=interactive)
        if not api_key:
            logger.warning("MISTRAL_API_KEY not available for transcription")
            return None

        try:
            from mistralai import Mistral
        except ImportError:
            logger.error(
                "mistralai package not installed. Install with: pip install 'flavia[transcription]'"
            )
            return None

        try:
            client = Mistral(api_key=api_key)

            with open(audio_path, "rb") as f:
                response = self._request_transcription(
                    client=client,
                    api_key=api_key,
                    audio_file=f,
                    audio_path=audio_path,
                )

            return self._format_transcription_response(response)

        except Exception as e:
            logger.error(f"Transcription failed for {audio_path}: {e}")
            return None

    @staticmethod
    def _request_transcription(
        client: object,
        api_key: str,
        audio_file,
        audio_path: Path,
    ) -> object:
        """Request transcription via SDK when available, with HTTP fallback."""
        audio_resource = getattr(client, "audio", None)
        transcriptions_resource = getattr(audio_resource, "transcriptions", None)

        if transcriptions_resource is not None:
            if hasattr(transcriptions_resource, "complete"):
                return transcriptions_resource.complete(
                    model=TRANSCRIPTION_MODEL,
                    file={"content": audio_file, "file_name": audio_path.name},
                    timestamp_granularities=["segment"],
                )
            if hasattr(transcriptions_resource, "create"):
                return transcriptions_resource.create(
                    model=TRANSCRIPTION_MODEL,
                    file={"content": audio_file, "file_name": audio_path.name},
                    timestamp_granularities=["segment"],
                )

        return AudioConverter._request_transcription_http(
            api_key=api_key,
            audio_file=audio_file,
            audio_path=audio_path,
        )

    @staticmethod
    def _request_transcription_http(
        api_key: str,
        audio_file,
        audio_path: Path,
    ) -> dict:
        """Fallback transcription call using raw HTTP API."""
        headers = {"Authorization": f"Bearer {api_key}"}
        data = {
            "model": TRANSCRIPTION_MODEL,
            "timestamp_granularities[]": "segment",
        }
        files = {
            "file": (
                audio_path.name,
                audio_file,
                "application/octet-stream",
            )
        }

        response = httpx.post(
            "https://api.mistral.ai/v1/audio/transcriptions",
            headers=headers,
            data=data,
            files=files,
            timeout=600.0,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Unexpected transcription API response format")
        return payload

    def _format_transcription_response(self, response: object) -> Optional[str]:
        """Format the Mistral transcription response into text with timestamps.

        Args:
            response: The transcription API response object.

        Returns:
            Formatted text with segment timestamps, or plain text fallback.
        """
        if isinstance(response, dict):
            data = response
        else:
            try:
                data = json.loads(response.model_dump_json())
            except (AttributeError, TypeError, json.JSONDecodeError):
                # If response doesn't have model_dump_json, try direct attribute access
                text = getattr(response, "text", None)
                if text:
                    return text
                return None

        if not isinstance(data, dict):
            text = getattr(response, "text", None)
            if text:
                return text
            return None

        # Extract plain text
        text = data.get("text", "")

        # Extract segments with timestamps if available
        segments = data.get("segments", [])
        if not segments:
            segments = data.get("chunks", [])
        if segments:
            parts: list[str] = []
            for seg in segments:
                start = seg.get("start")
                end = seg.get("end")
                seg_text = seg.get("text", "").strip()
                if not seg_text:
                    continue

                if start is not None and end is not None:
                    start_fmt = _format_timestamp(start)
                    end_fmt = _format_timestamp(end)
                    parts.append(f"[{start_fmt} - {end_fmt}] {seg_text}")
                else:
                    parts.append(seg_text)

            if parts:
                return "\n\n".join(parts)

        # Fallback: return plain text
        return text if text else None

    @staticmethod
    def _format_as_markdown(transcription: str, source_path: Path) -> str:
        """Format the transcription as a markdown document.

        Args:
            transcription: Transcribed text (possibly with timestamps).
            source_path: Original audio file path.

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

        duration = _get_audio_duration(source_path)
        if duration:
            lines.append(f"duration: {duration}")

        lines.append(f"transcription_model: {TRANSCRIPTION_MODEL}")
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


def _format_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS or MM:SS."""
    total = int(seconds)
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _format_file_size(file_path: Path) -> Optional[str]:
    """Return a human-readable file size string."""
    try:
        size = file_path.stat().st_size
    except OSError:
        return None

    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _get_audio_duration(file_path: Path) -> Optional[str]:
    """Try to get audio duration via ffprobe (best-effort)."""
    import shutil
    import subprocess

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
