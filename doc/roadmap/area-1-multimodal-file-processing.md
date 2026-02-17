# Area 1: Multimodal File Processing

The content system (`content/converters/`) has a clean `BaseConverter` / `ConverterRegistry` architecture. It supports PDF conversion (pdfplumber/pypdf), scanned-PDF OCR with quality assessment, Office documents, audio/video transcription, image descriptions, visual frame extraction, and online source converters (YouTube, web pages). All tasks in this area are now complete.

All new converters follow the same pattern: implement `BaseConverter`, register in `ConverterRegistry`, output Markdown to `.converted/`. The general approach for multimodal processing is to use external APIs (Mistral API for audio transcription and OCR, GPT-4o vision for images).

---

### ~~Task 1.1 -- Audio/Video Transcription Converter~~ ✅ DONE

**Difficulty**: ~~Medium~~ | **Dependencies**: ~~None~~

Implemented audio and video transcription using Mistral Transcription API (`voxtral-mini-latest`).

**What was delivered**:
- New `AudioConverter` in `content/converters/audio_converter.py` with Mistral API integration
- New `VideoConverter` in `content/converters/video_converter.py` with ffmpeg audio extraction
- Centralized `get_mistral_api_key()` in `mistral_key_manager.py` with interactive prompting and persistence
- Segment-level timestamps in transcription output (e.g., `[00:01:23 - 00:01:45] Text...`)
- Metadata headers with source file, format, file size, duration, and model information
- Video audio extraction to `.flavia/.tmp_audio/` with automatic cleanup
- Platform-specific ffmpeg installation instructions when not available
- Duration detection via ffprobe for accurate metadata
- Refactored existing `MistralOcrConverter` and `catalog_command.py` to use centralized key manager
- Integrated with `flavia --init` for automatic transcription during setup
- New `/catalog` support for audio/video files with per-file transcription, re-transcription, transcript viewing, and summary/quality refresh

**Implemented files**:
- `src/flavia/content/converters/mistral_key_manager.py` (new)
- `src/flavia/content/converters/audio_converter.py` (new)
- `src/flavia/content/converters/video_converter.py` (new)
- `src/flavia/content/converters/__init__.py` (updated)
- `src/flavia/content/converters/mistral_ocr_converter.py` (refactored)
- `src/flavia/interfaces/catalog_command.py` (refactored)
- `pyproject.toml` (new `[transcription]` optional dependency)
- `tests/test_audio_video_converter.py` (45 tests)

**New dependencies**: 
- Python package: `mistralai` (optional `[transcription]` extra)
- System requirement: `ffmpeg` (for video processing) and `ffprobe` (for duration detection)

**Output format**: Markdown files in `.converted/` with transcription text, segment-level timestamps, and metadata header (source file, format, file size, duration, model).

---

### Task 1.2 -- Image Description Converter

**Difficulty**: Medium | **Dependencies**: None

Create `content/converters/image_converter.py`. Use the GPT-4o vision API (or any compatible multimodal endpoint) by sending the image as a base64-encoded content part. The system prompt should request a detailed descriptive textual representation of the image. Register for `IMAGE_EXTENSIONS` from `scanner.py`.

**Key files to modify/create**:
- `content/converters/image_converter.py` (new)
- `content/converters/__init__.py` (register)

**Design consideration**: The provider system currently uses the OpenAI-compatible API; vision endpoints require the multimodal message format (`content: [{type: "image_url", ...}]`). This pattern is already exercised by Task 1.4's OCR flow and can be reused for image descriptions.

---

### ~~Task 1.3 -- Word/Office Document Converter~~ ✅ DONE

**Difficulty**: ~~Easy~~ | **Dependencies**: ~~None~~

Implemented `OfficeConverter` supporting Microsoft Office and OpenDocument formats.

**What was delivered**:
- New `content/converters/office_converter.py` with full `BaseConverter` implementation
- Modern Office support: `.docx`, `.xlsx`, `.pptx` (via python-docx, openpyxl, python-pptx)
- Legacy Office fallback: `.doc`, `.xls`, `.ppt` (via LibreOffice CLI)
- OpenDocument support: `.odt`, `.ods`, `.odp`
- Word documents preserve headings (H1/H2/H3) and tables as markdown tables
- Excel spreadsheets convert to markdown tables with sheet headers
- PowerPoint extracts slides, titles, bullet points, and speaker notes as blockquotes
- Integrated with `flavia --init` for automatic conversion during setup
- New `/catalog` menu item `Office Documents` for managing Office files
- 30 unit tests covering all formats and edge cases

**Implemented files**:
- `src/flavia/content/converters/office_converter.py` (new)
- `src/flavia/content/converters/__init__.py` (register)
- `src/flavia/setup_wizard.py` (include Office extensions)
- `src/flavia/interfaces/catalog_command.py` (Office Documents menu)
- `pyproject.toml` (new `[office]` optional dependency)
- `tests/test_office_converter.py` (30 tests)

**New dependencies** (optional `[office]` extra): `python-docx>=0.8.11`, `openpyxl>=3.1.0`, `python-pptx>=0.6.21`.

---

### ~~Task 1.4 -- OCR for Handwritten Documents and Equation-Heavy PDFs~~ ✅ DONE

**Difficulty**: ~~Hard~~ | **Dependencies**: ~~Task 1.2~~ (implemented independently via OCR provider integration)

Implemented OCR workflow for scanned PDFs with quality feedback in catalog operations.

**What was delivered**:
- Dedicated OCR converter (`MistralOcrConverter`) with PDF upload + markdown extraction pipeline
- Scanned-PDF detection in `PdfConverter` (average extracted chars/page heuristic)
- Explicit OCR execution path in `/catalog` (`PDF Files` manager)
- Per-file summary + extraction quality (`good` / `partial` / `poor`)
- Model fallback and manual model selection for summary/quality retries

**Implemented files**:
- `src/flavia/content/converters/mistral_ocr_converter.py`
- `src/flavia/content/converters/pdf_converter.py`
- `src/flavia/content/summarizer.py`
- `src/flavia/content/scanner.py`
- `src/flavia/interfaces/catalog_command.py`
- `src/flavia/cli.py`

---

### ~~Task 1.5 -- Visual Frame Extraction from Videos~~ ✅ DONE

**Difficulty**: ~~Medium~~ | **Dependencies**: ~~Task 1.1, Task 1.2~~

Implemented visual frame extraction and description for video files using vision-capable LLMs.

**What was delivered**:
- New `video_frame_extractor.py` module with complete frame extraction pipeline
- Frame extraction via `ffmpeg` at sampled timestamps from video transcriptions
- Automatic timestamp parsing from transcript segments (e.g., `[00:30 - 02:45]`)
- Configurable sampling interval (default: extract 1 frame every 10 segments)
- Configurable max frames limit (default: 10 frames per video)
- Frame descriptions generated using existing `ImageConverter` and LLM vision APIs
- Individual markdown files per frame with metadata (timestamp, vision model)
- Frame descriptions persisted in catalog metadata for interactive viewing via `/catalog`
- New `frame_descriptions` field in `FileEntry` for catalog management
- Interactive `/catalog` menu options for frame extraction and viewing
- `--init` wizard integration for batch processing of video files

**Output format**:
- Subdirectory structure: `.converted/video_name_frames/frame_XXmYYs.jpg` + `.md`
- Frame markdown includes: video_source, frame_file, timestamp, vision_model, description
- Frame descriptions are viewable through `/catalog` and stored in `frame_descriptions`

**Implemented files**:
- `src/flavia/content/converters/video_frame_extractor.py` (new, 360 lines)
- `src/flavia/content/converters/video_converter.py` (updated with frame extraction integration)
- `src/flavia/content/scanner.py` (FileEntry with `frame_descriptions` field)
- `src/flavia/interfaces/catalog_command.py` (new menu options for frames)
- `src/flavia/setup_wizard.py` (batch frame extraction support)
- `tests/test_video_frame_extractor.py` (new test file)
- `tests/test_content_catalog.py` (frame_descriptions serialization tests)

---

### ~~Task 1.6 -- Online Source Converters (YouTube, Webpage)~~ ✅ DONE

**Difficulty**: ~~Medium~~ | **Dependencies**: ~~Task 1.1~~ (YouTube shares transcription infrastructure)

Implemented online source converters for YouTube videos and web pages, with full interactive management in `/catalog`.

**What was delivered**:
- **YouTubeConverter** (`content/converters/online/youtube.py`) with two-tier transcript strategy:
  - Tier 1: `youtube-transcript-api` for free/fast transcript retrieval (videos with existing subtitles)
  - Tier 2: `yt-dlp` audio download + Mistral `voxtral-mini-latest` transcription fallback
  - Metadata extraction via `yt-dlp` (title, channel, duration, description, thumbnail, view count)
  - Thumbnail download via `yt-dlp --write-thumbnail` with webp-to-jpg conversion
  - Thumbnail description via vision LLM (`ImageConverter`)
  - URL parsing for all YouTube formats (watch, youtu.be, shorts, embed, live)
  - Markdown output with metadata header and timestamped transcript segments
- **WebPageConverter** (`content/converters/online/webpage.py`):
  - HTML fetching via `httpx` (already a core dependency)
  - Article text extraction via `trafilatura` (with Markdown output, links, tables)
  - Metadata extraction (title, author, date, description, sitename, categories, tags)
  - Fallback to basic HTML tag stripping when trafilatura is unavailable
  - YouTube URL exclusion (defers to YouTubeConverter)
  - Size guard (10 MB max HTML) and configurable timeout
- **Full `/catalog` online sources menu** (`interfaces/catalog_command.py`):
  - List all online sources with type, URL, status, and title
  - Per-source action menu: fetch, re-fetch, view content, view metadata, refresh metadata, summarize, delete
  - YouTube-specific: download & describe thumbnail action
  - Immediate fetch offered after adding a new source
  - Delete with optional removal of converted content files
- **Updated `_add_online_source()`**: removed "not implemented" warning, auto-detects source type, fetches metadata on add, offers immediate content fetch

**Implemented files**:
- `src/flavia/content/converters/online/youtube.py` (rewritten from placeholder, ~640 lines)
- `src/flavia/content/converters/online/webpage.py` (rewritten from placeholder, ~380 lines)
- `src/flavia/interfaces/catalog_command.py` (new `_manage_online_sources()` + helper functions)
- `pyproject.toml` (new `[online]` optional dependency group)

**New dependencies** (optional `[online]` extra): `yt-dlp>=2024.0`, `youtube-transcript-api>=0.6.0`, `trafilatura>=1.6.0`.

**Output format**: Markdown files in `.converted/_online/{youtube,webpage}/` with metadata header, content body, and timestamps (for YouTube transcripts).

---

**[← Back to Roadmap](../roadmap.md)**
