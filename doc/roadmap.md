# Roadmap

Planned features and improvements for flavIA, organized by area. Each task includes a difficulty rating and dependencies, so they can be implemented incrementally in any convenient order.

**Difficulty scale**: Easy (a few hours) | Medium (1-2 days) | Hard (3+ days)

## Area 1: Multimodal File Processing

The content system (`content/converters/`) has a clean `BaseConverter` / `ConverterRegistry` architecture. It currently supports PDF (via pdfplumber) and text passthrough. The `FileScanner` already classifies files into types (image, audio, video, binary\_document) but does nothing with non-text/non-PDF files. Online converters (YouTube, webpage) are placeholders.

All new converters follow the same pattern: implement `BaseConverter`, register in `ConverterRegistry`, output Markdown to `.converted/`. The general approach for multimodal processing is to use external APIs (OpenAI Whisper for audio, GPT-4o vision for images/OCR).

### Task 1.1 -- Audio/Video Transcription Converter

**Difficulty**: Medium | **Dependencies**: None

Create `content/converters/audio_converter.py` and `content/converters/video_converter.py` implementing `BaseConverter`. Use the OpenAI Whisper API (`/v1/audio/transcriptions`) for transcription. For video files, extract the audio track first (via `ffmpeg` subprocess or `pydub`) then transcribe. Register for extensions already defined in `scanner.py` (`AUDIO_EXTENSIONS`, `VIDEO_EXTENSIONS`).

**Key files to modify/create**:
- `content/converters/audio_converter.py` (new)
- `content/converters/video_converter.py` (new)
- `content/converters/__init__.py` (register new converters)

**Output format**: Markdown files in `.converted/` with transcription text, timestamps (if available from the API), and a metadata header (duration, source format, etc.).

**New dependencies**: `pydub` or direct `ffmpeg` subprocess (for video audio extraction). The OpenAI SDK already present handles the Whisper API.

### Task 1.2 -- Image Description Converter

**Difficulty**: Medium | **Dependencies**: None

Create `content/converters/image_converter.py`. Use the GPT-4o vision API (or any compatible multimodal endpoint) by sending the image as a base64-encoded content part. The system prompt should request a detailed descriptive textual representation of the image. Register for `IMAGE_EXTENSIONS` from `scanner.py`.

**Key files to modify/create**:
- `content/converters/image_converter.py` (new)
- `content/converters/__init__.py` (register)

**Design consideration**: The provider system currently uses the OpenAI-compatible API; vision endpoints require the multimodal message format (`content: [{type: "image_url", ...}]`). This may require a utility function in `BaseAgent` or a standalone helper for vision calls that can be shared with Task 1.4.

### Task 1.3 -- Word/Office Document Converter

**Difficulty**: Easy | **Dependencies**: None

Create `content/converters/docx_converter.py`. Use `python-docx` for `.docx`, `openpyxl` for `.xlsx`, `python-pptx` for `.pptx`. These are pure-Python libraries requiring no external services. For legacy formats (`.doc`, `.xls`, `.ppt`), consider a `libreoffice --headless` subprocess fallback. Register for extensions defined in `BINARY_DOCUMENT_EXTENSIONS` in `scanner.py`.

**Key files to modify/create**:
- `content/converters/docx_converter.py` (new)
- `content/converters/__init__.py` (register)

**New dependencies** (optional extras, like `python-telegram-bot`): `python-docx`, `openpyxl`, `python-pptx`.

### Task 1.4 -- OCR for Handwritten Documents and Equation-Heavy PDFs

**Difficulty**: Hard | **Dependencies**: Task 1.2 (shares vision API infrastructure)

Create `content/converters/ocr_converter.py`. Use the GPT-4o vision API with a specialized prompt for OCR of handwritten documents. The prompt should instruct the model to transcribe handwritten text faithfully, preserving structure.

**Sub-feature -- LaTeX equation OCR**: The OCR prompt should include instructions to render mathematical equations in LaTeX notation within `$...$` (inline) or `$$...$$` (display) delimiters. The output should be valid Markdown with embedded LaTeX. This is primarily a prompt engineering challenge.

**Sub-feature -- Scanned PDF OCR**: Extend `PdfConverter` to detect image-based PDF pages (pages where pdfplumber extracts no text or very little text) and route those pages to the vision API for per-page OCR. Combine extracted text pages with OCR pages in the final output.

**Key files to modify/create**:
- `content/converters/ocr_converter.py` (new)
- `content/converters/pdf_converter.py` (extend for scanned page detection)
- Shared vision API helper (from Task 1.2)

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

## Area 2: Agent System Improvements

Agents are currently defined in `agents.yaml` with a free-form `context` field (the system prompt), a tools list, subagents dict, and permissions. The `build_system_prompt()` function in `context.py` composes the full prompt. The setup wizard has an AI-assisted mode that generates agents via a setup agent.

### Task 2.1 -- Structured Agent Profiles

**Difficulty**: Medium | **Dependencies**: None

Redesign `agents.yaml` to support structured context fields instead of a single free-form `context` string. New schema:

```yaml
main:
  name: "Research Assistant"
  role: "academic research assistant specializing in ML and NLP"
  expertise:
    - "machine learning"
    - "transformer architectures"
    - "attention mechanisms"
  personality: "precise, thorough, academically rigorous"
  instructions: |
    When analyzing papers, always cite specific sections.
    Compare methodologies across papers when relevant.
  context: |
    Legacy free-form context (still supported for backward compat)
  tools: [...]
  subagents: {...}
```

The `build_system_prompt()` function in `context.py` would compose a richer, more effective prompt from these structured fields when available, falling back to raw `context` for full backward compatibility. The `AgentProfile` dataclass in `profile.py` would gain optional fields (`role`, `expertise`, `personality`, `instructions`) that map to the new YAML keys.

**Key files to modify**:
- `agent/profile.py` -- add new fields to `AgentProfile`
- `agent/context.py` -- update `build_system_prompt()` to use structured fields
- `config/settings.py` -- no change needed (already loads raw YAML dict)

### Task 2.2 -- CLI Agent Management Commands

**Difficulty**: Medium | **Dependencies**: Task 2.1 (benefits from structured profiles), Task 4.2 (agent switching)

Add new slash commands for agent CRUD operations (agent switching itself is covered by Task 4.2):

| Command | Description |
|---------|-------------|
| `/agent-edit <name>` | Interactively edit agent context, tools, and permissions |
| `/agent-create` | Create a new agent interactively via prompts |
| `/agent-list` | Show all agents with full details (expanded `/agents`) |
| `/agent-delete <name>` | Remove an agent from configuration |

All changes persist to `.flavia/agents.yaml`. After modification, the settings and agent profile are reloaded.

**Key files to modify**:
- `interfaces/cli_interface.py` -- add slash command handlers
- `config/settings.py` -- use `reset_settings()` + `load_settings()` after YAML changes

### Task 2.3 -- Meta-Agent for Agent Generation

**Difficulty**: Hard | **Dependencies**: Task 2.1, Task 2.2

Create a specialized "agent architect" agent that can be invoked from the CLI at any time (not just during `--init`) to analyze the project content and generate or improve agent configurations. This extends the existing setup wizard's AI-assisted mode (see `SETUP_AGENT_CONTEXT` in `setup_wizard.py`).

The meta-agent would:
- Analyze the content catalog and current agent configurations
- Suggest improvements to agent contexts, tool assignments, and subagent structures
- Generate structured profiles (per Task 2.1 schema)
- Support iterative refinement with user feedback (similar to the setup wizard's revision rounds)

Invokable via `/agent-improve` or `/agent-generate` slash commands.

**Key files to modify/create**:
- New tool in `tools/setup/` or a dedicated meta-agent profile
- `interfaces/cli_interface.py` -- add slash commands
- Reference pattern: `setup_wizard.py` `SETUP_AGENT_CONTEXT` and `create_agents_config` tool

---

## Area 3: Messaging Platform Framework

The current Telegram integration is tightly coupled: a single bot token stored in `.env`, a single whitelist, one agent config shared by all users, and all configuration via environment variables. The `TelegramBot` class in `telegram_interface.py` is ~280 lines and self-contained.

### Task 3.1 -- YAML-Based Bot Configuration

**Difficulty**: Medium | **Dependencies**: None (foundational for all messaging tasks)

Replace environment variable-based Telegram config with a structured YAML file (`.flavia/bots.yaml`). Example schema:

```yaml
bots:
  research-bot:
    platform: telegram
    token: "${TELEGRAM_BOT_TOKEN_RESEARCH}"
    default_agent: main
    access:
      allowed_users: [123456789]
      allow_all: false

  study-bot:
    platform: telegram
    token: "${TELEGRAM_BOT_TOKEN_STUDY}"
    default_agent: summarizer
    access:
      allowed_users: [123456789, 987654321]
      allow_all: false

  whatsapp-assistant:
    platform: whatsapp
    credentials:
      phone_number_id: "${WA_PHONE_ID}"
      access_token: "${WA_ACCESS_TOKEN}"
    default_agent: main
    access:
      allowed_users: ["+5511999999999"]

  web-api:
    platform: web
    port: 8080
    default_agent: main
    access:
      api_key: "${WEB_API_KEY}"
```

Maintain backward compatibility: if `bots.yaml` does not exist, fall back to current env var behavior (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USER_IDS`, `TELEGRAM_ALLOW_ALL_USERS`).

Environment variable expansion (`${VAR}`) should use the same mechanism as `providers.yaml`.

**Key files to modify/create**:
- `config/settings.py` -- load bot configs alongside other settings
- `config/loader.py` -- discover `bots.yaml` in config paths
- `.flavia/bots.yaml` -- new config file (generated by setup wizard)
- `setup/telegram_wizard.py` -- update to generate `bots.yaml` entries

### Task 3.2 -- Per-Conversation Agent Binding

**Difficulty**: Medium | **Dependencies**: Task 3.1

Allow each bot instance (and each conversation/user within a bot) to be bound to a specific agent from `agents.yaml`. Each bot in `bots.yaml` specifies a `default_agent`. Users can switch agents within their conversation.

New Telegram commands:
- `/agent <name>` -- switch to a different agent (resets conversation history)
- `/agents` -- list available agents from `agents.yaml`

Implementation: The `_get_or_create_agent()` method looks up the bot's configured `default_agent` instead of always using `"main"`. A per-user agent override dict tracks manual switches.

**Key files to modify**:
- `interfaces/telegram_interface.py` -- agent lookup from bot config, new commands

### Task 3.3 -- Multi-Bot Support

**Difficulty**: Medium | **Dependencies**: Task 3.1, Task 3.2

Allow multiple bot instances to run simultaneously from the same `.flavia/` directory. Each entry in `bots.yaml` maps to a separate bot instance.

The `--telegram` flag would start all configured Telegram bots by default, or `--telegram <bot-name>` for a specific one. Use `asyncio.gather()` or equivalent to run multiple bots concurrently in the same process.

**Key files to modify**:
- `cli.py` -- update `--telegram` dispatch to support bot selection
- `interfaces/telegram_interface.py` -- support multiple concurrent instances
- Consider a new `interfaces/bot_runner.py` utility for managing multiple bots

### Task 3.4 -- Abstract Messaging Interface

**Difficulty**: Hard | **Dependencies**: Task 3.1, Task 3.2

Extract a `BaseMessagingBot` abstract class from `TelegramBot` that defines the common interface for all messaging platforms. This becomes the foundation for WhatsApp, Web API, and any future platform.

```
interfaces/
├── base_bot.py          # BaseMessagingBot ABC
├── cli_interface.py     # (unchanged)
├── telegram_bot.py      # TelegramBot(BaseMessagingBot)
├── whatsapp_bot.py      # WhatsAppBot(BaseMessagingBot)
└── web_api.py           # WebAPIBot(BaseMessagingBot)
```

The ABC should handle:
- Authentication and authorization (configurable per platform)
- Agent lifecycle management (get/create/reset per user)
- Message chunking for platform-specific size limits
- Command routing (platform-agnostic command registry)
- Structured logging

Platform-specific subclasses handle only API communication (receiving messages, sending responses, platform-specific formatting).

**Key files to modify/create**:
- `interfaces/base_bot.py` (new ABC)
- `interfaces/telegram_interface.py` -- refactor to extend `BaseMessagingBot`

### Task 3.5 -- WhatsApp Integration

**Difficulty**: Hard | **Dependencies**: Task 3.4

Implement `WhatsAppBot(BaseMessagingBot)`. Two approaches to evaluate at implementation time:

**Option A -- Official WhatsApp Business API (Meta Cloud API)**:
- Uses webhooks: requires running a web server (e.g., `aiohttp`, `FastAPI`) to receive incoming messages
- Reliable and officially supported
- Requires Meta business verification and a phone number
- Message templates needed for initiating conversations
- Supports text, images, documents, audio

**Option B -- Third-party libraries**:
- Libraries like `whatsapp-web.js` (Node.js, would require a bridge) or pure-Python alternatives
- Easier to set up, no business verification
- Less stable, against WhatsApp ToS, may break with updates

The abstract interface from Task 3.4 ensures the choice does not affect the rest of the system. Both approaches should be evaluated; the decision is deferred to implementation time.

**Key files to create**:
- `interfaces/whatsapp_bot.py` (new)
- Webhook server infrastructure (if using official API)

**New dependencies**: `aiohttp` or `fastapi` + `uvicorn` (for webhook server), or platform-specific client library.

### Task 3.6 -- Web API Interface

**Difficulty**: Medium | **Dependencies**: Task 3.4

Create a simple HTTP/WebSocket API server (`WebAPIBot`) that exposes the agent as a programmable endpoint. Use `aiohttp` or `FastAPI`.

Proposed endpoints:
- `POST /chat` -- send a message, receive the agent response
- `POST /reset` -- reset conversation for a session
- `GET /agents` -- list available agents
- `POST /agent` -- switch active agent for a session
- `WebSocket /ws` -- streaming conversation (optional, for real-time UX)

Authentication via API key (configured in `bots.yaml`). Session management via tokens or session IDs.

This enables custom web frontends, mobile apps, or integration with other services and automation pipelines.

**Key files to create**:
- `interfaces/web_api.py` (new)

**New dependencies**: `aiohttp` or `fastapi` + `uvicorn` (optional extras).

---

## Area 4: CLI Improvements

The interactive CLI (`cli_interface.py`) and the CLI flags (`cli.py`) have grown organically and now contain several redundancies, inconsistencies, and gaps. This area covers consolidating existing commands, adding runtime switching capabilities, and introducing features that make the CLI a fully self-contained interface for managing flavIA without needing to restart.

**Current problems identified**:

- `/models` and `/providers` show nearly identical information (models grouped by provider) with different formatting. Neither allows any action.
- `--list-models`, `--list-providers`, `--list-tools` duplicate the slash commands at the flag level with slightly different output detail.
- `/tools` shows only tool names; `--list-tools` shows names, descriptions, and categories. Inconsistent depth.
- `/config` (slash) shows only file paths; `--config` (flag) shows paths plus active settings. Same name, different content.
- `--setup-provider`, `--manage-provider`, and `--test-provider` are only available as CLI flags -- users must exit the interactive session to use them.
- No runtime model or agent switching mid-session.
- No concept of a default "standard" agent or global (user-level) agent definitions.
- The `/agents` command only manages model assignments; it cannot edit contexts, tools, or create/delete agents.

### Task 4.1 -- Consolidate Info Commands

**Difficulty**: Easy | **Dependencies**: None

Merge and rationalize the overlapping information commands:

1. **Merge `/models` and `/providers` into `/providers`**: The `/providers` command already shows models per provider. Remove the standalone `/models` command (or make it an alias). The consolidated `/providers` command shows: provider name, ID, default marker, API key status, URL, and the model list with defaults.

2. **Improve `/tools` detail level**: Make `/tools` match the detail of `--list-tools` -- show descriptions and group by category. Add `/tools <name>` to show the full schema of a specific tool.

3. **Improve `/config` completeness**: Make `/config` show the same information as `--config` (active settings, model, agent, subagents status) in addition to file paths. This becomes the single "show me my current state" command.

4. **Deprecate redundant CLI flags**: Once the slash commands are feature-complete, `--list-models`, `--list-providers`, and `--list-tools` become thin wrappers that print the same output and exit. The implementations should share code to avoid divergence.

**Key files to modify**:
- `interfaces/cli_interface.py` -- update `/providers`, `/tools`, `/config` handlers; remove or alias `/models`
- `cli.py` -- refactor `list_models()`, `list_tools_info()`, `list_providers()` to share logic with slash commands

### Task 4.2 -- Runtime Agent Switching in CLI

**Difficulty**: Easy | **Dependencies**: None

Currently, the `--agent` CLI flag promotes a subagent as main at startup, but there is no way to switch agents mid-session. The existing `/agents` command only manages model assignments.

Add a `/agent <name>` slash command to `cli_interface.py` that:

1. Validates the agent name exists in `agents_config` (including subagents)
2. Creates a new `RecursiveAgent` with the selected profile
3. Resets conversation history
4. Updates the prompt display to show the active agent name

Also add `/agent` (no arguments) to show the current active agent and its configuration summary (name, model, tools, context snippet).

**Key files to modify**:
- `interfaces/cli_interface.py` -- add `/agent` command handler
- Optionally update prompt prefix to display active agent name

### Task 4.3 -- Runtime Model Switching in CLI

**Difficulty**: Easy | **Dependencies**: None

Add a `/model` slash command that allows changing the active model mid-session without restarting:

| Invocation | Behavior |
|------------|----------|
| `/model` | Show current active model (provider:model_id) |
| `/model <ref>` | Switch to a different model. Accepts index number, model ID, or `provider:model_id` format. Recreates the agent with the new model, resets conversation. |
| `/model list` | Alias for `/providers` (quick access) |

This replaces the current workflow of exiting, running `flavia -m <model>`, and losing context. The model change updates `settings.default_model` for the session (not persisted to disk unless explicitly saved).

**Key files to modify**:
- `interfaces/cli_interface.py` -- add `/model` command handler
- `interfaces/cli_interface.py` -- update `create_agent_from_settings()` to accept model override

### Task 4.4 -- In-Session Provider & Model Management

**Difficulty**: Medium | **Dependencies**: Task 4.1

Expose the provider management wizards (currently only accessible via CLI flags) as interactive slash commands within the CLI session:

| Command | Equivalent flag | Description |
|---------|----------------|-------------|
| `/provider-setup` | `--setup-provider` | Run the interactive provider configuration wizard |
| `/provider-manage [id]` | `--manage-provider` | Manage models for a provider (add, remove, fetch from API) |
| `/provider-test [id]` | `--test-provider` | Test connection to a provider |

After provider changes, prompt the user to `/reset` to reload the updated configuration (same pattern as `/setup` and `/agents` already use).

This eliminates the need to exit the interactive session for provider management, making the CLI fully self-sufficient.

**Key files to modify**:
- `interfaces/cli_interface.py` -- add slash command handlers that call existing wizard functions
- `setup/provider_wizard.py` -- no changes needed (functions are already importable)

### Task 4.5 -- Standard Default Agent

**Difficulty**: Medium | **Dependencies**: None

Define a built-in "standard" agent that is always available, regardless of whether the project has an `agents.yaml` file. This agent:

- Uses the project's default model (from `providers.yaml` or environment)
- Has a general-purpose system prompt suitable for academic research and writing assistance
- Is registered as `"standard"` in the agent list and can be switched to via `/agent standard`
- Serves as the fallback when no `agents.yaml` exists (replacing the current minimal hardcoded fallback in `create_agent_from_settings()`)
- Cannot be deleted or overridden by project config (always present alongside project-defined agents)

The standard agent should have a reasonable default tool set (file reading, search, directory listing) and a well-crafted academic-assistant system prompt.

**Key files to modify**:
- `interfaces/cli_interface.py` -- update `create_agent_from_settings()` to always register the standard agent
- `agent/profile.py` -- add a `standard_profile()` class method or standalone function
- Consider a `defaults/standard_agent.yaml` file for the default configuration

### Task 4.6 -- Global Agent Definitions

**Difficulty**: Medium | **Dependencies**: Task 2.1 (structured profiles), Task 4.2 (agent switching)

Support user-level agent definitions in `~/.config/flavia/agents.yaml` that are available across all projects. These complement project-local agents in `.flavia/agents.yaml`.

Resolution order (later overrides earlier for same-name agents):
1. Built-in standard agent (Task 4.5)
2. User-level agents (`~/.config/flavia/agents.yaml`)
3. Project-level agents (`.flavia/agents.yaml`)

Example global agents:

```yaml
# ~/.config/flavia/agents.yaml
beamer-specialist:
  name: "Beamer Presentation Expert"
  role: "LaTeX Beamer academic presentation specialist"
  context: |
    You specialize in creating and improving LaTeX Beamer presentations
    for academic conferences. You follow best practices for slide design:
    minimal text, clear figures, consistent themes, proper use of
    columns, blocks, and overlays.
  tools: [read_file, list_files, search_files]

paper-reviewer:
  name: "Academic Paper Reviewer"
  role: "critical reviewer of academic papers"
  context: |
    You review academic papers with the rigor of a top-tier venue
    reviewer. You evaluate: novelty, methodology, experimental design,
    writing clarity, and proper citation of related work.
  tools: [read_file, search_files]

code-analyst:
  name: "Code Analysis Expert"
  context: |
    You specialize in code review, refactoring suggestions, and
    identifying potential bugs, performance issues, and security
    concerns in source code.
  tools: [read_file, list_files, search_files, get_file_info]
```

The `/agent` command (Task 4.2) lists agents from all three sources with source labels (`[built-in]`, `[global]`, `[project]`).

**Key files to modify**:
- `config/settings.py` -- load and merge global + local agents configs
- `config/loader.py` -- discover user-level `agents.yaml`
- `interfaces/cli_interface.py` -- update agent listing to show sources

### Task 4.7 -- Unified Slash Command Help System

**Difficulty**: Easy | **Dependencies**: None

Improve the `/help` command from a static text block to a structured, categorized system:

1. **`/help`** (no args): Show all commands organized by category with one-line descriptions:
   - **Session**: `/reset`, `/quit`
   - **Agents**: `/agent`, `/agents`
   - **Models & Providers**: `/model`, `/providers`, `/provider-setup`, `/provider-manage`, `/provider-test`
   - **Information**: `/tools`, `/config`, `/catalog`
   - **Setup**: `/setup`

2. **`/help <command>`**: Show detailed help for a specific command -- description, arguments, examples, and related commands.

3. Register commands in a lightweight command registry (a dict mapping command names to handler functions and metadata) instead of the current `if/elif` chain in `run_cli()`. This makes it easy to add new commands and auto-generate help text.

**Key files to modify**:
- `interfaces/cli_interface.py` -- implement command registry, update `/help` handler, refactor `run_cli()` dispatch

---

## Area 5: File Modification Tools

Currently flavIA is read-only: agents can read files, list directories, and search content, but cannot modify any project files. The permission system (`AgentPermissions.can_write()`, `check_write_permission()` in `tools/permissions.py`) already exists and is fully implemented, but no tools use the write path. Adding write tools unlocks the agent's ability to assist with document editing, code modification, report drafting, and other productive workflows.

### Task 5.1 -- Write/Edit File Tools

**Difficulty**: Medium | **Dependencies**: None

Create a new `tools/write/` category with tools that let the agent modify project files:

| Tool | Description |
|------|-------------|
| `write_file` | Create a new file or overwrite an existing file entirely |
| `edit_file` | Replace a specific section of a file by matching an exact text fragment and substituting it (similar to how coding assistants do targeted edits) |
| `insert_text` | Insert text at a specific line number in a file |
| `append_file` | Append content to the end of a file |

All write tools enforce the existing `AgentPermissions.write_paths` system via `check_write_permission()` from `tools/permissions.py`. The infrastructure is already in place -- `AgentPermissions.can_write()` and `check_write_permission()` exist but no tools actually call them yet.

Safety considerations:
- All operations are logged with before/after state for auditability
- The `edit_file` tool should require an exact match of the text to be replaced (not regex), to prevent unintended modifications
- Consider creating a `.flavia/file_backups/` directory for automatic backups before edits

**Key files to modify/create**:
- `tools/write/write_file.py` (new)
- `tools/write/edit_file.py` (new)
- `tools/write/__init__.py` (new, with `register_tool()` calls)
- `tools/__init__.py` (add `write` submodule import for auto-registration)

**New dependencies**: None (uses only stdlib and existing permission infrastructure).

---

## Area 6: Academic Workflow Tools

flavIA is designed for research and academic work. Beyond reading and analyzing files, researchers need to compile LaTeX documents (papers, reports, presentations) and run computational scripts (data analysis, simulations, plotting). These tools bridge the gap between the agent's text generation capabilities and actual academic output.

### Task 6.1 -- LaTeX Compilation Tool

**Difficulty**: Medium | **Dependencies**: Task 5.1 (agent needs write tools to generate `.tex` files first)

Create a `tools/academic/compile_latex.py` tool that compiles LaTeX documents into PDFs.

Functionality:
- Run `pdflatex` (or `latexmk` if available) on a `.tex` file as a subprocess
- Handle multiple compilation passes automatically (for cross-references, table of contents)
- Optionally run `bibtex` or `biber` between passes (for bibliography)
- Return compilation status, output PDF path, and any errors/warnings from the log
- Parse `.log` file to extract meaningful error messages rather than dumping raw output
- Enforce write permissions (output directory must be in write-allowed paths)

Requires `pdflatex`/`latexmk` installed on the system (not a Python dependency). The tool should detect availability at registration time and report clearly if missing.

Configuration in `agents.yaml`:
```yaml
main:
  tools:
    - compile_latex
  latex:
    compiler: "pdflatex"     # or "latexmk", "xelatex", "lualatex"
    passes: 2                # number of compilation passes
    bibtex: true             # run bibtex/biber automatically
    clean_aux: true          # remove auxiliary files after compilation
```

**Key files to modify/create**:
- `tools/academic/compile_latex.py` (new)
- `tools/academic/__init__.py` (new, with `register_tool()` calls)
- `tools/__init__.py` (add `academic` submodule import)

### Task 6.2 -- Sandboxed Script Execution (Python/MATLAB)

**Difficulty**: Hard | **Dependencies**: Task 5.1

Create a `tools/academic/run_script.py` tool for executing Python and MATLAB/Octave scripts with a combination safety approach: user confirmation before execution, plus subprocess-level restrictions during execution.

**Safety model -- two layers**:

1. **User confirmation gate**: Before any script runs, the tool presents the full script content to the user and requires explicit approval. The confirmation mechanism is platform-aware:
   - CLI: interactive prompt showing the script and asking `Execute this script? [y/N]`
   - Telegram/WhatsApp: send the script as a message, wait for user reply "yes"/"no"
   - Web API: return script in response, require a separate confirmation API call

2. **Subprocess restrictions** (even after user approval):
   - Timeout limits (configurable, default 60 seconds)
   - Working directory restricted to write-allowed paths
   - For Python: restricted imports (block `os`, `subprocess`, `sys`, `shutil`, `socket`, `http`, `ctypes`, etc.) enforced by pre-scanning the script's AST with Python's `ast` module before execution
   - For MATLAB/Octave: run via `matlab -batch` or `octave --eval` with the same timeout
   - stdout/stderr captured and returned to the agent as the tool result
   - Resource limits where the platform supports them (`ulimit` on Linux/macOS)

Tools to implement:
- `run_python` -- execute a Python script (`.py` file path or inline code string)
- `run_matlab` -- execute a MATLAB/Octave script (`.m` file path or inline code string)

Configuration in `agents.yaml`:
```yaml
main:
  tools:
    - run_python
    - run_matlab
  script_execution:
    timeout: 60
    require_confirmation: true
    blocked_imports:
      - os
      - subprocess
      - sys
      - shutil
      - socket
      - http
      - ctypes
      - importlib
```

**Key files to modify/create**:
- `tools/academic/run_script.py` (new)
- `tools/academic/__init__.py` (update)
- Agent confirmation callback mechanism (new -- needs to work across CLI, Telegram, Web API)

---

## Area 7: External Service Integration

Extend flavIA's capabilities beyond the local filesystem by integrating with external services commonly used in academic and professional workflows. A new `.flavia/services.yaml` configuration file manages credentials and settings for all external services, using the same `${ENV_VAR}` expansion mechanism as `providers.yaml`.

```yaml
# .flavia/services.yaml
services:
  email:
    imap_server: "imap.gmail.com"
    imap_port: 993
    smtp_server: "smtp.gmail.com"
    smtp_port: 587
    username: "${EMAIL_USERNAME}"
    password: "${EMAIL_APP_PASSWORD}"

  google_calendar:
    credentials_file: "google_credentials.json"
    calendar_id: "primary"
```

The general principle for all external service tools: **read operations are autonomous** (the agent can search, list, and read without user intervention), while **write operations require user confirmation** (sending emails, creating events, etc.).

### Task 7.1 -- Email Integration (IMAP/SMTP)

**Difficulty**: Hard | **Dependencies**: None

Create `tools/services/email.py` with tools for email access via standard IMAP/SMTP protocols.

**Read tools (autonomous, no confirmation required)**:

| Tool | Description |
|------|-------------|
| `search_email` | Search inbox by sender, subject, date range, keywords |
| `read_email` | Read a specific email by ID, including text content and attachment list |
| `list_email_folders` | List available email folders/labels |

**Write tools (require user confirmation before acting)**:

| Tool | Description |
|------|-------------|
| `send_email` | Compose and send an email -- shows full draft to user, waits for approval |
| `reply_email` | Reply to a specific email -- shows draft, waits for approval |

Implementation uses Python's built-in `imaplib` for reading and `smtplib` for sending. No external dependencies required.

For Gmail specifically: requires an App Password (not the regular account password) with 2FA enabled. The setup wizard should guide users through generating an App Password. OAuth2 support could be added later for a smoother experience but is not required for the initial implementation.

The confirmation mechanism for `send_email`/`reply_email` is platform-aware (same infrastructure as Task 6.2):
- CLI: interactive prompt showing the draft and asking `Send this email? [y/N]`
- Telegram/WhatsApp: send the draft as a message, wait for user reply
- Web API: return draft in response, require separate confirmation call

**Key files to modify/create**:
- `tools/services/email.py` (new)
- `tools/services/__init__.py` (new)
- `config/settings.py` (load services config from `services.yaml`)
- `config/loader.py` (discover `services.yaml` in config paths)
- `setup/services_wizard.py` (new -- guided email setup)

**New dependencies**: None (uses Python stdlib `imaplib`, `smtplib`, `email`).

### Task 7.2 -- Google Calendar Integration

**Difficulty**: Hard | **Dependencies**: None

Create `tools/services/calendar.py` with Google Calendar tools.

**Read tools (autonomous)**:

| Tool | Description |
|------|-------------|
| `list_events` | List calendar events in a date range |
| `search_events` | Search events by keyword or attendee |
| `get_event` | Get full details of a specific event |

**Write tools (require user confirmation)**:

| Tool | Description |
|------|-------------|
| `create_event` | Create a calendar event -- shows details, waits for approval |
| `update_event` | Modify an existing event -- shows changes, waits for approval |
| `delete_event` | Delete an event -- requires confirmation |

Use `google-api-python-client` + `google-auth-oauthlib` for OAuth2 authentication. First-time setup requires a browser-based OAuth flow; credentials are cached in `.flavia/google_credentials.json` (excluded from git via `.flavia/.gitignore`).

A setup wizard (`--setup-calendar` or part of a broader `--setup-services`) would guide the user through:
1. Creating a Google Cloud project and enabling the Calendar API
2. Downloading OAuth client credentials (`client_secret.json`)
3. Running the OAuth consent flow to authorize access
4. Storing the refresh token securely in `.flavia/`

Configuration in `.flavia/services.yaml`:
```yaml
services:
  google_calendar:
    credentials_file: "google_credentials.json"
    calendar_id: "primary"           # or a specific calendar ID
    default_timezone: "America/Sao_Paulo"
```

**Key files to modify/create**:
- `tools/services/calendar.py` (new)
- `tools/services/__init__.py` (update)
- `setup/calendar_wizard.py` (new -- OAuth flow guide)
- `config/settings.py` (load services config)

**New dependencies** (optional extras): `google-api-python-client`, `google-auth-oauthlib`, `google-auth-httplib2`.

---

## Dependency Graph

```
Area 1 -- Multimodal File Processing:
Task 1.1 (Audio/Video) ──────────────────────┐
Task 1.2 (Image Description) ─────┐          │
Task 1.3 (Word/Office) ───────────┤          │
                                   ├── Task 1.4 (OCR + LaTeX)
                                   │          │
                                   │          └── Task 1.5 (YouTube/Web)

Area 2 -- Agent System:
Task 2.1 (Structured Profiles) ──┬── Task 2.2 (CLI Agent Commands) ── depends also on Task 4.2
                                 └───────────── Task 2.3 (Meta-Agent)

Area 3 -- Messaging Platforms:
Task 3.1 (YAML Bot Config) ──┬── Task 3.2 (Per-Conv Agent Binding)
                              ├── Task 3.3 (Multi-Bot)
                              └── Task 3.4 (Abstract Interface) ──┬── Task 3.5 (WhatsApp)
                                                                  └── Task 3.6 (Web API)

Area 4 -- CLI Improvements:
Task 4.1 (Consolidate Info Cmds) ────── Task 4.4 (In-Session Provider Mgmt)
Task 4.2 (Runtime Agent Switching) ─┐
Task 4.3 (Runtime Model Switching)  ├── Task 4.6 (Global Agents)
Task 4.5 (Standard Default Agent)   │     also depends on Task 2.1
Task 4.7 (Unified Help System)      │
                                     │
Task 2.1 (Structured Profiles) ─────┘

Area 5 -- File Modification:
Task 5.1 (Write/Edit Tools) ──┬── Task 6.1 (LaTeX Compilation)
                               └── Task 6.2 (Script Execution)

Area 6 -- Academic Workflow:
Task 6.1 (LaTeX Compilation) ── depends on Task 5.1
Task 6.2 (Script Execution) ── depends on Task 5.1

Area 7 -- External Services:
Task 7.1 (Email IMAP/SMTP) ── (independent, no dependencies)
Task 7.2 (Google Calendar) ── (independent, no dependencies)
```

## Suggested Implementation Order

Tasks ordered by difficulty (easy first) and dependency readiness. Each task can be implemented independently as long as its dependencies are met.

| Order | Task | Difficulty | Area |
|-------|------|------------|------|
| 1 | **4.1** Consolidate info commands | Easy | CLI |
| 2 | **4.2** Runtime agent switching in CLI | Easy | CLI |
| 3 | **4.3** Runtime model switching in CLI | Easy | CLI |
| 4 | **4.7** Unified slash command help system | Easy | CLI |
| 5 | **1.3** Word/Office document converter | Easy | File Processing |
| 6 | **5.1** Write/Edit file tools | Medium | File Modification |
| 7 | **1.1** Audio/Video transcription converter | Medium | File Processing |
| 8 | **1.2** Image description converter | Medium | File Processing |
| 9 | **4.4** In-session provider & model management | Medium | CLI |
| 10 | **4.5** Standard default agent | Medium | CLI |
| 11 | **2.1** Structured agent profiles | Medium | Agents |
| 12 | **3.1** YAML-based bot configuration | Medium | Messaging |
| 13 | **6.1** LaTeX compilation tool | Medium | Academic Workflow |
| 14 | **4.6** Global agent definitions | Medium | CLI |
| 15 | **2.2** CLI agent management commands | Medium | Agents |
| 16 | **3.2** Per-conversation agent binding | Medium | Messaging |
| 17 | **3.3** Multi-bot support | Medium | Messaging |
| 18 | **1.5** Online source converters (YouTube/Web) | Medium | File Processing |
| 19 | **3.6** Web API interface | Medium | Messaging |
| 20 | **1.4** OCR + LaTeX equation support | Hard | File Processing |
| 21 | **3.4** Abstract messaging interface | Hard | Messaging |
| 22 | **2.3** Meta-agent for agent generation | Hard | Agents |
| 23 | **6.2** Sandboxed script execution (Python/MATLAB) | Hard | Academic Workflow |
| 24 | **7.1** Email integration (IMAP/SMTP) | Hard | External Services |
| 25 | **7.2** Google Calendar integration | Hard | External Services |
| 26 | **3.5** WhatsApp integration | Hard | Messaging |

This order is a suggestion. Tasks can be implemented in any order that respects the dependency graph above.
