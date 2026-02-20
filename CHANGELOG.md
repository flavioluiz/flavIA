# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added

- **Web Search Tool (Task 9.1)**: Multi-provider web search with configurable search engines:
  - `WebSearchTool` integrates with DuckDuckGo (default, no API key), Google Custom Search, Brave Search, and Bing Web Search
  - Parameters: `query` (required), `num_results` (1-20, default 10), `region` (optional), `time_range` (day/week/month/year), `provider` (override)
  - Provider abstraction via `BaseSearchProvider` with lazy settings loading for API keys
  - Settings UI integration: new "Web Search" category with provider choice and 4 API key fields
  - Environment variable configuration: `WEB_SEARCH_PROVIDER`, `GOOGLE_SEARCH_API_KEY`, `GOOGLE_SEARCH_CX`, `BRAVE_SEARCH_API_KEY`, `BING_SEARCH_API_KEY`
  - Optional dependency: `duckduckgo-search>=6.0` (installed with `pip install 'flavia[research]'`)
  - Graceful error handling: missing libraries and unconfigured providers return informative error messages
- **File-targeted RAG retrieval via `@arquivo` mentions**:
  - `search_chunks` now parses explicit file mentions in `query` (example: `@relatorio.pdf pontos fracos`)
  - Mentions are resolved against original catalog entries (`entry.path` / `entry.name`) and mapped to indexed converted chunks
  - Mention scope combines with existing filters: union of mentions, then intersection with `file_type_filter` / `doc_name_filter`
  - Unknown or unindexed mentions now return explicit feedback instead of silently broadening retrieval
  - Recursive agent loop now enforces a `search_chunks` grounding attempt before final answer when the user prompt includes `@mentions` and index/tool are available
  - Added regression tests in `tests/test_search_chunks_tool.py` for mention scoping and filter intersection
- **RAG diagnostics mode and tuning controls**:
  - Runtime command `/rag-debug [on|off|status|last [N]]` to toggle diagnostics capture and inspect recent traces
  - Added turn-scoped diagnostics command `/rag-debug turn [N]` to inspect only traces from the current user turn
  - `/rag-debug turn` now explicitly warns when debug is off and no traces were captured for the turn
  - Added `/citations [turn [N]|id <CITATION_ID>]` to inspect retrieval citation markers (source, locator, excerpt)
  - New persistent citation log: `.flavia/rag_citations.jsonl`
  - New persistent diagnostics log: `.flavia/rag_debug.jsonl` (JSONL, one retrieval trace per entry)
  - New `/index diagnose` command (alias `/index-diagnose`) with deeper index health insights:
    - runtime RAG configuration
    - modality chunk distribution (count/min/max/avg size)
    - top documents by chunk count
    - actionable tuning hints
  - `search_chunks` supports `debug: true` and persists pipeline traces (router/vector/FTS/fusion timings and counts) out-of-band
  - New RAG tuning environment variables:
    - `RAG_CATALOG_ROUTER_K`, `RAG_VECTOR_K`, `RAG_FTS_K`, `RAG_RRF_K`, `RAG_MAX_CHUNKS_PER_DOC`
    - `RAG_CHUNK_MIN_TOKENS`, `RAG_CHUNK_MAX_TOKENS`, `RAG_VIDEO_WINDOW_SECONDS`
    - `RAG_EXPAND_VIDEO_TEMPORAL`, `RAG_DEBUG`
  - Index build/update now includes richer per-document diagnostics when RAG debug mode is enabled
- **Agent Guidance Update (Task 11.8)**: Updated `_build_catalog_first_guidance()` in `src/flavia/agent/context.py` to clarify tool usage:
  - Use `search_chunks` for document content and semantic questions (what/how/why)
  - Keep `query_catalog` for metadata and file discovery/filtering by type or name
- **Index CLI Commands (Task 11.7)**: New index lifecycle commands for retrieval data maintenance:
  - `/index build` (and legacy alias `/index-build`) for full rebuild (clear + rechunk + re-embed)
  - `/index update` (and legacy alias `/index-update`) for incremental updates of new/modified docs
  - `/index stats` (and legacy alias `/index-stats`) for chunk/doc counts, index size, modalities, and last indexed timestamp
  - New `content/indexer/index_manager.py` utilities for build/update/stats workflows
- **search_chunks Tool (Task 11.6)**: New agent-accessible tool for semantic search across indexed document chunks using hybrid RAG retrieval:
  - `SearchChunksTool` in `tools/content/search_chunks.py` calls `retrieve()` and formats results as annotated context blocks with citations
  - Parameters: `query` (required), `top_k` (default: 10), `file_type_filter`, `doc_name_filter`
  - Converts filters to `doc_ids_filter` via catalog lookup using SHA1-based doc_id derivation
  - Checks read permissions for `.flavia` and `.index` directories
  - Validates catalog and vector index existence before retrieval
  - Formats results with citations: document name, heading path, and line numbers
  - Supports video temporal bundles with annotated timestamps and modality labels
  - Output format: `[N] doc_name — Section > Subsection (lines 120–170)\n    "text content"`
  - Registered in `tools/content/__init__.py` for automatic tool registry
  - Available only when `.index/index.db` exists
- **Video Temporal Expansion (Task 11.5)**: New `video_retrieval.py` module in `content/indexer/` for expanding retrieved video chunks with chronological evidence bundles:
  - `expand_temporal_window(anchor_chunk, base_dir, vector_store, fts_index)` — Expands video_transcript (±15s) and video_frame (±10s) chunks with surrounding context
  - Temporal bundle format: chronological across modalities (Audio/Screen)
  - Fallback mechanism: 1 nearest frame before + 1 after (up to 30s) when no frames in range
  - Frame reading from filesystem (`.converted/{video}_frames/frame_{MM}m{SS}s.md`) for efficiency
  - `_get_all_frames_for_doc(doc_id, base_dir)` — Reads catalog to find all frame descriptions for a document
  - `_get_nearest_frames(center_time, all_frames, max_distance)` — Finds closest frames before/after anchor
  - `_format_evidence_bundle(transcript_items, frame_items)` — Formats output with `time_display`, `modality_label` ("(Audio)" / "(Screen)"), and `text`
  - Integration: `retrieve()` now accepts `expand_video_temporal=True` parameter (default True) and adds `temporal_bundle` field to video chunk results
  - New `VectorStore.get_chunks_by_doc_id(doc_id, modalities)` — Retrieve all chunks for a document, filtered by modality, sorted by time_start
  - New `FTSIndex.get_chunks_by_doc_id(doc_id, modalities)` — Retrieve FTS chunks for a document, optionally filtered by modality
  - 13 unit tests in `tests/test_video_retrieval.py` covering timecode parsing, frame reading, bundle formatting, hashed `doc_id` frame lookup, overlap-aware expansion, nearest frames, and expansion logic
- **Hybrid Retrieval Engine with RRF fusion (Task 11.4)**: New `retrieval.py` module in `content/indexer/`:
  - Stage A catalog router: FTS5 shortlist (default 20) over catalog summaries + metadata
  - `retrieve(question, base_dir, settings, ...)` combines vector kNN + FTS BM25 via Reciprocal Rank Fusion (`k=60`)
  - Diversity policy enforcement (`max_chunks_per_doc`, default 3)
  - Unified result contract with source ranks (`vector_rank`, `fts_rank`) and merged chunk metadata
  - `doc_ids_filter` semantics aligned at retrieval boundary (`None` = unfiltered, `[]` = explicit empty scope)
  - `retrieve` exported in `content/indexer/__init__.py`
- **FTS Index with SQLite FTS5 (Task 11.3)**: New `fts.py` module in `content/indexer/` for exact-term full-text search:
  - `FTSIndex` class with `upsert()`, `search()`, `get_existing_chunk_ids()`, `delete_chunks()`, `get_stats()`
  - FTS5 virtual table `chunks_fts` with BM25 ranking
  - Porter stemming + unicode61 tokenizer for international text support
  - Shares `index.db` with VectorStore for unified index management
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

- **Chunk `doc_id` consistency hardening**:
  - `chunker.chunk_document()` now uses the original source checksum (`entry.checksum_sha256`) for `doc_id` derivation when available
  - This aligns index-time `doc_id` generation with retrieval/router/filter derivation and avoids scope mismatches
  - Legacy fallback (converted checksum) is preserved only for direct chunker calls without catalog checksum context
  - **Migration note**: existing indexes built before this change should run `/index build` once to regenerate chunk metadata with the new stable `doc_id` mapping
  - Added regression test in `tests/test_content_indexer_chunker.py`
- **Agent retrieval guidance update**:
  - Catalog-first prompt guidance now explicitly instructs keeping `@arquivo.ext` mentions in `search_chunks` queries for precise file scoping
- **RAG debug context hardening**:
  - Detailed retrieval traces are no longer appended to `search_chunks` tool output
  - This avoids inflating model context during diagnostics and keeps debug inspection outside agent memory via `/rag-debug last`
- **Retrieval recall/coverage hardening**:
  - FTS search now retries broader lexical variants (token OR/AND + exact phrase fallback) to reduce `fts_hits=0` cases in natural-language queries
  - Retrieval diversity cap now adapts for single-document scopes to avoid clipping coverage in item/subitem extraction tasks
  - `search_chunks` supports `retrieval_mode=exhaustive` and auto-switches to exhaustive profile for checklist-like prompts ("todos os itens/subitens")
  - Exhaustive auto-detection now covers broader list/comparison cues (e.g., compare/versus/list-only/sem descrição variants)
  - In exhaustive mode with multi-document scope, `search_chunks` now backfills uncovered scoped docs and rebalances results to improve per-document evidence coverage
  - Mention-scoped grounding is now stricter: when user prompts include `@...`, the loop requires successful `search_chunks` grounding and returns an explicit error if grounding is repeatedly skipped
  - Comparative prompts with multiple `@mentions` now require cross-document mention coverage before final answer
  - Comparative answers now enforce two-stage structure (evidence matrix then conclusions) with inline citations (`[1]`, `[2]`) before finalization
  - New explicit-scope preservation in retrieval: when scope comes from `@mentions`, Stage-A router no longer narrows that caller-defined multi-document scope
  - `RecursiveAgent` now canonicalizes equivalent `@mention` tokens in `search_chunks` calls (e.g., mistyped extension with same stem) back to user-scoped references before execution
  - `search_chunks` now emits stable citation IDs (`[C-...]`) and persists their mapping for user-facing audit
  - Mention-target errors from `search_chunks` (unresolved/unindexed `@file`) are now propagated directly instead of being masked by fallback responses
  - Turn-level exhaustive propagation: checklist intent in the original user prompt now auto-applies `retrieval_mode=exhaustive` to all `search_chunks` calls in that turn (unless explicitly overridden)
  - RAG debug hint quality improved: router-candidate hint is suppressed when retrieval is already explicitly scoped by caller filters
- **Hybrid converted-content access policy**:
  - New per-agent `converted_access_mode` in `agents.yaml`: `strict`, `hybrid`, `open`
  - `hybrid` is the default: agents must call `search_chunks` first, then can fallback to direct `.converted/` reads
  - `.converted` policy is now enforced centrally in `check_read_permission`, covering `read_file`, `search_files`, `list_files`, `get_file_info`, and `analyze_image`
  - Legacy `allow_converted_read` remains supported for backward compatibility (`true` -> `open`, `false` -> `strict`)
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
