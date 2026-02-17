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
import json
import logging
import os
import re
import shutil
import subprocess
from html import unescape
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import parse_qs, urlparse

from ..video_frame_extractor import DEFAULT_FRAME_SAMPLE_INTERVAL, DEFAULT_MAX_FRAMES
from .base import OnlineSourceConverter

logger = logging.getLogger(__name__)
_YOUTUBE_HOSTS = {
    "youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}
_TRANSCRIPT_LANGUAGE_PREFERENCE = ("en", "en-US", "en-GB", "pt", "pt-BR")
_YT_DLP_EXTRACTOR_ARGS = {"youtube": {"player_client": ["android", "web"]}}
_HTTP_TIMEOUT_SECONDS = 30


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

    @staticmethod
    def _apply_ytdlp_cookie_options(ydl_opts: dict) -> None:
        """Apply optional cookie settings from environment variables."""
        cookie_file = os.getenv("FLAVIA_YTDLP_COOKIEFILE", "").strip()
        if cookie_file:
            ydl_opts["cookiefile"] = cookie_file

        browser = os.getenv("FLAVIA_YTDLP_COOKIES_FROM_BROWSER", "").strip()
        if browser:
            # Simple form: "chrome", "firefox", "safari", etc.
            ydl_opts["cookiesfrombrowser"] = (browser,)

    @staticmethod
    def _parse_timestamp_to_seconds(timestamp: str) -> Optional[float]:
        """Parse VTT/SRT timestamp into seconds."""
        ts = timestamp.strip().replace(",", ".")
        parts = ts.split(":")
        try:
            if len(parts) == 3:
                h, m, s = parts
                return int(h) * 3600 + int(m) * 60 + float(s)
            if len(parts) == 2:
                m, s = parts
                return int(m) * 60 + float(s)
        except ValueError:
            return None
        return None

    @classmethod
    def _parse_json3_captions(cls, payload: str) -> Optional[str]:
        """Parse YouTube json3 captions into timestamped transcript text."""
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return None

        events = data.get("events")
        if not isinstance(events, list):
            return None

        parts: list[str] = []
        for event in events:
            if not isinstance(event, dict):
                continue
            start_ms = event.get("tStartMs")
            duration_ms = event.get("dDurationMs", 0)
            segs = event.get("segs", [])
            if start_ms is None or not isinstance(segs, list):
                continue

            text = "".join(
                seg.get("utf8", "") for seg in segs if isinstance(seg, dict) and seg.get("utf8")
            )
            text = unescape(re.sub(r"\s+", " ", text)).strip()
            if not text:
                continue

            start = float(start_ms) / 1000.0
            end = start + max(float(duration_ms or 0) / 1000.0, 0.0)
            parts.append(f"[{_format_timestamp(start)} - {_format_timestamp(end)}] {text}")

        if parts:
            return "\n\n".join(parts)
        return None

    @classmethod
    def _parse_text_captions(cls, payload: str) -> Optional[str]:
        """Parse VTT/SRT captions into timestamped transcript text."""
        lines = payload.splitlines()
        cue_time = re.compile(
            r"^\s*([0-9:.]{4,12})\s*-->\s*([0-9:.]{4,12})(?:\s+.*)?$"
        )
        parts: list[str] = []

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line or line.upper() == "WEBVTT" or line.startswith("NOTE"):
                i += 1
                continue

            match = cue_time.match(line)
            if not match:
                i += 1
                continue

            start = cls._parse_timestamp_to_seconds(match.group(1))
            end = cls._parse_timestamp_to_seconds(match.group(2))

            i += 1
            text_lines: list[str] = []
            while i < len(lines) and lines[i].strip():
                text_lines.append(lines[i].strip())
                i += 1

            text = unescape(re.sub(r"<[^>]+>", "", " ".join(text_lines))).strip()
            text = re.sub(r"\s+", " ", text)

            if text and start is not None and end is not None:
                parts.append(f"[{_format_timestamp(start)} - {_format_timestamp(end)}] {text}")

        if parts:
            return "\n\n".join(parts)
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
            # Tier 2: yt-dlp subtitle/auto-caption track retrieval
            transcript_text = self._get_transcript_ytdlp_captions(source_url)
            if transcript_text:
                transcript_source = "yt-dlp subtitle track"
                logger.info(f"Obtained transcript via yt-dlp caption track for {video_id}")
            else:
                # Tier 3: yt-dlp audio download + Mistral transcription
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
                    "Caption track retrieval via yt-dlp metadata",
                    "Audio download + Mistral transcription fallback",
                    "Video download + visual frame extraction/description",
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
    # Tier 2: yt-dlp caption tracks (no audio download)
    # ------------------------------------------------------------------

    @staticmethod
    def _preferred_languages(keys: list[str]) -> list[str]:
        preferred = [lang for lang in _TRANSCRIPT_LANGUAGE_PREFERENCE if lang in keys]
        for lang in keys:
            if lang not in preferred:
                preferred.append(lang)
        return preferred

    @classmethod
    def _get_transcript_ytdlp_captions(cls, source_url: str) -> Optional[str]:
        """
        Try to fetch subtitle/auto-caption tracks via yt-dlp metadata.

        This path does not download audio and can still succeed when
        media stream download is blocked (e.g., HTTP 403).
        """
        try:
            import httpx
            import yt_dlp
        except ImportError:
            return None

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extractor_args": _YT_DLP_EXTRACTOR_ARGS,
        }
        cls._apply_ytdlp_cookie_options(ydl_opts)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(source_url, download=False)
        except Exception as e:
            logger.debug(f"yt-dlp caption metadata extraction failed: {e}")
            return None

        if not isinstance(info, dict):
            return None

        # Prefer manually provided subtitles; fallback to automatic captions.
        for key in ("subtitles", "automatic_captions"):
            caption_map = info.get(key)
            if not isinstance(caption_map, dict) or not caption_map:
                continue

            languages = cls._preferred_languages(list(caption_map.keys()))
            for language in languages:
                tracks = caption_map.get(language)
                if not isinstance(tracks, list) or not tracks:
                    continue

                sorted_tracks = sorted(
                    (
                        t
                        for t in tracks
                        if isinstance(t, dict) and isinstance(t.get("url"), str) and t.get("url")
                    ),
                    key=lambda t: {
                        "json3": 0,
                        "srv3": 1,
                        "vtt": 2,
                        "srt": 3,
                    }.get(str(t.get("ext", "")).lower(), 99),
                )

                for track in sorted_tracks:
                    caption_url = str(track.get("url", "")).strip()
                    if not caption_url.startswith(("http://", "https://")):
                        continue

                    ext = str(track.get("ext", "")).lower()
                    try:
                        response = httpx.get(caption_url, timeout=_HTTP_TIMEOUT_SECONDS)
                        response.raise_for_status()
                    except Exception as e:
                        logger.debug(f"Failed to download caption track ({language}/{ext}): {e}")
                        continue

                    payload = response.text
                    parsed: Optional[str] = None
                    if ext in ("json3", "srv3"):
                        parsed = cls._parse_json3_captions(payload)
                    if not parsed:
                        parsed = cls._parse_text_captions(payload)

                    if parsed:
                        return parsed

        return None

    # ------------------------------------------------------------------
    # Tier 3: yt-dlp audio download + Mistral transcription
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
            "extractor_args": _YT_DLP_EXTRACTOR_ARGS,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "128",
                }
            ],
        }
        YouTubeConverter._apply_ytdlp_cookie_options(ydl_opts)

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
            error_text = str(e).lower()
            if "403" in error_text or "forbidden" in error_text:
                logger.error(
                    "YouTube blocked media download (HTTP 403). "
                    "Try setting FLAVIA_YTDLP_COOKIES_FROM_BROWSER=chrome "
                    "(or firefox/safari) before running flavia."
                )
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

    def download_video(
        self,
        source_url: str,
        output_dir: Path,
    ) -> Optional[Path]:
        """Download a YouTube video file for frame extraction."""
        try:
            import yt_dlp
        except ImportError:
            logger.error("yt-dlp not installed for video download.")
            return None

        video_id = self.parse_video_id(source_url)
        if not video_id:
            return None

        output_dir.mkdir(parents=True, exist_ok=True)

        ydl_opts = {
            "format": (
                "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/"
                "best[height<=720][ext=mp4]/best"
            ),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "merge_output_format": "mp4",
            "outtmpl": str(output_dir / f"video_{video_id}.%(ext)s"),
            "extractor_args": _YT_DLP_EXTRACTOR_ARGS,
        }
        self._apply_ytdlp_cookie_options(ydl_opts)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([source_url])

            candidates: list[Path] = []
            for file_path in output_dir.glob(f"video_{video_id}.*"):
                if (
                    file_path.is_file()
                    and file_path.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov", ".m4v"}
                    and file_path.stat().st_size > 0
                ):
                    candidates.append(file_path)

            if not candidates:
                logger.error("yt-dlp produced no downloadable video file")
                return None

            candidates.sort(key=lambda p: p.stat().st_size, reverse=True)
            return candidates[0]

        except Exception as e:
            logger.error(f"Video download failed: {e}")
            error_text = str(e).lower()
            if "403" in error_text or "forbidden" in error_text:
                logger.error(
                    "YouTube blocked media download (HTTP 403). "
                    "Try setting FLAVIA_YTDLP_COOKIES_FROM_BROWSER=chrome "
                    "(or firefox/safari) before running flavia."
                )
            return None

    def extract_and_describe_frames(
        self,
        source_url: str,
        transcript: str,
        base_output_dir: Path,
        settings=None,
        interval: int = DEFAULT_FRAME_SAMPLE_INTERVAL,
        max_frames: int = DEFAULT_MAX_FRAMES,
    ) -> Tuple[list[Path], list[float]]:
        """
        Download a YouTube video and run frame extraction + vision description.

        Returns:
            Tuple of (description_paths, timestamps). Empty lists on failure.
        """
        tmp_video_dir = Path.cwd() / ".flavia" / ".tmp_video"
        downloaded_video = self.download_video(source_url, tmp_video_dir)
        if downloaded_video is None:
            return [], []

        try:
            from flavia.content.converters.video_converter import VideoConverter

            converter = VideoConverter(settings)
            return converter.extract_and_describe_frames(
                transcript=transcript,
                video_path=downloaded_video,
                base_output_dir=base_output_dir,
                interval=interval,
                max_frames=max_frames,
            )
        except Exception as e:
            logger.error(f"YouTube frame extraction failed: {e}")
            return [], []
        finally:
            try:
                downloaded_video.unlink(missing_ok=True)
                if tmp_video_dir.exists() and not any(tmp_video_dir.iterdir()):
                    tmp_video_dir.rmdir()
            except OSError:
                pass

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
