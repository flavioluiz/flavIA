# Area 1: Multimodal File Processing

The content system (`content/converters/`) has a clean `BaseConverter` / `ConverterRegistry` architecture. It supports PDF conversion (pdfplumber/pypdf) and scanned-PDF OCR with quality assessment via the catalog workflow. The `FileScanner` already classifies files into types (image, audio, video, binary\_document) but still lacks dedicated converters for most non-text formats. Online converters (YouTube, webpage) are placeholders.

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

### Task 1.5 -- Online Source Converters (YouTube, Webpage)

**Difficulty**: Medium | **Dependencies**: Task 1.1 (YouTube shares transcription infrastructure)

Implement the existing placeholder converters in `content/converters/online/`. These files already exist with `is_implemented = False`.

**YouTube**: Use `yt-dlp` to download audio, then transcribe via Mistral Transcription API. Alternatively, use the `youtube-transcript-api` library for videos that already have transcripts/subtitles (faster, free, no API cost). Ideally support both: try transcript API first, fall back to audio download + Mistral transcription.

**Webpage**: Use `httpx` (already a dependency) with `readability-lxml` or `trafilatura` to extract clean article text from web pages. Output as Markdown.

Update the `fetch_status` field in `FileEntry` from `"not_implemented"` to `"completed"` or `"failed"`.

**Key files to modify**:
- `content/converters/online/youtube.py` (implement)
- `content/converters/online/webpage.py` (implement)
- `content/converters/online/base.py` (if needed)

**New dependencies**: `yt-dlp`, `youtube-transcript-api`, `trafilatura` or `readability-lxml` (all optional extras).

---

**[← Back to Roadmap](../roadmap.md)**
