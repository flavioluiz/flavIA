# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added

- **Embedding Index with sqlite-vec (Task 11.2)**: New `embedder.py` and `vector_store.py` modules in `content/indexer/` for semantic search:
  - `embed_chunks(chunks, client)` — Batch embed chunks with retry and progress reporting
  - `embed_query(query, client)` — Embed search queries for retrieval
  - `get_embedding_client(settings)` — Resolve Synthetic provider for embeddings
  - `VectorStore` class with `upsert()`, `knn_search()`, `get_existing_chunk_ids()`, `get_stats()`
  - SQLite schema: `chunks_vec` (vec0 virtual table) + `chunks_meta` (metadata join table)
  - L2 normalization of all vectors for cosine similarity via dot product
  - New optional dependency extra: `rag` (`sqlite-vec`)
- **Audio/Video Transcription Converter (Task 1.1)**: New `AudioConverter` and `VideoConverter` in `content/converters/` supporting audio and video file transcription:
  - Audio formats: `.mp3`, `.wav`, `.flac`, `.ogg`, `.m4a`, `.aac`, `.wma`, `.opus`, `.aiff`, `.ape`, `.alac`, `.amr`
  - Video formats: `.mp4`, `.avi`, `.mkv`, `.mov`, `.wmv`, `.flv`, `.webm`, `.mpeg`, `.mpg`, `.3gp`, `.m4v`, `.ts`, `.vob`, `.ogv`
  - Uses Mistral Transcription API (`voxtral-mini-latest`) for transcription with segment-level timestamps
  - Video audio extraction to `.flavia/.tmp_audio/` using ffmpeg subprocess with automatic cleanup
  - Duration detection via ffprobe for accurate metadata
  - Platform-specific ffmpeg installation instructions when not available
  - Centralized `get_mistral_api_key()` in `mistral_key_manager.py`:
    - Interactive prompting when API key is not found
    - Persistence options: local project (`.flavia/.env`), global (`~/.config/flavia/.env`), or session-only
    - Shared with OCR feature for unified key management
  - Refactored `MistralOcrConverter` and `catalog_command.py` to use centralized key manager
  - Transcription output format: Markdown with metadata header (source file, format, file size, duration, model) and segment-level timestamps (e.g., `[00:01:23 - 00:01:45] Text...`)
  - New optional dependency extra: `transcription` (`mistralai`)
  - System requirement: `ffmpeg` and `ffprobe` (for video processing and duration detection)
  - Integrated with `flavia --init` for automatic transcription during setup
  - New `/catalog` menu item `Audio/Video Files` with per-file actions:
    - transcribe and re-transcribe
    - view transcript
    - re-run summary/quality from existing transcript
  - SDK compatibility fallback for transcription: when `mistralai` lacks `client.audio` namespace, transcription now falls back to direct HTTP API call
  - 45 new unit tests covering key manager, audio converter, video converter, and utilities
- **Image analysis with vision-capable models**:
  - New `ImageConverter` for `.png`, `.jpg`, `.jpeg`, `.gif`, `.bmp`, `.webp`, `.ico`, `.tiff`, `.tif`, `.svg`
  - New `flavia.content.vision` module for image encoding, optional SVG->PNG conversion, and multimodal chat completion calls
  - New `analyze_image` content tool for direct image inspection by agents
  - New `/catalog` menu section `Image Files` with actions to generate/view descriptions and switch the active vision model in-session
  - `flavia --init` now detects image files and explicitly offers optional conversion to text descriptions in `.converted/`
  - New `IMAGE_VISION_MODEL` environment variable for selecting a dedicated model for image analysis
  - New test suites: `tests/test_vision.py`, `tests/test_image_converter.py`, `tests/test_analyze_image_tool.py`
- **Office Document Converter (Task 1.3)**: New `OfficeConverter` in `content/converters/` supporting Microsoft Office and OpenDocument formats:
  - Modern Office: `.docx`, `.xlsx`, `.pptx` (via python-docx, openpyxl, python-pptx)
  - Legacy Office: `.doc`, `.xls`, `.ppt` (via LibreOffice CLI fallback)
  - OpenDocument: `.odt`, `.ods`, `.odp`
  - Word documents preserve headings (H1/H2/H3) and tables as markdown
  - Excel spreadsheets convert to markdown tables with sheet headers
  - PowerPoint extracts slides, titles, bullet points, and speaker notes
  - New optional dependency extra: `office` (`python-docx`, `openpyxl`, `python-pptx`)
  - Integrated with `flavia --init` for automatic conversion during setup
  - New `/catalog` menu item `Office Documents` for managing Office files
  - 30 new unit tests covering all formats and edge cases
- **PDF extraction quality + OCR manager in `/catalog`**:
  - New `FileEntry.extraction_quality` field (`good` / `partial` / `poor`) persisted in catalog metadata
  - New `summarize_file_with_quality()` path stores summary + extraction quality in one LLM call
  - New `/catalog` menu item `PDF Files` with per-file quality badges and actions for:
    - local PDF text extraction
    - explicit Mistral OCR execution (with optional re-summarization)
  - New optional dependency extra: `ocr` (`mistralai`)
- **Context Compaction Tool (Task 8.5)**: New `compact_context` tool that allows agents to proactively compact their own context:
  - Uses sentinel string pattern (`__COMPACT_CONTEXT__`) for agent loop integration
  - Optional `instructions` parameter for customized compaction (e.g., "focus on technical decisions", "preserve all file paths")
  - Entire compaction pipeline (`compact_conversation()` → `_summarize_messages_for_compaction()` → `_summarize_messages_recursive()` → `_call_compaction_llm()`) now accepts `instructions`
  - Mid-execution context warning: injects a system notice when context usage crosses threshold during tool loops, informing the LLM it can use `compact_context`
  - Warning injected only once per `run()` call via `_compaction_warning_injected` flag
  - Compaction summary now consistently displayed after compaction in CLI (auto-compaction) and Telegram (`/compact` reply includes 500-char preview)
  - 23 new tests covering schema, sentinel execution, detection, instructions, and warning injection
- **LaTeX Compilation Tool (Task 6.1)**: New `compile_latex` tool in `tools/academic/` for compiling `.tex` files into PDFs:
  - Supports `pdflatex`, `xelatex`, `lualatex`, and `latexmk` compilers
  - Automatic multiple compilation passes (configurable, 1-5)
  - Optional `bibtex`/`biber` bibliography processing (auto-detects `biblatex` vs `natbib`)
  - Parses `.log` files to extract meaningful errors, warnings, and bad-box reports
  - Cleans auxiliary files (`.aux`, `.log`, `.out`, `.toc`, etc.) after successful compilation
  - Enforces write permissions on output directory via existing permission system
  - Detects compiler availability at registration time with clear error messages if missing
  - Configurable via `agents.yaml` under `latex:` key (compiler, passes, bibtex, clean_aux)
  - Supports dry-run mode
  - New `tools/academic/` submodule auto-registered in tool registry

### Changed

- **Parallel CLI status display compaction**:
  - Per-agent recent activity window now defaults to 5 entries (was 8)
  - Window shrinks automatically when many sub-agents are active (`3` when >3 agents, `2` when >5)
  - Trimming is now applied after each frame's event batch, so limits adapt immediately as new agents appear
- **Write confirmation callback compatibility hardening**:
  - `WriteConfirmation.confirm()` now resolves callback signature upfront instead of using retry-on-`TypeError` fallback
  - Prevents accidental double callback invocation when callbacks raise internal `TypeError`
  - Supports legacy 3-argument callbacks plus preview-aware positional and keyword-only callback signatures
- **Consolidated info commands (Task 4.1)**: Unified info display across CLI flags and slash commands via new `src/flavia/display.py` module:
  - Removed `/models` slash command and `--list-models` CLI flag (redundant with `/providers`)
  - `/providers` now shows providers with globally indexed models (usable with `-m` flag)
  - `/tools` now shows tools grouped by category with descriptions; `/tools <name>` shows full tool schema
  - `/config` now shows both configuration paths and active settings
  - CLI flags (`--list-providers`, `--list-tools`, `--config`) output clean plain text without ANSI codes when piped
- **Unified agent setup commands**: Replaced separate `/setup` and `/agents` flows with `/agent_setup`:
  - **Quick mode**: update models for existing agents/subagents
  - **Revise mode** (new): modify existing agents via LLM text-free prompts — loads current config, accepts change descriptions, iterates until satisfied
  - **Full mode**: complete reconfiguration:
    - Simplified Step 1: single model selection (no redundant confirmation)
    - Steps 2/3/4 merged into "Preparation" status panel showing ✓/✗ for documents, catalog, summaries; skips completed steps
    - Ctrl+C at any point cancels without saving (restores original `agents.yaml`)
    - "Overwrite?" moved to end — save only on final acceptance
    - Batch subagent approval via interactive checkboxes (`questionary`) with fallback to numbered list
    - Support for rebuild selection when all preparation steps are complete
- **Init wizard flow refactor**: `flavia --init` now builds the content catalog before AI analysis, supports optional LLM summaries during setup, and asks explicitly whether specialized subagents should be included.
- **Converted PDF directory changed from `converted/` to `.converted/`**: PDF files converted to text are now stored in a hidden directory `.converted/` instead of `converted/`. This prevents converted files from being indexed as separate entries in the content catalog, avoiding duplicates. The catalog now links the original PDF to its converted text version.

### Added

- **Tool result size protection (Task 8.4)**: Four-layer protection system preventing large file reads and tool outputs from exceeding context window:
  - **Layer 1 (tool-level)**: `read_file` now checks file size before reading; large files return preview (50 lines) + metadata + instructions for partial reads
  - **Layer 2 (context awareness)**: `AgentContext` exposes `max_context_tokens` and `current_context_tokens`; tools can see current usage
  - **Layer 3 (result guard)**: `BaseAgent._guard_tool_result()` truncates any tool output exceeding 25% of context window
  - **Layer 4 (dynamic budget)**: Budget shrinks as conversation fills: `min(25% of total, 50% of remaining)`
  - New `start_line` / `end_line` parameters on `read_file` for partial file reading
  - Prevents "Context limit exceeded" errors when reading large files (e.g., 500KB Markdown files)
  - See `doc/roadmap/area-8-context-window-management.md` Task 8.4 for details
- **Write operation previews + dry-run mode (Task 5.2)**:
  - New `OperationPreview` model and preview helpers in `src/flavia/tools/write/preview.py`
  - CLI write confirmations now show rich previews before approval:
    - unified diffs for edits/overwrites
    - content previews for write/append
    - insertion context for `insert_text`
    - file/directory previews for delete/remove operations
  - New global `--dry-run` flag and runtime `dry_run` propagation through `Settings` and `AgentContext`
  - All seven write tools now support non-destructive preview execution in dry-run mode
  - New safety documentation in `doc/SAFETY.md` and usage updates in `doc/usage.md`
  - Added test coverage in `tests/test_preview.py` and `tests/test_dry_run.py`
- **File Modification Tools (Task 5.1)**: Seven new write tools in `tools/write/` enabling agents to create, edit, and delete files and directories:
  - `write_file` — create or overwrite files
  - `edit_file` — replace exact text fragments (single-match enforced)
  - `insert_text` — insert text at a specific line number
  - `append_file` — append to files (or create new)
  - `delete_file` — delete files with automatic backup
  - `create_directory` — create directories (`mkdir -p`)
  - `remove_directory` — remove directories (empty or recursive)
  - All write operations require user confirmation via a callback mechanism (`WriteConfirmation`); denied by default if no handler is configured (fail-safe)
  - Automatic backups saved to `.flavia/file_backups/` with high-resolution timestamped filenames before destructive file operations
  - All tools enforce `AgentPermissions.write_paths` via existing permission infrastructure
  - CLI displays real-time status for write operations (e.g., "Writing config.yaml", "Editing main.py")
  - Write confirmation preserved across agent switches (`/agent`, `/model`)
  - Telegram interface naturally denies write operations (no confirmation handler = fail-safe)
- **Real-time Tool Status Display**: The CLI now shows which tool the agent is currently executing during processing:
  - Status line updates in real-time (e.g., "Reading config.yaml", "Searching 'TODO'", "Querying catalog")
  - Sub-agents display with indentation to show nesting depth
  - Verbose mode (`-v`) shows detailed tool arguments
  - Falls back to loading messages when waiting for LLM response
  - New `src/flavia/agent/status.py` module with `ToolStatus`, `StatusPhase`, and formatting utilities
- **Interactive Prompts with questionary (Task 4.8)**: Replaced plain `input()` and numbered menus with `questionary` interactive prompts throughout the CLI:
  - New wrapper functions in `prompt_utils.py`: `q_select()`, `q_autocomplete()`, `q_path()`, `q_password()`, `q_confirm()`, `q_checkbox()`
  - All wrappers include automatic non-TTY fallback for scripts and CI environments
  - Agent setup mode selection now uses arrow-key navigation
  - Provider wizard menus converted to interactive selection
  - Catalog browser uses interactive menu
  - `/agent` command offers autocomplete when no args provided
- **In-Session Provider Management (Task 4.4)**: New slash commands for managing providers without exiting the CLI
  - `/provider-setup` — Run the interactive provider configuration wizard
  - `/provider-manage [id]` — Manage provider models and settings (add, remove, fetch, rename)
  - `/provider-test [id]` — Test connection to a provider (tests default provider if no ID given)
  - All config-changing commands prompt to use `/reset` to reload settings
- **Runtime Model Switching**: New `/model` command allows changing the active model mid-session without restarting
  - `/model` — Show current active model details (provider, model name, reference, max tokens)
  - `/model <ref>` — Switch to different model (by index, model_id, or provider:model_id format)
  - `/model list` — List all available models (alias for `/providers`)
  - Model changes are session-only and reset conversation context
  - Validates model existence and provider API key before switching
  - Implements rollback on agent creation failure
- **`/catalog` interactive command**: New command to browse the content catalog with an interactive menu. Features include:
  - Overview with statistics (files, sizes, types, online sources)
  - Tree view of directory structure
  - Search by name, extension, or text in summaries
  - View files with summaries
  - List and manage online sources
- **Online source support in Content Catalog**: Catalog can now track online sources (YouTube videos, web pages) alongside local files. New `FileEntry` fields: `source_type`, `source_url`, `source_metadata`, `fetch_status`.
- **Converter Registry**: Centralized singleton registry for managing file converters by extension and source type. Auto-registers PDF, text, YouTube, and web page converters.
- **Online source converters (placeholders)**: `YouTubeConverter` and `WebPageConverter` placeholder implementations ready for future development. Marked as `is_implemented=False` with documented dependencies (`yt_dlp`, `whisper`, `httpx`, `beautifulsoup4`, `markdownify`).
- **Configurable timeouts for LLM summarization**: The `summarize_file()` and `summarize_directory()` functions now accept `timeout` and `connect_timeout` parameters (defaults: 30s and 10s respectively).
- **Improved error handling and logging**: LLM summarization now has specific exception handling for timeout, HTTP errors, and import errors, with appropriate logging at different levels.
- **Enhanced compatibility fallback**: More robust detection of OpenAI SDK/httpx version mismatches with better fallback behavior.

### Fixed

- **Vision image payload guardrail**:
  - `analyze_image()` now rejects files above a safety size limit before base64/API upload
  - Prevents accidental oversized multimodal payloads and unnecessary API cost spikes
- **PDF OCR safety/behavior regressions**:
  - `/catalog` PDF manager now blocks unsafe catalog paths that resolve outside project `base_dir`
  - "Extract text (simple)" no longer triggers remote OCR implicitly
  - OCR image assets are now written next to nested markdown outputs so image links remain valid
- **CLI status animation frame rewind when block shrinks**:
  - `_render_status_block()` now returns the rendered frame height (`max(previous, current)`) instead of current line count only
  - Cursor rewind now moves to the first line of the previous frame (`line_count - 1`), avoiding progressive upward drift
  - Prevents cursor rewind underflow on the next repaint, avoiding overwritten output above the status block and duplicate spinner lines below
- **Sub-agent ID/profile consistency under concurrency**:
  - `RecursiveAgent._spawn_dynamic()` now uses one locked counter snapshot for both `agent_id` and dynamic `profile.name`
  - Prevents occasional mismatches between dynamic sub-agent labels during parallel spawning
- **Tool result guard edge cases (Task 8.4)**:
  - Guard budget now accounts for cumulative size of multiple tool results in the same LLM turn (`BaseAgent` and `RecursiveAgent`)
  - `read_file` now validates `start_line` / `end_line` argument types and returns explicit errors for invalid values
- **Runtime model switching edge cases**:
  - `/model` now rejects invalid model references (including out-of-range indexes) instead of silently falling back
  - `/model` now applies the selected model at runtime even when `agents.yaml` defines a fixed `main.model`
  - `/model` details now reflect the actual active agent model
- **Setup robustness during conversion**: Conversion failures in individual binary documents during `--init` no longer abort the setup flow.
- **Duplicate catalog entries**: Converted PDF files no longer appear as separate entries in the content catalog alongside their original PDFs.
- **Better error diagnostics**: Failed LLM calls are now properly logged with context, making debugging easier.
- **Online sources preserved on catalog refresh**: `ContentCatalog.update()` no longer marks online source entries as `missing` during local filesystem scans.
- **Online source type normalization**: `add_online_source()` now normalizes source type values (e.g., `YouTube` -> `youtube`) for consistent storage and filtering.
- **Online/source path collision handling**: Adding an online source no longer overwrites an existing local file entry when generated paths collide.
- **Provider compatibility fallback headers**: OpenAI client compatibility fallback paths in provider setup/testing now preserve custom headers (e.g., OpenRouter `HTTP-Referer`/`X-Title`) instead of dropping them.
- **`/agent` autocomplete cancellation flow**: Cancelling interactive agent selection no longer switches implicitly to `main`; it now safely falls back to listing available agents.
- **Provider management cancel safety**: Cancelling the provider management action menu now exits without saving instead of defaulting to "Save and exit."
- **CLI `/model` autocomplete consistency**: Model completion now prefers `provider:model` references (no duplicate bare IDs), while numeric index selection remains supported directly in `/model`.
- **CLI prompt completion expansion**: `Tab` completion now supports mention-style file references with `@` (e.g., `@notes.md`, `@docs/chapter.md`).

### Removed

- **Legacy slash commands**: Removed `/setup` and `/agents` command handlers in favor of `/agent_setup`.
- **Legacy `converted/` directory support**: The system no longer checks for or migrates files from the old `converted/` directory. Users should reconvert their PDFs or manually move files to `.converted/` if needed.

## Migration Guide

If you have existing converted PDFs in a `converted/` directory:

1. **Option 1 - Reconvert** (recommended): Delete the `converted/` directory and run the PDF conversion again. Files will be created in `.converted/`.

2. **Option 2 - Manual migration**:
   ```bash
   mv converted .converted
   ```

3. **Option 3 - Remove legacy directory**: Delete `converted/` after reconversion/migration to avoid stale duplicate markdown files in your project tree.

After migration, run `flavia` and use the `refresh_catalog` tool to rebuild the content catalog with correct links.
