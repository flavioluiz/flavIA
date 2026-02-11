# Area 1: Multimodal File Processing

The content system (`content/converters/`) has a clean `BaseConverter` / `ConverterRegistry` architecture. It currently supports PDF (via pdfplumber) and text passthrough. The `FileScanner` already classifies files into types (image, audio, video, binary\_document) but does nothing with non-text/non-PDF files. Online converters (YouTube, webpage) are placeholders.

All new converters follow the same pattern: implement `BaseConverter`, register in `ConverterRegistry`, output Markdown to `.converted/`. The general approach for multimodal processing is to use external APIs (OpenAI Whisper for audio, GPT-4o vision for images/OCR).

---

### Task 1.1 -- Audio/Video Transcription Converter

**Difficulty**: Medium | **Dependencies**: None

Create `content/converters/audio_converter.py` and `content/converters/video_converter.py` implementing `BaseConverter`. Use the OpenAI Whisper API (`/v1/audio/transcriptions`) for transcription. For video files, extract the audio track first (via `ffmpeg` subprocess or `pydub`) then transcribe. Register for extensions already defined in `scanner.py` (`AUDIO_EXTENSIONS`, `VIDEO_EXTENSIONS`).

**Key files to modify/create**:
- `content/converters/audio_converter.py` (new)
- `content/converters/video_converter.py` (new)
- `content/converters/__init__.py` (register new converters)

**Output format**: Markdown files in `.converted/` with transcription text, timestamps (if available from the API), and a metadata header (duration, source format, etc.).

**New dependencies**: `pydub` or direct `ffmpeg` subprocess (for video audio extraction). The OpenAI SDK already present handles the Whisper API.

---

### Task 1.2 -- Image Description Converter

**Difficulty**: Medium | **Dependencies**: None

Create `content/converters/image_converter.py`. Use the GPT-4o vision API (or any compatible multimodal endpoint) by sending the image as a base64-encoded content part. The system prompt should request a detailed descriptive textual representation of the image. Register for `IMAGE_EXTENSIONS` from `scanner.py`.

**Key files to modify/create**:
- `content/converters/image_converter.py` (new)
- `content/converters/__init__.py` (register)

**Design consideration**: The provider system currently uses the OpenAI-compatible API; vision endpoints require the multimodal message format (`content: [{type: "image_url", ...}]`). This may require a utility function in `BaseAgent` or a standalone helper for vision calls that can be shared with Task 1.4.

---

### Task 1.3 -- Word/Office Document Converter

**Difficulty**: Easy | **Dependencies**: None

Create `content/converters/docx_converter.py`. Use `python-docx` for `.docx`, `openpyxl` for `.xlsx`, `python-pptx` for `.pptx`. These are pure-Python libraries requiring no external services. For legacy formats (`.doc`, `.xls`, `.ppt`), consider a `libreoffice --headless` subprocess fallback. Register for extensions defined in `BINARY_DOCUMENT_EXTENSIONS` in `scanner.py`.

**Key files to modify/create**:
- `content/converters/docx_converter.py` (new)
- `content/converters/__init__.py` (register)

**New dependencies** (optional extras, like `python-telegram-bot`): `python-docx`, `openpyxl`, `python-pptx`.

---

### Task 1.4 -- OCR for Handwritten Documents and Equation-Heavy PDFs

**Difficulty**: Hard | **Dependencies**: Task 1.2 (shares vision API infrastructure)

Create `content/converters/ocr_converter.py`. Use the GPT-4o vision API with a specialized prompt for OCR of handwritten documents. The prompt should instruct the model to transcribe handwritten text faithfully, preserving structure.

**Sub-feature -- LaTeX equation OCR**: The OCR prompt should include instructions to render mathematical equations in LaTeX notation within `$...$` (inline) or `$$...$$` (display) delimiters. The output should be valid Markdown with embedded LaTeX. This is primarily a prompt engineering challenge.

**Sub-feature -- Scanned PDF OCR**: Extend `PdfConverter` to detect image-based PDF pages (pages where pdfplumber extracts no text or very little text) and route those pages to the vision API for per-page OCR. Combine extracted text pages with OCR pages in the final output.

**Key files to modify/create**:
- `content/converters/ocr_converter.py` (new)
- `content/converters/pdf_converter.py` (extend for scanned page detection)
- Shared vision API helper (from Task 1.2)

---

### Task 1.5 -- Online Source Converters (YouTube, Webpage)

**Difficulty**: Medium | **Dependencies**: Task 1.1 (YouTube shares transcription infrastructure)

Implement the existing placeholder converters in `content/converters/online/`. These files already exist with `is_implemented = False`.

**YouTube**: Use `yt-dlp` to download audio, then transcribe via Whisper API. Alternatively, use the `youtube-transcript-api` library for videos that already have transcripts/subtitles (faster, free, no API cost). Ideally support both: try transcript API first, fall back to audio download + Whisper.

**Webpage**: Use `httpx` (already a dependency) with `readability-lxml` or `trafilatura` to extract clean article text from web pages. Output as Markdown.

Update the `fetch_status` field in `FileEntry` from `"not_implemented"` to `"completed"` or `"failed"`.

**Key files to modify**:
- `content/converters/online/youtube.py` (implement)
- `content/converters/online/webpage.py` (implement)
- `content/converters/online/base.py` (if needed)

**New dependencies**: `yt-dlp`, `youtube-transcript-api`, `trafilatura` or `readability-lxml` (all optional extras).

---

**[← Back to Roadmap](../roadmap.md)**
