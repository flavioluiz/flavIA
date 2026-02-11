# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Changed

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
