"""YouTube video converter.

Downloads transcripts (via youtube-transcript-api) or audio (via yt-dlp) for
YouTube videos, transcribes when needed, and produces Markdown output with
metadata and timestamped transcripts.

Optionally downloads thumbnails and describes them with a vision LLM.

Dependencies (optional extras -- ``pip install 'flavia[online]'``):
- yt-dlp: video/audio download and metadata extraction
- youtube-transcript-api: free transcript retrieval for videos with subtitles
"""

import hashlib
import importlib.util
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import parse_qs, urlparse

from .base import OnlineSourceConverter

logger = logging.getLogger(__name__)
_YOUTUBE_HOSTS = {
    "youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}


class YouTubeConverter(OnlineSourceConverter):
    """Converter for YouTube videos.

    Two-tier strategy:
    1. Try ``youtube-transcript-api`` first (free, fast, no API cost).
    2. Fall back to ``yt-dlp`` audio download + Mistral transcription.

    Thumbnail extraction and vision-based description are available as a
    separate action in the ``/catalog`` menu.
    """

    source_type = "youtube"
    url_patterns = ["youtube.com", "youtu.be", "youtube.com/watch"]
    is_implemented = True
    requires_dependencies = ["yt_dlp", "youtube_transcript_api"]
    dependency_import_map = {"youtube_transcript_api": "youtube_transcript_api"}

    # ------------------------------------------------------------------
    # URL helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _module_available(module_name: str) -> bool:
        """Return True if an importable module is available."""
        try:
            return importlib.util.find_spec(module_name) is not None
        except (ImportError, ModuleNotFoundError, ValueError):
            return False

    @classmethod
    def _has_yt_dlp(cls) -> bool:
        return cls._module_available("yt_dlp")

    @classmethod
    def _has_transcript_api(cls) -> bool:
        return cls._module_available("youtube_transcript_api")

    def can_handle_source(self, source_url: str) -> bool:
        """Check if URL is a valid YouTube host and has a parseable video id."""
        url = source_url.strip()
        if not url:
            return False

        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().replace("www.", "")
        if host not in _YOUTUBE_HOSTS:
            return False

        return self.parse_video_id(url) is not None

    @staticmethod
    def parse_video_id(url: str) -> Optional[str]:
        """Extract the YouTube video ID from a URL.

        Handles:
        - https://www.youtube.com/watch?v=VIDEO_ID
        - https://youtu.be/VIDEO_ID
        - https://www.youtube.com/shorts/VIDEO_ID
        - https://www.youtube.com/embed/VIDEO_ID
        - https://www.youtube.com/live/VIDEO_ID

        Args:
            url: YouTube URL.

        Returns:
            Video ID string, or None if the URL cannot be parsed.
        """
        url = url.strip()
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower().replace("www.", "")

        if hostname in ("youtube.com", "m.youtube.com", "music.youtube.com"):
            # /watch?v=ID
            if parsed.path == "/watch":
                qs = parse_qs(parsed.query)
                ids = qs.get("v")
                if ids:
                    return ids[0]
            # /shorts/ID, /embed/ID, /live/ID
            for prefix in ("/shorts/", "/embed/", "/live/"):
                if parsed.path.startswith(prefix):
                    video_id = parsed.path[len(prefix) :].split("/")[0].split("?")[0]
                    if video_id:
                        return video_id
        elif hostname == "youtu.be":
            video_id = parsed.path.lstrip("/").split("/")[0].split("?")[0]
            if video_id:
                return video_id

        # Last-resort regex
        match = re.search(r"(?:v=|/)([a-zA-Z0-9_-]{11})(?:[&?/]|$)", url)
        if match:
            return match.group(1)

        return None

    def check_dependencies(self) -> tuple[bool, list[str]]:
        """
        Check availability for at least one transcript backend.

        Fetch can succeed with either:
        - youtube-transcript-api (captions already available), or
        - yt-dlp (plus Mistral key) fallback path.
        """
        if self._has_transcript_api() or self._has_yt_dlp():
            return True, []
        return False, ["youtube_transcript_api", "yt_dlp"]

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    def fetch_and_convert(
        self,
        source_url: str,
        output_dir: Path,
    ) -> Optional[Path]:
        """Fetch transcript for a YouTube video and write Markdown.

        Strategy:
        1. Extract metadata via yt-dlp.
        2. Try ``youtube-transcript-api`` for free transcript.
        3. Fall back to audio download + Mistral transcription.

        Args:
            source_url: YouTube video URL.
            output_dir: Directory to write the output file.

        Returns:
            Path to the generated Markdown file, or None on failure.
        """
        video_id = self.parse_video_id(source_url)
        if not video_id:
            logger.error(f"Could not parse video ID from URL: {source_url}")
            return None

        # --- metadata ---------------------------------------------------
        metadata = self._fetch_metadata_ytdlp(source_url)

        # --- transcript --------------------------------------------------
        transcript_text: Optional[str] = None
        transcript_source: str = "unknown"

        # Tier 1: youtube-transcript-api
        transcript_text = self._get_transcript_api(video_id)
        if transcript_text:
            transcript_source = "youtube-transcript-api"
            logger.info(f"Obtained transcript via youtube-transcript-api for {video_id}")
        else:
            # Tier 2: yt-dlp audio download + Mistral transcription
            transcript_text = self._download_and_transcribe_audio(source_url)
            if transcript_text:
                transcript_source = "yt-dlp + Mistral voxtral-mini-latest"
                logger.info(f"Transcribed audio via Mistral for {video_id}")

        if not transcript_text:
            logger.error(f"No transcript obtained for {source_url}")
            return None

        # --- write markdown -----------------------------------------------
        markdown = self._format_markdown(
            metadata=metadata,
            transcript=transcript_text,
            transcript_source=transcript_source,
            source_url=source_url,
            video_id=video_id,
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        url_hash = hashlib.sha256(source_url.encode()).hexdigest()[:12]
        title_slug = self._slugify(metadata.get("title", video_id))
        filename = f"{title_slug}_{url_hash}.md"
        output_path = output_dir / filename

        output_path.write_text(markdown, encoding="utf-8")
        return output_path

    def get_metadata(self, source_url: str) -> dict:
        """Get metadata for a YouTube video.

        Uses yt-dlp for extraction (no download). Falls back to
        basic parsing if yt-dlp is unavailable.

        Args:
            source_url: YouTube video URL.

        Returns:
            Dict with video metadata.
        """
        video_id = self.parse_video_id(source_url)
        if not video_id:
            return {
                "status": "error",
                "source_url": source_url,
                "source_type": self.source_type,
                "message": "Could not parse video ID from URL.",
            }

        metadata = self._fetch_metadata_ytdlp(source_url)
        if metadata.get("status") == "error":
            # Minimal fallback
            metadata = {
                "title": f"YouTube Video ({video_id})",
                "video_id": video_id,
                "source_url": source_url,
                "source_type": self.source_type,
                "status": "partial",
            }

        metadata["status"] = metadata.get("status", "ok")
        metadata["source_type"] = self.source_type
        metadata["source_url"] = source_url
        return metadata

    def get_implementation_status(self) -> dict:
        """Get detailed implementation status."""
        base_status = super().get_implementation_status()
        base_status.update(
            {
                "source_type": self.source_type,
                "url_patterns": self.url_patterns,
                "features": [
                    "Transcript retrieval via youtube-transcript-api (free, fast)",
                    "Audio download + Mistral transcription fallback",
                    "Metadata extraction (title, channel, duration)",
                    "Thumbnail download and vision LLM description",
                    "Markdown output with timestamps",
                ],
            }
        )
        return base_status

    # ------------------------------------------------------------------
    # Tier 1: youtube-transcript-api
    # ------------------------------------------------------------------

    @staticmethod
    def _get_transcript_api(video_id: str) -> Optional[str]:
        """Try to get transcript via youtube-transcript-api.

        Args:
            video_id: YouTube video ID.

        Returns:
            Formatted transcript text with timestamps, or None.
        """
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
        except ImportError:
            logger.debug("youtube-transcript-api not installed, skipping.")
            return None

        try:
            # Try fetching transcript list
            ytt_api = YouTubeTranscriptApi()
            transcript_list = ytt_api.fetch(video_id)

            if not transcript_list:
                return None

            parts: list[str] = []
            for snippet in transcript_list:
                start = snippet.start
                duration = snippet.duration
                end = start + duration
                text = snippet.text.strip()
                if not text:
                    continue

                start_fmt = _format_timestamp(start)
                end_fmt = _format_timestamp(end)
                parts.append(f"[{start_fmt} - {end_fmt}] {text}")

            if parts:
                return "\n\n".join(parts)

        except Exception as e:
            logger.debug(f"youtube-transcript-api failed for {video_id}: {e}")

        return None

    # ------------------------------------------------------------------
    # Tier 2: yt-dlp audio download + Mistral transcription
    # ------------------------------------------------------------------

    @staticmethod
    def _download_and_transcribe_audio(source_url: str) -> Optional[str]:
        """Download audio via yt-dlp and transcribe with Mistral.

        Args:
            source_url: YouTube video URL.

        Returns:
            Transcribed text with timestamps, or None.
        """
        try:
            import yt_dlp
        except ImportError:
            logger.error("yt-dlp not installed. Install with: pip install 'flavia[online]'")
            return None

        tmp_dir = Path.cwd() / ".flavia" / ".tmp_audio"
        tmp_dir.mkdir(parents=True, exist_ok=True)

        url_hash = hashlib.sha256(source_url.encode()).hexdigest()[:12]
        output_template = str(tmp_dir / f"yt_{url_hash}.%(ext)s")

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "128",
                }
            ],
        }

        audio_path: Optional[Path] = None
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([source_url])

            # Find the downloaded audio file
            expected = tmp_dir / f"yt_{url_hash}.mp3"
            if expected.exists() and expected.stat().st_size > 0:
                audio_path = expected
            else:
                # Try to find any file with the hash prefix
                for f in tmp_dir.glob(f"yt_{url_hash}.*"):
                    if f.stat().st_size > 0:
                        audio_path = f
                        break

            if audio_path is None:
                logger.error("yt-dlp produced no audio file")
                return None

            # Delegate to AudioConverter
            from flavia.content.converters.audio_converter import AudioConverter

            converter = AudioConverter()
            return converter._transcribe_audio(audio_path, interactive=True)

        except Exception as e:
            logger.error(f"Audio download/transcription failed: {e}")
            return None
        finally:
            # Cleanup temp audio
            if audio_path and audio_path.exists():
                try:
                    audio_path.unlink(missing_ok=True)
                    if tmp_dir.exists() and not any(tmp_dir.iterdir()):
                        tmp_dir.rmdir()
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # Metadata via yt-dlp
    # ------------------------------------------------------------------

    @staticmethod
    def _fetch_metadata_ytdlp(source_url: str) -> dict:
        """Extract video metadata using yt-dlp without downloading.

        Args:
            source_url: YouTube video URL.

        Returns:
            Dict with title, channel, duration, description, thumbnail, etc.
        """
        try:
            import yt_dlp
        except ImportError:
            logger.debug("yt-dlp not installed, cannot fetch metadata.")
            return {"status": "error", "message": "yt-dlp not installed"}

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(source_url, download=False)

            if info is None:
                return {"status": "error", "message": "No info extracted"}

            duration_secs = info.get("duration")
            duration_str = _format_timestamp(float(duration_secs)) if duration_secs else None

            return {
                "title": info.get("title", ""),
                "channel": info.get("channel", info.get("uploader", "")),
                "duration": duration_str,
                "duration_seconds": duration_secs,
                "description": (info.get("description") or "")[:500],
                "thumbnail": info.get("thumbnail", ""),
                "upload_date": info.get("upload_date", ""),
                "view_count": info.get("view_count"),
                "video_id": info.get("id", ""),
            }
        except Exception as e:
            logger.debug(f"yt-dlp metadata extraction failed: {e}")
            return {"status": "error", "message": str(e)}

    # ------------------------------------------------------------------
    # Thumbnail download + description
    # ------------------------------------------------------------------

    def download_thumbnail(
        self,
        source_url: str,
        output_dir: Path,
    ) -> Optional[Path]:
        """Download the video thumbnail image.

        Args:
            source_url: YouTube video URL.
            output_dir: Directory to save the thumbnail.

        Returns:
            Path to the downloaded thumbnail, or None.
        """
        try:
            import yt_dlp
        except ImportError:
            logger.error("yt-dlp not installed for thumbnail download.")
            return None

        video_id = self.parse_video_id(source_url)
        if not video_id:
            return None

        output_dir.mkdir(parents=True, exist_ok=True)

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "writethumbnail": True,
            "outtmpl": str(output_dir / f"thumbnail_{video_id}"),
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([source_url])

            # Find the thumbnail file (extension varies: jpg, webp, png)
            for ext in ("jpg", "jpeg", "webp", "png"):
                candidate = output_dir / f"thumbnail_{video_id}.{ext}"
                if candidate.exists() and candidate.stat().st_size > 0:
                    # Convert webp to jpg if needed (ffmpeg)
                    if ext == "webp" and shutil.which("ffmpeg"):
                        jpg_path = candidate.with_suffix(".jpg")
                        try:
                            subprocess.run(
                                [
                                    "ffmpeg",
                                    "-i",
                                    str(candidate),
                                    "-y",
                                    str(jpg_path),
                                ],
                                capture_output=True,
                                timeout=30,
                            )
                            if jpg_path.exists() and jpg_path.stat().st_size > 0:
                                candidate.unlink(missing_ok=True)
                                return jpg_path
                        except (subprocess.TimeoutExpired, OSError):
                            pass
                    return candidate

        except Exception as e:
            logger.error(f"Thumbnail download failed: {e}")

        return None

    def download_and_describe_thumbnail(
        self,
        source_url: str,
        output_dir: Path,
        image_converter=None,
    ) -> Optional[Tuple[Path, str]]:
        """Download thumbnail and describe it with a vision LLM.

        Args:
            source_url: YouTube video URL.
            output_dir: Directory for output files.
            image_converter: Optional ImageConverter instance.

        Returns:
            Tuple of (description_md_path, description_text), or None.
        """
        thumbnail_path = self.download_thumbnail(source_url, output_dir)
        if thumbnail_path is None:
            return None

        if image_converter is None:
            try:
                from flavia.content.converters.image_converter import ImageConverter

                image_converter = ImageConverter()
            except Exception as e:
                logger.error(f"Cannot create ImageConverter: {e}")
                return None

        try:
            description = image_converter.extract_text(thumbnail_path)
            if not description or not description.strip():
                logger.warning("No description generated for thumbnail")
                return None

            video_id = self.parse_video_id(source_url) or "unknown"
            vision_model = getattr(
                getattr(image_converter, "settings", None),
                "image_vision_model",
                "unknown",
            )

            md_content = (
                f"# YouTube Video Thumbnail\n\n"
                f"---\n"
                f"video_id: `{video_id}`\n"
                f"source_url: `{source_url}`\n"
                f"thumbnail_file: `{thumbnail_path.name}`\n"
                f"vision_model: {vision_model}\n"
                f"---\n\n"
                f"## Thumbnail Description\n\n"
                f"{description}\n"
            )

            md_path = output_dir / f"thumbnail_{video_id}.md"
            md_path.write_text(md_content, encoding="utf-8")

            return md_path, description

        except Exception as e:
            logger.error(f"Thumbnail description failed: {e}")
            return None

    # ------------------------------------------------------------------
    # Markdown formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _format_markdown(
        metadata: dict,
        transcript: str,
        transcript_source: str,
        source_url: str,
        video_id: str,
    ) -> str:
        """Format transcript and metadata as Markdown.

        Args:
            metadata: Video metadata dict.
            transcript: Transcript text with timestamps.
            transcript_source: How the transcript was obtained.
            source_url: Original YouTube URL.
            video_id: YouTube video ID.

        Returns:
            Markdown-formatted string.
        """
        title = metadata.get("title", f"YouTube Video ({video_id})")

        lines: list[str] = []
        lines.append(f"# {title}")
        lines.append("")
        lines.append("---")
        lines.append("source_type: youtube")
        lines.append(f"source_url: `{source_url}`")
        lines.append(f"video_id: `{video_id}`")

        channel = metadata.get("channel")
        if channel:
            lines.append(f"channel: {channel}")

        duration = metadata.get("duration")
        if duration:
            lines.append(f"duration: {duration}")

        upload_date = metadata.get("upload_date")
        if upload_date:
            # Format YYYYMMDD → YYYY-MM-DD
            if len(upload_date) == 8 and upload_date.isdigit():
                upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
            lines.append(f"upload_date: {upload_date}")

        view_count = metadata.get("view_count")
        if view_count is not None:
            lines.append(f"view_count: {view_count:,}")

        lines.append(f"transcript_source: {transcript_source}")
        lines.append("---")
        lines.append("")

        # Description excerpt
        description = metadata.get("description", "").strip()
        if description:
            lines.append("## Video Description")
            lines.append("")
            lines.append(description)
            lines.append("")

        # Transcript
        lines.append("## Transcript")
        lines.append("")
        lines.append(transcript)
        lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    @staticmethod
    def _slugify(text: str, max_length: int = 50) -> str:
        """Create a filesystem-safe slug from text.

        Args:
            text: Input text.
            max_length: Maximum slug length.

        Returns:
            Lowercase slug with only alphanumeric and hyphens.
        """
        text = text.lower().strip()
        text = re.sub(r"[^\w\s-]", "", text)
        text = re.sub(r"[\s_]+", "-", text)
        text = re.sub(r"-+", "-", text).strip("-")
        return text[:max_length] if text else "youtube-video"


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
