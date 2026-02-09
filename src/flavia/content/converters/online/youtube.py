"""YouTube video converter (placeholder implementation)."""

from pathlib import Path
from typing import Optional

from .base import OnlineSourceConverter


class YouTubeConverter(OnlineSourceConverter):
    """
    Converter for YouTube videos.

    This is a placeholder implementation. Full functionality requires:
    - yt_dlp for video/audio download
    - whisper for audio transcription

    Future capabilities:
    - Download video/audio
    - Transcribe audio to text
    - Extract metadata (title, duration, channel, etc.)
    - Generate markdown with transcript and metadata
    """

    source_type = "youtube"
    url_patterns = ["youtube.com", "youtu.be", "youtube.com/watch"]
    is_implemented = False
    requires_dependencies = ["yt_dlp", "whisper"]

    def fetch_and_convert(
        self,
        source_url: str,
        output_dir: Path,
    ) -> Optional[Path]:
        """
        Fetch and transcribe a YouTube video.

        Not yet implemented. Returns None.

        Args:
            source_url: YouTube video URL.
            output_dir: Directory to write the output file.

        Returns:
            None (not implemented).
        """
        return None

    def get_metadata(self, source_url: str) -> dict:
        """
        Get metadata for a YouTube video.

        Not yet implemented. Returns status information.

        Args:
            source_url: YouTube video URL.

        Returns:
            Dict with not_implemented status.
        """
        return {
            "status": "not_implemented",
            "source_url": source_url,
            "source_type": self.source_type,
            "message": "YouTube converter not yet implemented. "
            "Requires yt_dlp and whisper dependencies.",
        }

    def get_implementation_status(self) -> dict:
        """
        Get detailed implementation status.

        Returns:
            Dict with implementation status and planned features.
        """
        base_status = super().get_implementation_status()
        base_status.update(
            {
                "source_type": self.source_type,
                "url_patterns": self.url_patterns,
                "planned_features": [
                    "Video/audio download via yt_dlp",
                    "Audio transcription via Whisper",
                    "Metadata extraction (title, duration, channel)",
                    "Markdown generation with transcript",
                    "Chapter markers support",
                    "Subtitle extraction (when available)",
                ],
            }
        )
        return base_status
