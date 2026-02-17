# Usage

## Interactive CLI

The default mode is the interactive CLI, started with:

```bash
flavia
```

The interface uses [Rich](https://github.com/Textualize/rich) for formatting, with command history (readline) and loading animations.

### Real-time tool status

During agent execution, the CLI status block shows current activity in real time:

- Tool-aware messages such as `Reading config.yaml`, `Searching 'TODO'`, or `Querying catalog`
- Hierarchical sub-agent display (children nested under parent agent branches)
- Rolling per-agent history (keeps the most recent tasks and collapses older ones as `... (N previous)`)
- Verbose mode (`-v`) includes compact tool arguments in the status line
- Automatic fallback to generic loading messages while waiting for the next LLM response
- Task history limits are configurable with `STATUS_MAX_TASKS_MAIN` and `STATUS_MAX_TASKS_SUBAGENT` (`-1` = unlimited)

### Token usage indicator

After each assistant response, the CLI prints a compact context usage line:

```text
[tokens: 12,450 / 128,000 (9.7%) | response: 850 tokens]
```

Color coding:
- Green: context usage below 70%
- Yellow: context usage between 70% and 89%
- Red: context usage at or above 90%

### Context compaction confirmation

When context usage reaches the configured `compact_threshold` (default `0.9`), the interface warns before the context window gets full:

- CLI prompt:
  - `⚠ Context usage at 92% (117,760/128,000 tokens). Compact conversation? [y/N]`
- Telegram warning:
  - `⚠ Context usage at 92%. Reply /compact to summarize and continue, or keep chatting.`

Compaction summarizes the conversation and resets context with the summary injected as starting context.
You can also force compaction at any time with `/compact`, even below the threshold.

The agent also has a `compact_context` tool it can use proactively. When the context window gets close to the threshold during a tool execution loop, the agent receives a system notice informing it of the low context and suggesting it use the `compact_context` tool. The tool accepts an optional `instructions` parameter to customize the compaction focus (e.g., "preserve all file paths", "focus on technical decisions").

Configuration options:
- `agents.yaml` per-agent:
  - `main.compact_threshold: 0.9`
- Global setting (environment):
  - `AGENT_COMPACT_THRESHOLD=0.9`
- Provider/model defaults (`providers.yaml`, optional):
  - `providers.<id>.compact_threshold`
  - `providers.<id>.models[].compact_threshold`

### Write tool confirmation and previews

When the agent uses a write tool (e.g., `write_file`, `edit_file`, `delete_file`), the CLI prompts for explicit confirmation before executing the operation, **with a preview of the changes**:

```text
Write confirmation: Edit file: ./src/config.py (replacing 245 chars)

Changes:
--- a/src/config.py
+++ b/src/config.py
@@ -10,7 +10,7 @@

 class Config:
     def __init__(self):
-        self.timeout = 30
+        self.timeout = 60
         self.retry = 3

Allow? [y/N]
```

**Preview types:**
- **Edits**: Colored unified diff showing exact changes
- **Writes/Appends**: Content preview (truncated if large)
- **Inserts**: Context lines before and after insertion point
- **Deletes**: First lines of file being deleted
- **Directories**: List of contents

This applies to all seven write tools: `write_file`, `edit_file`, `insert_text`, `append_file`, `delete_file`, `create_directory`, and `remove_directory`. If declined, the operation is cancelled and the agent is notified.

Before destructive file operations, a backup is automatically saved to `.flavia/file_backups/` with a timestamped filename (e.g., `report.md.20250210_143022_123456.bak`).

In Telegram mode, write operations are denied by default since there is no interactive confirmation mechanism.

**See [SAFETY.md](SAFETY.md) for complete documentation on write tool safety features, including dry-run mode, permissions, and backups.**

### Prompt completion (Tab)

In interactive CLI mode, press `Tab` to autocomplete:

- Slash commands (`/ag` -> `/agent`)
- Agent names after `/agent`
- Provider IDs after `/provider-manage` and `/provider-test`
- Model references after `/model`:
  - numeric index (`0`, `1`, `2`, ...)
  - provider-prefixed reference (`openai:gpt-4o`)
- File and directory paths
- Mention-style file references with `@` (e.g., `@notes.md`, `@docs/chapter1.md`)

## Command-line flags

### Initialization and modes

| Flag | Description |
|------|-------------|
| `--init` | Initialize local configuration with interactive wizard |
| `--update` | Refresh content catalog (new/modified/deleted files) |
| `--update-convert` | Refresh catalog and convert pending/modified convertible files (PDFs, Office files, audio, and video) |
| `--update-summarize` | Refresh catalog and generate summaries for pending files |
| `--update-full` | Rebuild catalog from scratch |
| `--telegram` | Start in Telegram bot mode |
| `--version` | Show version and exit |

Catalog examples:

```bash
flavia --update
flavia --update-convert
flavia --update-summarize
flavia --update-full
```

### Model selection

| Flag | Description |
|------|-------------|
| `-m, --model MODEL` | Model to use (index, model ID, or `provider:model_id`) |

Examples:

```bash
flavia -m 0                        # model by index
flavia -m openai:gpt-4o            # explicit provider:model
flavia -m openrouter:anthropic/claude-3.5-sonnet
```

Numeric indexes follow the combined order shown by `flavia --list-providers`.

### Execution options

| Flag | Description |
|------|-------------|
| `-v, --verbose` | Verbose output |
| `-d, --depth N` | Maximum agent recursion depth |
| `--no-subagents` | Disable sub-agent spawning (single-agent mode) |
| `--agent NAME` | Promote a sub-agent as the main agent |
| `--parallel-workers N` | Maximum parallel sub-agents (default: 4) |
| `--dry-run` | Preview file operations without actually modifying files |
| `-p, --path PATH` | Base directory for file operations (default: current directory) |

### Information

| Flag | Description |
|------|-------------|
| `--list-providers` | List configured providers with indexed models |
| `--list-tools` | List available tools grouped by category |
| `--config` | Show configuration paths and active settings |

### Provider management

| Flag | Description |
|------|-------------|
| `--setup-provider` | Interactive provider configuration wizard |
| `--manage-provider [ID]` | Manage provider settings (models, name, ID, URL, API key, headers) or delete provider |
| `--test-provider [ID]` | Test connection to a provider (no argument: tests default) |

### Telegram

| Flag | Description |
|------|-------------|
| `--setup-telegram` | Configure bot token and access control |

## Interactive commands (inside chat)

Inside a chat session, the following commands are available:

| Command | Description |
|---------|-------------|
| `/help` | Show all commands organized by category |
| `/help <command>` | Show detailed help for a specific command (usage, examples, related commands) |
| `/reset` | Reset conversation and reload configuration |
| `/compact` | Manually compact the current conversation with confirmation |
| `/agent_setup` | Configure agents (quick model change, revise, or full rebuild) |
| `/agent` | Open interactive agent selection (fallback: list available agents) |
| `/agent <name>` | Switch to a different agent (resets conversation) |
| `/model` | Show the current active model |
| `/model <ref>` | Switch model by index, model ID, or `provider:model_id` (resets conversation) |
| `/model list` | Quick alias for `/providers` |
| `/catalog` | Browse content catalog (overview, search, summaries, online sources, PDF/Office/Image/Audio-Video managers) |
| `/providers` | List configured providers with indexed models |
| `/provider-setup` | Run interactive provider configuration wizard |
| `/provider-manage [id]` | Manage provider models and settings |
| `/provider-test [id]` | Test connection to a provider |
| `/index build` | Full index rebuild: clears and reindexes all converted docs |
| `/index update` | Incremental index update: new/modified docs + stale cleanup |
| `/index stats` | Show index statistics (chunks, docs, size, last indexed) |
| `/index diagnose` | Show detailed RAG diagnostics (chunk distribution, tuning hints, runtime params) |
| `/index-build` | Legacy alias for `/index build` |
| `/index-update` | Legacy alias for `/index update` |
| `/index-stats` | Legacy alias for `/index stats` |
| `/index-diagnose` | Legacy alias for `/index diagnose` |
| `/rag-debug [on\|off\|status]` | Toggle detailed retrieval diagnostics in `search_chunks` output |
| `/tools` | List available tools by category |
| `/tools <name>` | Show tool schema and parameters |
| `/config` | Show configuration paths and active settings |
| `/quit` | Exit session (aliases: `/exit`, `/q`) |

### Semantic Retrieval (RAG) workflow

From a fresh project setup (`flavia --init`) to retrieval-ready chat:

1. Convert source materials to `.converted/` content (`flavia --init` or `flavia --update-convert`).
2. Build the retrieval index once with `/index build`.
3. Start chatting; the agent can use `search_chunks` for semantic/content questions.
4. After adding/modifying files, run `/index update` to keep vectors/FTS in sync.
5. Use `/index stats` to verify chunk counts, index size, and last indexed timestamp.
6. Use `/index diagnose` and `/rag-debug on` to inspect retrieval behavior and tune parameters.

Notes:
- `search_chunks` is only available when `.index/index.db` exists.
- `query_catalog` remains the best tool for file discovery/metadata filtering.
- Runtime retrieval diagnostics:
  - `/rag-debug on`: appends pipeline trace (`router/vector/fts/fusion` counts + timings + hints) to `search_chunks` output.
  - `/index diagnose`: reports index health, modality distribution, top docs by chunk count, and current RAG tuning parameters.
- Converted-content policy is per-agent via `converted_access_mode` in `agents.yaml`:
  - `strict`: no direct `.converted/` reads.
  - `hybrid` (default): call `search_chunks` first, then allow direct fallback reads.
  - `open`: direct `.converted/` reads always allowed.

### Help System Details

The unified help system organizes commands into logical categories:

- **Session**: `/quit`, `/reset`, `/help`, `/compact`
- **Agents**: `/agent`, `/agent_setup`
- **Models & Providers**: `/model`, `/providers`, `/provider-setup`, `/provider-manage`, `/provider-test`
- **Index**: `/index <build\|update\|stats\|diagnose>` (plus legacy aliases `/index-build`, `/index-update`, `/index-stats`, `/index-diagnose`)
- **Information**: `/tools`, `/config`, `/catalog`

Use `/help` without arguments to see all commands with one-line descriptions grouped by category. Use `/help <command>` for detailed help including usage patterns, examples, and related commands:

```bash
/help              # Show all commands
/help model        # Detailed help for /model
/help agent        # Detailed help for /agent
/help help         # Meta: help about the help system!
```

## `/agent_setup` - Configure Agents

Unified command for agent configuration with three modes:

**Mode 1: Quick** - Change models for existing agents
- Lists all agents (main + subagents)
- Allows changing the model for each agent
- No regeneration of agent configurations

**Mode 2: Revise** - Modify existing agents with LLM assistance (new)
- Loads and previews current `agents.yaml`
- Accepts natural language descriptions of changes ("add a quiz-making subagent")
- LLM applies modifications iteratively
- Changes saved only when you accept; Ctrl+C cancels without saving

**Mode 3: Full** - Complete agent reconfiguration with LLM analysis
- Simplified Step 1: single model selection (no redundant confirmation)
- Steps 2/3/4 merged into "Preparation" status panel showing ✓/✗ for documents, catalog, summaries; skips completed steps
- Batch subagent approval via interactive checkboxes
- Ctrl+C at any point cancels without saving (restores original `agents.yaml`)
- "Overwrite?" moved to end — save only on final acceptance
- Support for rebuild selection when all preparation steps are complete

### Workflow example (Full Mode)

Inside a chat session:

```
You: /agent_setup
Agent: Choose setup mode:
  [1] Quick:  Change models for existing agents
  [2] Revise: Modify current agents with LLM assistance
  [3] Full:   Reconfigure agents completely (with LLM analysis)
You: 3

[Step 1] Model Selection
  Model: openai:gpt-4o
  Use this model or choose another? [Y/n] → Y

[Step 2] Preparation
  ✓ Documents:       12 PDFs converted
  ✓ Content catalog: 48 files indexed
  ✗ Summaries:       not generated
  All preparation steps are complete. Rebuild any?

[Step 3] Subagent Configuration
  Include specialized subagents? [Y/n] → Y

[Step 4] Project Guidance (Optional)
  Add guidance? [Y/n] → n

[Step 5] Analyzing Project...
  [AI generates agents.yaml]

Generated Configuration:
  [Preview of main agent and subagents]

Subagent Approval
  The AI proposed 3 subagent(s):
    summarizer - Summarize long documents and extract key points
    explainer - Explain complex concepts in simple terms
    quiz_maker - Create quizzes for studying

Select subagents to include (space to toggle, enter to confirm):
  [ ] summarizer
  [x] explainer
  [x] quiz_maker

Accept this configuration? [Y/n] → Y

Configuration saved! Use /reset to load.
```

## `/catalog` quick workflow

Inside the interactive CLI:

1. Run `/catalog`.
2. Use the interactive menu (arrow keys + Enter). Non-interactive fallback uses numbered options.
3. Press Esc/Ctrl+C (or choose "Back to chat") to return.

Notes:
- Online source converters are implemented. `/catalog` can fetch/re-fetch, view content/metadata, summarize, and delete YouTube/webpage sources.
- YouTube sources support transcript retrieval (youtube-transcript-api), audio fallback transcription via Mistral (yt-dlp + `MISTRAL_API_KEY`), and thumbnail download/description.
- YouTube sources also support `Extract & describe visual frames` in `/catalog`, mirroring the local video frame workflow.
- If YouTube media download returns HTTP 403 in your environment, you can pass browser cookies via `FLAVIA_YTDLP_COOKIES_FROM_BROWSER` (for example: `chrome` or `firefox`) or a Netscape cookie file via `FLAVIA_YTDLP_COOKIEFILE`.
- Web pages are fetched with `httpx`, extracted with `trafilatura` when available, and fall back to basic HTML text extraction when `trafilatura` is missing.
- Online sources are persisted in `.flavia/content_catalog.json`.
- `PDF Files` menu in `/catalog` supports per-file quality display, local text extraction, and explicit Mistral OCR execution.
- `Office Documents` menu in `/catalog` supports per-file conversion to markdown and summary/quality refresh.
- `Image Files` menu in `/catalog` supports per-file vision description generation, viewing generated descriptions, and switching the runtime vision model.
- `Audio/Video Files` menu in `/catalog` supports per-file transcription, re-transcription, transcript viewing, visual frame extraction/description, and summary/quality refresh.
- Audio/video files are transcribed using Mistral Transcription API with segment-level timestamps when the `transcription` extra is installed.
- For video files, you can optionally extract visual frames at sampled timestamps and generate descriptions using vision-capable LLMs (uses `IMAGE_VISION_MODEL` and can consume tokens).
- Office conversion requires installing the `office` extra; legacy/OpenDocument formats also require LibreOffice CLI.
- Mistral OCR requires installing the `ocr` extra and exporting `MISTRAL_API_KEY`.
- Audio/video transcription requires installing the `transcription` extra and exporting `MISTRAL_API_KEY` (shared with OCR).
- Online source processing requires installing the `online` extra. Use `.venv/bin/pip install -e ".[online]"`.
- Visual frame extraction from videos also requires a vision-capable model configured via `IMAGE_VISION_MODEL` or `providers.yaml` (uses existing vision API infrastructure).
- Extracted frames are downscaled/compressed and visually similar consecutive frames are deduplicated (keeping the latest frame) to reduce token usage and processing time.
- Frame descriptions are generated as individual markdown files in `.converted/video_name_frames/` subdirectories and can be viewed from `/catalog`.
- Video transcription also requires `ffmpeg` to be installed on your system for audio extraction.
- In `PDF Files`, you can run `Re-run summary/quality (no extraction)` to regenerate metadata from the existing converted markdown only.
- If summary/quality generation fails, the CLI can prompt you to switch the active model and retry.
- You can set `SUMMARY_MODEL` in `.flavia/.env` to use a dedicated model for catalog summary/quality (separate from the main chat model).
- You can set `IMAGE_VISION_MODEL` in `.flavia/.env` to define a dedicated model for image analysis.

## Startup connection check

When starting flavIA (CLI or Telegram), connectivity to the active provider/model is verified automatically the first time. The result is cached in `.connection_checks.yaml` so the check is not repeated on every run.

## Usage examples

```bash
# Initialize in a papers folder
cd ~/papers/machine-learning
flavia --init

# Chat normally
flavia
> Explain the attention mechanism from the Transformer paper

# Use a specific sub-agent as the main agent
flavia --agent summarizer
> Summarize the three GPT papers

# Verbose mode for debugging
flavia -v

# Enable RAG diagnostics at startup
flavia --rag-debug

# Show all configuration details
flavia --config
```
