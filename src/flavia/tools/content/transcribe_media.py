"""Tool for transcribing audio and video files to markdown."""

import shutil
from typing import TYPE_CHECKING, Any

from ..base import BaseTool, ToolParameter, ToolSchema
from ._conversion_helpers import (
    load_catalog_with_permissions,
    resolve_and_find_entry,
    convert_and_update_catalog,
)

if TYPE_CHECKING:
    from flavia.agent.context import AgentContext


class TranscribeMediaTool(BaseTool):
    """Transcribe an audio or video file to markdown with timestamps."""

    name = "transcribe_media"
    description = (
        "Transcribe an audio or video file to markdown with timestamps. "
        "Uses the Mistral Transcription API. For video files, optionally extracts "
        "and describes visual frames using a vision model. "
        "The transcription is saved in .converted/ and the catalog is updated."
    )
    category = "content"

    def get_schema(self, **context) -> ToolSchema:
        return ToolSchema(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="path",
                    type="string",
                    description=(
                        "Path to the audio/video file (relative to project root or absolute)"
                    ),
                    required=True,
                ),
                ToolParameter(
                    name="extract_frames",
                    type="boolean",
                    description=(
                        "For video files, extract key frames and generate visual descriptions "
                        "using a vision model. Consumes additional API tokens. Default: false"
                    ),
                    required=False,
                ),
            ],
        )

    def execute(self, args: dict[str, Any], agent_context: "AgentContext") -> str:
        from flavia.content.scanner import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS

        path_str = (args.get("path") or "").strip()
        if not path_str:
            return "Error: path is required"

        extract_frames = bool(args.get("extract_frames", False))

        catalog, config_dir, converted_dir, base_dir, err = load_catalog_with_permissions(
            agent_context
        )
        if err:
            return err

        full_path, entry, err = resolve_and_find_entry(path_str, agent_context, catalog)
        if err:
            return err

        ext = full_path.suffix.lower()
        if ext in AUDIO_EXTENSIONS:
            media_type = "audio"
        elif ext in VIDEO_EXTENSIONS:
            media_type = "video"
        else:
            all_media = sorted(AUDIO_EXTENSIONS | VIDEO_EXTENSIONS)
            return (
                f"Error: Unsupported media format '{ext}'. "
                f"Supported: {', '.join(all_media)}"
            )

        if media_type == "audio":
            from flavia.content.converters.audio_converter import AudioConverter

            converter = AudioConverter()
        else:
            from flavia.content.converters.video_converter import VideoConverter

            converter = VideoConverter()

            if not shutil.which("ffmpeg"):
                return (
                    "Error: ffmpeg is required for video transcription but was not found. "
                    "Install ffmpeg and ensure it is on your PATH."
                )

        deps_ok, missing = converter.check_dependencies()
        if not deps_ok:
            return (
                f"Error: Missing dependencies for {media_type} transcription: "
                f"{', '.join(missing)}.\n"
                f"Requires: mistralai. Install with: pip install 'flavia[transcription]'"
            )

        rel_converted, err = convert_and_update_catalog(
            converter, full_path, converted_dir, entry, base_dir, catalog, config_dir
        )
        if err:
            return err
        if rel_converted is None:
            return (
                f"Error: {media_type.capitalize()} transcription failed for '{path_str}'. "
                f"Check that MISTRAL_API_KEY is set in .flavia/.env or as an environment variable."
            )

        parts = [
            f"{media_type.capitalize()} transcribed successfully:",
            f"  Source: {path_str}",
            f"  Type: {media_type}",
            f"  Converted to: {rel_converted}",
        ]

        # Optionally extract and describe visual frames for video
        if extract_frames and media_type == "video":
            try:
                transcript_path = base_dir / rel_converted
                transcript = transcript_path.read_text(encoding="utf-8")

                from flavia.content.converters.video_converter import VideoConverter

                video_converter = VideoConverter()
                frame_paths, _timestamps = video_converter.extract_and_describe_frames(
                    transcript=transcript,
                    video_path=full_path,
                    base_output_dir=converted_dir,
                )

                if frame_paths:
                    if entry is not None:
                        try:
                            rel_frame_paths = [
                                str(p.relative_to(base_dir)) for p in frame_paths
                            ]
                        except ValueError:
                            rel_frame_paths = [str(p) for p in frame_paths]
                        entry.frame_descriptions = rel_frame_paths
                        catalog.save(config_dir)

                    parts.append(f"  Frames extracted: {len(frame_paths)}")
                else:
                    parts.append("  Frames: none extracted")
            except Exception as e:
                parts.append(f"  Frame extraction failed: {e}")

        parts.append("\nContent is now searchable via search_chunks and query_catalog.")
        return "\n".join(parts)

    def is_available(self, agent_context: "AgentContext") -> bool:
        config_dir = agent_context.base_dir / ".flavia"
        return (config_dir / "content_catalog.json").exists()
