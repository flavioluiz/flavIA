# Installation

## Requirements

- Python >= 3.10
- Git

## Standard installation

```bash
git clone https://github.com/flavioluiz/flavIA.git
cd flavIA
./install.sh
```

The `install.sh` script creates an isolated virtualenv at `.venv/`, installs locked dependencies (`requirements.lock`), and installs flavIA itself in editable mode.

After installation:

```bash
.venv/bin/flavia --version
```

## Manual installation (alternative)

If you prefer to install manually:

```bash
git clone https://github.com/flavioluiz/flavIA.git
cd flavIA
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/pip install --no-deps -e .
```

## Automatic venv re-execution

`flavia` automatically detects the project venv and re-executes inside it. This means that even if invoked outside the venv, it re-launches in the correct environment.

To disable this behavior (useful for debugging):

```bash
export FLAVIA_DISABLE_AUTO_VENV=1
```

## Telegram (optional)

To use the Telegram interface, install the extra dependency:

```bash
.venv/bin/pip install python-telegram-bot==22.6
```

Or install with the extra:

```bash
.venv/bin/pip install -e ".[telegram]"
```

## OCR for scanned PDFs (optional)

To enable Mistral OCR integration used by the `/catalog` PDF manager:

```bash
.venv/bin/pip install -e ".[ocr]"
```

Then set the API key in your environment or `.flavia/.env`:

```bash
MISTRAL_API_KEY=your_mistral_key
```

## Audio/Video transcription (optional)

To enable audio and video transcription via Mistral Transcription API:

```bash
.venv/bin/pip install -e ".[transcription]"
```

The `MISTRAL_API_KEY` is shared with the OCR feature. If not already configured, set it in `.flavia/.env`:

```bash
MISTRAL_API_KEY=your_mistral_key
```

**Video transcription requires ffmpeg**:

- **macOS**: `brew install ffmpeg`
- **Ubuntu/Debian**: `sudo apt-get install ffmpeg`
- **Fedora/RHEL**: `sudo dnf install ffmpeg`
- **Windows**: Download from [ffmpeg.org](https://ffmpeg.org/download.html) or use `choco install ffmpeg`

The system will detect if ffmpeg is missing and provide platform-specific installation instructions.

## Office document conversion (optional)

To enable Office conversion used by setup and `/catalog` (`.docx`, `.xlsx`, `.pptx`, plus legacy/OpenDocument variants):

```bash
.venv/bin/pip install -e ".[office]"
```

Notes:
- Legacy formats (`.doc`, `.xls`, `.ppt`) and OpenDocument files (`.odt`, `.ods`, `.odp`) use a LibreOffice CLI conversion step.
- Ensure `libreoffice`/`soffice` is available in your PATH when working with these formats.

## Online source converters (optional)

To enable YouTube and web page conversion in `/catalog`:

```bash
.venv/bin/pip install -e ".[online]"
```

This installs:
- `yt-dlp` (YouTube metadata/audio/thumbnail)
- `youtube-transcript-api` (free subtitle transcript retrieval when available)
- `trafilatura` (high-quality web article extraction)

Notes:
- Web page conversion still works with a basic fallback extractor if `trafilatura` is unavailable.
- YouTube audio transcription fallback uses the same `MISTRAL_API_KEY` as OCR/transcription features.
- If `yt-dlp` hits HTTP 403 for some videos, you can export `FLAVIA_YTDLP_COOKIES_FROM_BROWSER=chrome` (or `firefox`, `safari`) or set `FLAVIA_YTDLP_COOKIEFILE=/path/to/cookies.txt`.

## Development dependencies

```bash
.venv/bin/pip install -e ".[dev]"
pytest
black src/
ruff check src/
```

## First use

After installation, go to a folder with your materials and initialize:

```bash
cd ~/research/my-topic
flavia --init
```

The interactive wizard will:

1. Ask which model/provider to use (and test the connection)
2. Find convertible files (PDF/Office/audio/video) and offer conversion to text/transcription
3. Optionally extract and describe visual frames from video files (requires vision-capable model and `IMAGE_VISION_MODEL` configuration)
4. Build the project content catalog in `.flavia/content_catalog.json`
5. Optionally generate LLM summaries for files that need them
6. Let you choose simple configuration or AI-assisted configuration
7. Optionally include specialized subagents and generate the final `.flavia/` config

If no API key is configured, the wizard creates a basic template. Edit `.flavia/.env` with your key and start:

```bash
nano .flavia/.env    # add your API key
flavia               # start chatting
```

If you run `flavia` in an interactive terminal without any existing local or user configuration and without an API key, the setup wizard is offered automatically.
