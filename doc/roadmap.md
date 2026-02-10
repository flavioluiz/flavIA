# Roadmap

Planned features and improvements for flavIA, organized by area. Each task includes a difficulty rating and dependencies, so they can be implemented incrementally in any convenient order.

**Difficulty scale**: Easy (a few hours) | Medium (1-2 days) | Hard (3+ days)

---

## 📋 Executive Summary

This roadmap outlines **37 tasks** across **9 major areas** to extend flavIA from a read-only research assistant into a comprehensive, production-ready AI agent system with multimodal processing, write capabilities, external service integration, web & academic research tools, and multi-platform deployment.

### Quick Stats
- **8 Easy tasks** (< 1 day each) — Quick wins for immediate value — **2 completed** ✓
- **20 Medium tasks** (1-2 days each) — Core feature development
- **9 Hard tasks** (3+ days each) — Complex integrations requiring careful design

### Strategic Priorities
1. **Immediate value** (Tasks 4.1-4.7, 8.1): Improve CLI UX and add token tracking
2. **Core capabilities** (Tasks 5.1, 1.1-1.3): Enable file writing and expand content processing
3. **Academic workflows** (Tasks 6.1-6.2): LaTeX compilation and script execution
4. **Production readiness** (Tasks 3.1-3.6, 8.2-8.3): Multi-platform bots and context management
5. **Web & academic research** (Tasks 9.1-9.8): Web search, academic databases, DOI resolution, Scopus, article download, BibTeX management
6. **Advanced features** (Tasks 7.1-7.2, 2.3): External services and meta-agents

---

## 📖 Table of Contents

### [Area 1: Multimodal File Processing](#area-1-multimodal-file-processing) (5 tasks)
Expand content processing beyond PDF/text to audio, video, images, Office docs, and online sources.

- **1.1** Audio/Video Transcription (Medium) — Whisper API transcription
- **1.2** Image Description (Medium) — GPT-4o vision for images
- **1.3** Word/Office Documents (Easy) — python-docx, openpyxl, python-pptx
- **1.4** OCR + LaTeX Equations (Hard) — Handwritten docs, scanned PDFs, equation OCR
- **1.5** YouTube/Web Converters (Medium) — yt-dlp, trafilatura

### [Area 2: Agent System Improvements](#area-2-agent-system-improvements) (3 tasks)
Redesign agent configuration for richer, more maintainable agent definitions.

- **2.1** Structured Agent Profiles (Medium) — Replace free-form context with role/expertise/personality fields
- **2.2** CLI Agent Management (Medium) — /agent-create, /agent-edit, /agent-delete commands
- **2.3** Meta-Agent Generation (Hard) — AI-powered agent architect for automatic config generation

### [Area 3: Messaging Platform Framework](#area-3-messaging-platform-framework) (6 tasks)
Transform Telegram integration into a multi-platform bot framework.

- **3.1** YAML Bot Configuration (Medium) — Replace env vars with `.flavia/bots.yaml`
- **3.2** Per-Conversation Agents (Medium) — Each user can switch agents mid-chat
- **3.3** Multi-Bot Support (Medium) — Run multiple bot instances concurrently
- **3.4** Abstract Messaging Interface (Hard) — BaseMessagingBot ABC for platform independence
- **3.5** WhatsApp Integration (Hard) — WhatsApp Business API or third-party bridge
- **3.6** Web API Interface (Medium) — HTTP/WebSocket API for custom frontends

### [Area 4: CLI Improvements](#area-4-cli-improvements) (7 tasks)
Consolidate commands, eliminate redundancies, add runtime switching, and introduce global agents.

- **4.1** ~~Consolidate Info Commands (Easy)~~ — **DONE** ✓ Merged /models into /providers, /tools shows categories + schema, /config shows active settings
- **4.2** ~~Runtime Agent Switching (Easy)~~ — **DONE** ✓ /agent command to list agents or switch mid-session
- **4.3** Runtime Model Switching (Easy) — /model command to change models without restart
- **4.4** In-Session Provider Management (Medium) — /provider-setup, /provider-test from within CLI
- **4.5** Standard Default Agent (Medium) — Built-in fallback agent always available
- **4.6** Global Agent Definitions (Medium) — User-level agents in ~/.config/flavia/agents.yaml
- **4.7** Unified Help System (Easy) — Structured /help with categories and command registry

### [Area 5: File Modification Tools](#area-5-file-modification-tools) (1 task)
Enable write capabilities using the existing permission infrastructure.

- **5.1** Write/Edit File Tools (Medium) — write_file, edit_file, insert_text, append_file with permission checks

### [Area 6: Academic Workflow Tools](#area-6-academic-workflow-tools) (2 tasks)
Bridge the gap between text generation and actual research output.

- **6.1** LaTeX Compilation (Medium) — Compile .tex to PDF with pdflatex/latexmk
- **6.2** Sandboxed Script Execution (Hard) — Run Python/MATLAB scripts with user confirmation + AST-based safety

### [Area 7: External Service Integration](#area-7-external-service-integration) (2 tasks)
Connect to email and calendar services with read-autonomous, write-confirmed pattern.

- **7.1** Email Integration (Hard) — IMAP/SMTP for Gmail with read/search/send tools
- **7.2** Google Calendar (Hard) — OAuth2 integration for event management

### [Area 8: Context Window Management & Compaction](#area-8-context-window-management--compaction) (3 tasks)
Track token usage and automatically summarize conversations approaching context limits.

- **8.1** Token Usage Tracking (Easy) — Capture response.usage, display utilization in CLI/Telegram
- **8.2** Compaction with Confirmation (Medium) — Auto-summarize at threshold with user approval
- **8.3** Manual /compact Command (Easy) — On-demand conversation summarization

### [Area 9: Web & Academic Research Tools](#area-9-web--academic-research-tools) (8 tasks)
Comprehensive web and academic search toolkit for literature reviews, deep research, and precise scientific citation management.

- **9.1** Web Search Engine (Medium) — Multi-provider web search (Google, Brave, DuckDuckGo)
- **9.2** Academic Database Search (Medium) — Google Scholar, OpenAlex, Semantic Scholar
- **9.3** DOI Metadata Resolution (Easy) — CrossRef/DataCite DOI lookup and metadata extraction
- **9.4** Scopus Integration (Medium) — Scopus API for journal metrics, author profiles, and citations
- **9.5** Article Download & Content Integration (Hard) — Download PDFs, integrate with content system
- **9.6** CAPES/Academic Network Publisher Access (Hard) — Access licensed publisher content via institutional networks
- **9.7** BibTeX Reference Management (Medium) — Automatic .bib file generation and maintenance
- **9.8** Research Session Management (Medium) — Track, manage, and organize web research results

---

## 🎯 Implementation Roadmap Overview

### Phase 1: Foundation & Quick Wins (Tasks 4.1-4.7, 8.1, 1.3)
**Timeline**: 1-2 weeks | **Effort**: 7 Easy + 1 Medium = ~5-7 days

Improve CLI usability, add token tracking, and expand file processing to Office docs. All tasks are independent and can be implemented in parallel.

**Deliverables**:
- Unified, consistent CLI commands with better help
- Real-time token usage visibility in CLI and Telegram
- Support for .docx, .xlsx, .pptx files

### Phase 2: Core Write Capabilities (Tasks 5.1, 6.1)
**Timeline**: 1 week | **Effort**: 2 Medium = ~3-4 days

Enable file modification and LaTeX compilation for productive academic workflows.

**Deliverables**:
- Agent can create, edit, and modify files (with permissions)
- Compile LaTeX documents directly from chat

### Phase 3: Multimodal Expansion (Tasks 1.1-1.2, 1.5)
**Timeline**: 2 weeks | **Effort**: 3 Medium = ~4-6 days

Add audio/video transcription, image understanding, and online source processing.

**Deliverables**:
- Transcribe audio/video files via Whisper
- Describe images via GPT-4o vision
- Process YouTube videos and web pages

### Phase 4: Production Messaging (Tasks 3.1-3.3, 8.2-8.3)
**Timeline**: 2 weeks | **Effort**: 3 Medium = ~4-6 days

Professionalize the bot infrastructure with YAML config, multi-bot support, and context management.

**Deliverables**:
- Multiple Telegram bots from one installation
- Per-user agent binding
- Automatic context compaction when approaching limits

### Phase 5: Advanced Features (Tasks 2.1-2.2, 4.6, 6.2)
**Timeline**: 2-3 weeks | **Effort**: 4 Medium + 1 Hard = ~7-10 days

Structured agent profiles, global agents, and sandboxed script execution.

**Deliverables**:
- Richer agent configuration system
- User-level agents available across all projects
- Safe execution of Python/MATLAB scripts

### Phase 6: Platform Expansion (Tasks 3.4, 3.6, 1.4)
**Timeline**: 2-3 weeks | **Effort**: 2 Hard + 1 Medium = ~7-10 days

Abstract bot interface, Web API, and advanced OCR.

**Deliverables**:
- HTTP/WebSocket API for custom integrations
- Platform-independent bot architecture
- OCR for handwritten notes and equations

### Phase 7: External Services (Tasks 7.1-7.2, 2.3, 3.5)
**Timeline**: 3-4 weeks | **Effort**: 4 Hard = ~12-16 days

Email, calendar, WhatsApp, and meta-agent generation.

**Deliverables**:
- Send/receive emails from chat
- Manage Google Calendar events
- WhatsApp bot (if desired)
- AI-powered agent configuration generation

### Phase 8: Web & Academic Research Foundation (Tasks 9.3, 9.1, 9.2, 9.4, 9.7)
**Timeline**: 3-4 weeks | **Effort**: 1 Easy + 4 Medium = ~7-10 days

Build the web and academic search toolkit, starting with DOI resolution (quick win), then web search, academic databases, Scopus integration, and BibTeX management.

**Deliverables**:
- Web search from within flavIA (Google, Brave, DuckDuckGo)
- Search academic databases (Google Scholar, OpenAlex, Semantic Scholar)
- Resolve DOI metadata and generate citations
- Scopus journal/author lookup
- Automatic BibTeX reference file management

### Phase 9: Research Infrastructure (Tasks 9.5, 9.6, 9.8)
**Timeline**: 3-4 weeks | **Effort**: 2 Hard + 1 Medium = ~8-12 days

Build the article download pipeline, CAPES publisher access, and research session management.

**Deliverables**:
- Download available articles and integrate with content catalog
- Access licensed content via CAPES/institutional network
- Research session tracking with temporary/permanent lifecycle

---

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
| `/agent-list` | Show all agents with full details (expanded `/agent`) |
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
- The `/agent_setup` command (Quick mode) only manages model assignments; it cannot edit contexts, tools, or create/delete agents.

### Task 4.1 -- Consolidate Info Commands ✓ COMPLETED

**Difficulty**: Easy | **Dependencies**: None | **Status**: DONE

~~Merge and rationalize the overlapping information commands:~~

**Implementation summary**:

1. **Created `src/flavia/display.py`** — New shared module with 4 display functions:
   - `display_providers()` — Shows providers with globally indexed models
   - `display_tools()` — Shows tools grouped by category with descriptions
   - `display_tool_schema()` — Shows full schema for a specific tool
   - `display_config()` — Shows config paths and active settings

2. **Removed `/models` and `--list-models`** — Redundant with `/providers`

3. **Updated commands to use shared module**:
   - `/providers` and `--list-providers` — Providers with indexed models
   - `/tools` and `--list-tools` — Categorized tools with descriptions
   - `/tools <name>` — Full tool schema (parameters, types, defaults)
   - `/config` and `--config` — Paths + active settings

4. **Plain text output for piping** — CLI flags detect non-TTY and strip ANSI codes

**Files modified**:
- `src/flavia/display.py` (new)
- `src/flavia/cli.py`
- `src/flavia/interfaces/cli_interface.py`
- `src/flavia/setup/provider_wizard.py`

### Task 4.2 -- Runtime Agent Switching in CLI ✓ COMPLETED

**Difficulty**: Easy | **Dependencies**: None | **Status**: Done

Implemented `/agent` slash command for runtime agent switching:

- `/agent` (no args) -- Lists all available agents (main + subagents) with model, tools, and context summary. Marks the active agent with `[active]`.
- `/agent <name>` -- Switches to a different agent, validates the name exists, creates a new agent instance, resets conversation, and updates the prompt to show `[agent_name] You:` for non-main agents.

**Files modified**:
- `src/flavia/display.py` -- Added `display_agents()` function
- `src/flavia/interfaces/cli_interface.py` -- Added `/agent` command handler, `_get_available_agents()` helper, updated `_read_user_input()` for agent prefix, updated `print_help()`
- `doc/usage.md` -- Documented new commands

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

After provider changes, prompt the user to `/reset` to reload the updated configuration (same pattern as `/agent_setup` already uses).

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
   - **Agents**: `/agent`, `/agent_setup`
   - **Models & Providers**: `/model`, `/providers`, `/provider-setup`, `/provider-manage`, `/provider-test`
   - **Information**: `/tools`, `/config`, `/catalog`
   - **Setup**: `/agent_setup`

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

## Area 8: Context Window Management & Compaction

The agent system currently has no awareness of context window limits. Messages accumulate indefinitely in `self.messages` (the conversation history list in `BaseAgent`), and the `response.usage` token counts returned by the OpenAI-compatible API are discarded. The `max_tokens` field already exists in `ModelConfig` (per-provider, e.g. 128000 for Kimi-K2.5, 200000 for Claude) but is never used at runtime.

This area introduces token usage tracking, context window monitoring, and a compaction mechanism that summarizes the conversation history when the context window approaches its limit.

### Task 8.1 -- Token Usage Tracking & Display

**Difficulty**: Easy | **Dependencies**: None

Capture the `response.usage` object returned by the OpenAI-compatible API after each LLM call, and expose the model's `max_tokens` to the agent so it can compute context utilization.

**Changes to `_call_llm()` in `agent/base.py`**:
- Currently returns only `response.choices[0].message`, discarding the rest. Change to also capture `response.usage` (which contains `prompt_tokens`, `completion_tokens`, `total_tokens`).
- Store cumulative token usage in new instance attributes on `BaseAgent`:
  - `self.last_prompt_tokens: int` -- prompt tokens from the most recent call
  - `self.last_completion_tokens: int` -- completion tokens from the most recent call
  - `self.total_prompt_tokens: int` -- cumulative prompt tokens across all calls in the session
  - `self.total_completion_tokens: int` -- cumulative completion tokens
- Expose `self.max_context_tokens: int` -- loaded from the resolved `ModelConfig.max_tokens` at agent initialization.

**Changes to `RecursiveAgent.run()` in `agent/recursive.py`**:
- After each `_call_llm()` call, update the token counters.
- Compute context utilization: `utilization = self.last_prompt_tokens / self.max_context_tokens`.
- Return or expose the utilization alongside the response text (e.g., as a property or as part of a structured return object).

**Display in CLI (`interfaces/cli_interface.py`)**:
- After each agent response, show a compact token usage line, e.g.:
  `[tokens: 12,450 / 128,000 (9.7%) | response: 850 tokens]`
- Use color coding: green (<70%), yellow (70-89%), red (≥90%).

**Display in Telegram (`interfaces/telegram_interface.py`)**:
- Append a token usage footer to each response message, e.g.:
  `📊 Context: 12,450/128,000 (9.7%)`

**Key files to modify**:
- `agent/base.py` -- capture `response.usage`, add token counter attributes, expose `max_context_tokens`
- `agent/recursive.py` -- update counters after each LLM call, expose utilization
- `interfaces/cli_interface.py` -- display token usage after each response
- `interfaces/telegram_interface.py` -- append token usage to responses

**New dependencies**: None.

### Task 8.2 -- Context Compaction with Confirmation

**Difficulty**: Medium | **Dependencies**: Task 8.1

When context utilization reaches a configurable threshold, warn the user and offer to compact the conversation. Compaction generates a summary of the conversation history via a dedicated LLM call, then resets the chat with the summary injected as initial context.

**Threshold configuration**:
- Add a `compact_threshold` field to the agent configuration (in `agents.yaml`) with a default of `0.9` (90%):
  ```yaml
  main:
    compact_threshold: 0.9  # trigger compaction warning at 90% context usage
  ```
- The `AgentProfile` dataclass in `agent/profile.py` gains a `compact_threshold: float = 0.9` field.
- The threshold can also be set globally in provider-level or settings-level config.

**Warning and confirmation flow**:
- After each `_call_llm()` call in `RecursiveAgent.run()`, check if `utilization >= compact_threshold`.
- If triggered, the agent does NOT compact automatically. Instead, it signals the interface layer.
- The interface (CLI or Telegram) presents a warning and asks for confirmation:
  - **CLI**: `⚠ Context usage at 92% (117,760/128,000 tokens). Compact conversation? [y/N]`
  - **Telegram**: Send a message: `⚠ Context usage at 92%. Reply /compact to summarize and continue, or keep chatting.`
- If the user confirms (or sends `/compact`), trigger compaction. Otherwise, continue normally (the warning will appear again after the next response).

**Compaction mechanism**:
- Create a `compact_conversation()` method on `BaseAgent` (or `RecursiveAgent`):
  1. Take the current `self.messages` list (excluding the system prompt).
  2. Build a compaction prompt that asks the LLM to summarize the entire conversation into a concise but comprehensive summary, preserving: key decisions, important facts, code/document references, and any ongoing task context.
  3. Make a dedicated `_call_llm()` call with a temporary message list containing the compaction prompt + the conversation history.
  4. Call `self.reset()` to reinitialize messages to just the system prompt.
  5. Inject the summary as a special message (e.g., `{"role": "user", "content": "[Conversation summary from compaction]: ..."}` followed by `{"role": "assistant", "content": "Understood, I have the context from our previous conversation. How can I continue helping you?"}`).
  6. Reset token counters.

**Compaction prompt design** (suggested):
```
You are summarizing a conversation to preserve context for continuation.
Summarize the following conversation between a user and an AI assistant.
Your summary must preserve:
- All key decisions made
- Important facts, numbers, and references mentioned
- Any ongoing tasks or open questions
- File paths, code snippets, or document references discussed
- The user's goals and preferences expressed

Be concise but comprehensive. The summary will be used to continue the conversation
with full context. Output only the summary, no preamble.
```

**Key files to modify**:
- `agent/base.py` or `agent/recursive.py` -- add `compact_conversation()` method
- `agent/profile.py` -- add `compact_threshold` field to `AgentProfile`
- `interfaces/cli_interface.py` -- handle compaction warning, prompt for confirmation
- `interfaces/telegram_interface.py` -- handle compaction warning, respond to confirmation

**New dependencies**: None.

### Task 8.3 -- Manual /compact Slash Command

**Difficulty**: Easy | **Dependencies**: Task 8.2

Add a `/compact` slash command available in both CLI and Telegram that allows the user to manually trigger conversation compaction at any time, regardless of context utilization level.

**CLI implementation** (`interfaces/cli_interface.py`):
- Add a `/compact` case to the `if/elif` slash command chain in `run_cli()`.
- Show current token usage, then ask for confirmation: `Context: 45,000/128,000 (35%). Compact conversation? [y/N]`
- If confirmed, call `agent.compact_conversation()` and display the generated summary.
- After compaction, show the new token usage (which should be much lower).

**Telegram implementation** (`interfaces/telegram_interface.py`):
- Register a new `CommandHandler("compact", self._compact_command)`.
- The `_compact_command` handler calls `agent.compact_conversation()` on the user's agent.
- Reply with a confirmation message including the before/after token usage.

**Key files to modify**:
- `interfaces/cli_interface.py` -- add `/compact` to command dispatch and `print_help()`
- `interfaces/telegram_interface.py` -- add `_compact_command` handler and register it

---

## Area 9: Web & Academic Research Tools

flavIA is designed as an academic research assistant, but currently has no ability to search the web or access academic databases. This area introduces a comprehensive suite of tools for web search, academic literature discovery, article retrieval, and reference management -- the foundational capabilities needed for literature reviews, deep research, and producing scientifically rigorous work with correct citations.

The general architecture follows the existing tool pattern: each tool is a `BaseTool` subclass registered in `ToolRegistry`, organized under a new `tools/research/` category. Web-fetched content integrates with the existing content system (`content/converters/`, `.converted/`) with additional metadata for provenance tracking and lifecycle management.

**Design principle**: Search tools return structured results (titles, links, snippets, metadata). The agent decides which results are relevant, then uses separate tools to fetch full content (via Task 1.5's webpage converter) or download articles (via Task 9.5). This separation keeps each tool focused and composable.

### Task 9.1 -- Web Search Engine

**Difficulty**: Medium | **Dependencies**: None (enhanced by Task 1.5 for content extraction)

Create `tools/research/web_search.py` implementing a general-purpose web search tool. The tool queries a search engine API and returns structured results (title, URL, snippet, position) without accessing the pages themselves. The agent can then use the webpage converter (Task 1.5) or `read_url` tool to extract full content from selected results.

**Search providers to evaluate** (decision deferred to implementation time):

| Provider | Pros | Cons |
|----------|------|------|
| **Google Custom Search API** | Most comprehensive index, high-quality results | 100 free queries/day, $5/1000 after; requires Google Cloud project + Custom Search Engine setup |
| **Brave Search API** | Good quality, privacy-focused, generous free tier (2000 queries/month) | Smaller index than Google, newer API |
| **SerpAPI** | Unified wrapper for Google/Bing/Yahoo/Scholar/etc., structured JSON output | Paid service ($50+/month), adds dependency on third-party proxy |
| **DuckDuckGo** | Free, no API key required (via `duckduckgo-search` library) | No official API, relies on scraping; rate-limited; less comprehensive |
| **Bing Web Search API** | Good quality, Microsoft-backed | Paid after free tier (1000/month) |

**Recommended approach**: Support multiple providers via a `SearchProvider` abstraction, similar to the existing LLM provider system. Configure the active provider in `.flavia/services.yaml`:

```yaml
services:
  web_search:
    provider: "brave"        # or "google", "duckduckgo", "serpapi", "bing"
    api_key: "${BRAVE_SEARCH_API_KEY}"
    max_results: 10
    # Provider-specific settings
    google:
      cx: "${GOOGLE_SEARCH_CX}"   # Custom Search Engine ID
      api_key: "${GOOGLE_SEARCH_API_KEY}"
    brave:
      api_key: "${BRAVE_SEARCH_API_KEY}"
    duckduckgo: {}  # No API key needed
```

**Tool interface**:

| Tool | Description |
|------|-------------|
| `web_search` | Search the web. Parameters: `query` (string), `num_results` (int, default 10), `region` (string, optional), `time_range` (string: "day"/"week"/"month"/"year", optional). Returns: list of `{title, url, snippet, position}`. |

**Output format** (returned to the agent):
```
## Web Search Results for "transformer attention mechanisms survey"

1. **Attention Is All You Need** (2017)
   URL: https://arxiv.org/abs/1706.03762
   "We propose a new simple network architecture, the Transformer, based solely on attention mechanisms..."

2. **A Survey of Transformers** (2022)
   URL: https://arxiv.org/abs/2106.04554
   "Transformers have achieved great success in many AI fields..."

[10 results total]
```

The agent can then decide which URLs to read in full using the webpage converter (Task 1.5) or other content extraction tools.

**Key files to modify/create**:
- `tools/research/__init__.py` (new)
- `tools/research/web_search.py` (new)
- `tools/research/search_providers/` (new directory)
- `tools/research/search_providers/base.py` (new -- `BaseSearchProvider` ABC)
- `tools/research/search_providers/brave.py` (new)
- `tools/research/search_providers/google.py` (new)
- `tools/research/search_providers/duckduckgo.py` (new)
- `tools/__init__.py` (add `research` submodule import)
- `config/settings.py` (load `services.yaml` web_search config)

**New dependencies** (optional extras): `duckduckgo-search` (for DuckDuckGo); API-based providers use `httpx` (already a dependency).

### Task 9.2 -- Academic Database Search

**Difficulty**: Medium | **Dependencies**: None (enhanced by Task 9.5 for article download)

Create `tools/research/academic_search.py` with tools for searching open academic databases. These databases provide free APIs with rich metadata (titles, authors, abstracts, citations, DOIs, publication venues).

**Databases to integrate**:

| Database | API | Coverage | Notes |
|----------|-----|----------|-------|
| **OpenAlex** | REST API, free, no key required | 250M+ works, fully open | Successor to Microsoft Academic Graph. Best coverage, fully open, well-documented API. **Primary recommendation.** |
| **Semantic Scholar** | REST API, free (API key for higher limits) | 200M+ papers | Allen AI project. Good CS/biomedical coverage. Includes citation graphs, influential citations, TLDR summaries. |
| **Google Scholar** | No official API (scraping via `scholarly` library) | Broadest academic index | No official API; `scholarly` library scrapes results. Fragile, rate-limited, against ToS. Use as fallback only. |
| **CrossRef** | REST API, free (Polite Pool with email) | 150M+ DOIs, metadata only | Primary DOI registration agency. Excellent metadata but no full-text. Used mainly for DOI resolution (Task 9.3). |
| **CORE** | REST API, free with API key | 300M+ metadata, 36M+ full-text OA | Aggregates open access content from repositories worldwide. Good for finding OA versions. |
| **Unpaywall** | REST API, free | OA location data for 30M+ DOIs | Given a DOI, finds legal open access copies. Essential for article download (Task 9.5). |

**Tools to implement**:

| Tool | Description |
|------|-------------|
| `search_papers` | Search academic databases. Parameters: `query` (string), `databases` (list, default `["openalex"]`), `num_results` (int, default 10), `year_range` (tuple, optional), `fields` (list: "cs", "medicine", etc., optional), `sort_by` ("relevance"/"date"/"citations", default "relevance"). Returns structured results with title, authors, year, venue, DOI, abstract snippet, citation count, open access status. |
| `get_paper_details` | Get full metadata for a specific paper. Parameters: `paper_id` (string -- DOI, OpenAlex ID, Semantic Scholar ID, or URL). Returns: full abstract, all authors with affiliations, references, citation count, related papers, available PDF URLs. |
| `get_citations` | Get papers that cite a given paper. Parameters: `paper_id`, `num_results`, `sort_by`. |
| `get_references` | Get papers referenced by a given paper. Parameters: `paper_id`, `num_results`. |
| `find_similar_papers` | Find papers similar to a given paper. Parameters: `paper_id`, `num_results`. Uses Semantic Scholar's recommendations API or OpenAlex related works. |

**Output format** (for `search_papers`):
```
## Academic Search Results for "attention mechanisms in transformers"
Database: OpenAlex | Results: 10 of 15,234

1. **Attention Is All You Need** (2017)
   Authors: Vaswani, A.; Shazeer, N.; Parmar, N.; et al.
   Venue: NeurIPS 2017 | Citations: 120,000+ | DOI: 10.48550/arXiv.1706.03762
   Open Access: [checkmark] (arXiv)
   "We propose a new simple network architecture, the Transformer..."

2. **BERT: Pre-training of Deep Bidirectional Transformers** (2019)
   Authors: Devlin, J.; Chang, M.; Lee, K.; Toutanova, K.
   Venue: NAACL 2019 | Citations: 85,000+ | DOI: 10.18653/v1/N19-1423
   Open Access: [checkmark] (arXiv)
   "We introduce a new language representation model called BERT..."

[...]
```

**Configuration** in `.flavia/services.yaml`:
```yaml
services:
  academic_search:
    default_databases: ["openalex", "semantic_scholar"]
    semantic_scholar:
      api_key: "${SEMANTIC_SCHOLAR_API_KEY}"  # optional, for higher rate limits
    core:
      api_key: "${CORE_API_KEY}"  # required for CORE API
    openalex:
      email: "${OPENALEX_EMAIL}"  # for polite pool (higher rate limits)
```

**Key files to modify/create**:
- `tools/research/academic_search.py` (new)
- `tools/research/academic_providers/` (new directory)
- `tools/research/academic_providers/base.py` (new -- `BaseAcademicProvider` ABC)
- `tools/research/academic_providers/openalex.py` (new)
- `tools/research/academic_providers/semantic_scholar.py` (new)
- `tools/research/academic_providers/google_scholar.py` (new -- via `scholarly` library)
- `tools/research/academic_providers/core.py` (new)
- `tools/research/academic_providers/unpaywall.py` (new)
- `tools/research/__init__.py` (register tools)

**New dependencies** (optional extras): `scholarly` (for Google Scholar, use cautiously); all other APIs use `httpx`.

### Task 9.3 -- DOI Metadata Resolution

**Difficulty**: Easy | **Dependencies**: None

Create `tools/research/doi_resolver.py` with a tool for resolving DOIs to full bibliographic metadata using the CrossRef and DataCite REST APIs. This is a foundational tool used by Tasks 9.5 and 9.7 for generating citations and BibTeX entries.

**Tool interface**:

| Tool | Description |
|------|-------------|
| `resolve_doi` | Resolve a DOI to full metadata. Parameters: `doi` (string -- e.g., "10.1145/3474085.3475688" or full URL "https://doi.org/..."). Returns: title, authors (with affiliations and ORCID when available), journal/venue, volume, issue, pages, year, publisher, ISSN, abstract, references count, license, open access URL (via Unpaywall), BibTeX entry. |

**Implementation**:
- Primary: CrossRef API (`https://api.crossref.org/works/{doi}`) -- covers most DOIs, returns rich metadata including references and license info
- Fallback: DataCite API (`https://api.datacite.org/dois/{doi}`) -- covers DOIs not in CrossRef (datasets, software, etc.)
- Enhancement: Query Unpaywall (`https://api.unpaywall.org/v2/{doi}?email=...`) to find open access PDF locations
- The tool automatically generates a BibTeX entry from the metadata (used by Task 9.7)

**Output format**:
```
## DOI: 10.48550/arXiv.1706.03762

**Title**: Attention Is All You Need
**Authors**: Ashish Vaswani, Noam Shazeer, Niki Parmar, Jakob Uszkoreit, Llion Jones, Aidan N. Gomez, Lukasz Kaiser, Illia Polosukhin
**Venue**: Advances in Neural Information Processing Systems (NeurIPS), 2017
**Publisher**: Curran Associates, Inc.
**DOI**: https://doi.org/10.48550/arXiv.1706.03762
**Open Access**: https://arxiv.org/pdf/1706.03762

### BibTeX
@inproceedings{vaswani2017attention,
  title={Attention is all you need},
  author={Vaswani, Ashish and Shazeer, Noam and Parmar, Niki and ...},
  booktitle={Advances in Neural Information Processing Systems},
  volume={30},
  year={2017}
}
```

No API key required for CrossRef (use "polite pool" by including an email in the `User-Agent` or `mailto` parameter). No API key for DataCite. Unpaywall requires an email address only.

**Key files to modify/create**:
- `tools/research/doi_resolver.py` (new)
- `tools/research/__init__.py` (register tool)

**New dependencies**: None (uses `httpx`, already a dependency).

### Task 9.4 -- Scopus Integration

**Difficulty**: Medium | **Dependencies**: None (enhanced by Task 9.3 for DOI cross-referencing)

Create `tools/research/scopus_search.py` with tools for accessing the Scopus database via the Elsevier API. Scopus is available via institutional networks (CAPES, university VPNs) and provides journal metrics (SJR, CiteScore, percentiles), author profiles (h-index, publications), and comprehensive citation data.

**Two implementation approaches** (to be evaluated at implementation time):

**Approach A -- Native tools (recommended for full integration)**:
Implement Scopus API calls directly using `httpx`, following the existing `BaseTool` pattern. This provides full control over error handling, caching, and integration with other research tools.

**Approach B -- MCP server integration**:
The environment already has MCP servers for Scopus search (`scopus-search_buscar_journal_percentile`, `scopus-search_buscar_autores`, etc.). If flavIA gains MCP client support in the future, these existing servers could be leveraged directly. The roadmap should document this option but not depend on it for the initial implementation.

**Tools to implement** (Approach A):

| Tool | Description |
|------|-------------|
| `scopus_search_papers` | Search Scopus for papers. Parameters: `query`, `num_results`, `year_range`, `subject_area`, `sort_by`. Returns: titles, authors, DOIs, citations, source, EID. |
| `scopus_journal_metrics` | Get journal metrics. Parameters: `journal_name` or `issn`. Returns: SJR, CiteScore, SNIP, highest percentile, subject categories, H-index. |
| `scopus_author_profile` | Get author profile. Parameters: `author_name`, `affiliation` (optional), `orcid` (optional), `scopus_id` (optional). Returns: h-index, total citations, document count, affiliation history, subject areas, co-authors. |
| `scopus_citations` | Get citation details for a paper. Parameters: `doi` or `scopus_eid`. Returns: list of citing papers with metadata. |

**Configuration** in `.flavia/services.yaml`:
```yaml
services:
  scopus:
    api_key: "${SCOPUS_API_KEY}"  # Elsevier Developer API key
    institutional_token: "${SCOPUS_INST_TOKEN}"  # optional, for higher limits
    # Note: many Scopus API features require access from an institutional IP
    # (university network, CAPES VPN, etc.)
```

**Important notes**:
- The Scopus API requires an API key (free registration at dev.elsevier.com) BUT many endpoints also require access from an institutional IP address
- When accessed from outside an institutional network, the API may return limited results or 403 errors
- The tool should gracefully handle access restrictions, informing the user when institutional access is needed
- Consider caching results locally (in `.flavia/cache/scopus/`) to reduce API calls and enable offline access to previously fetched data

**Key files to modify/create**:
- `tools/research/scopus_search.py` (new)
- `tools/research/__init__.py` (register tools)
- `config/settings.py` (load Scopus config from `services.yaml`)

**New dependencies**: None (uses `httpx`). Optional: `pybliometrics` library for a higher-level Scopus API wrapper (but adds a significant dependency).

### Task 9.5 -- Article Download & Content Integration

**Difficulty**: Hard | **Dependencies**: Task 9.2 (academic search provides DOIs/URLs), Task 9.3 (DOI resolution provides OA URLs), Task 1.5 (webpage converter for HTML articles)

Create `tools/research/article_download.py` with tools for downloading academic articles (PDFs) and integrating them into the flavIA content system. Downloaded articles are tracked with provenance metadata and support a temporary/permanent lifecycle.

**Tools to implement**:

| Tool | Description |
|------|-------------|
| `download_article` | Download an article PDF. Parameters: `doi` (string, optional), `url` (string, optional -- direct PDF URL), `search_id` (string, optional -- associates with a research session from Task 9.8). Attempts to find and download a PDF using, in order: (1) Unpaywall OA URL, (2) direct URL if provided, (3) publisher URL with institutional access. Returns: success/failure, local file path, metadata. |
| `list_downloads` | List downloaded articles. Parameters: `search_id` (optional -- filter by research session), `status` (optional -- "temporary"/"permanent"/"all"). Returns: list of articles with metadata, paths, and status. |
| `manage_download` | Change download status. Parameters: `article_id` or `search_id`, `action` ("make_permanent"/"delete"/"delete_session"). |

**Content system integration**:

Downloaded articles integrate with the existing content system (`content/converters/`, `.converted/`, `ContentCatalog`) with additional metadata:

```python
# Extended FileEntry metadata for downloaded articles
{
    "source": "web_research",       # distinguishes from local files
    "search_id": "search_abc123",   # links to research session (Task 9.8)
    "doi": "10.1145/...",
    "download_url": "https://...",
    "download_date": "2025-02-10T14:30:00",
    "status": "temporary",          # "temporary" | "permanent"
    "bibtex_key": "vaswani2017attention",
    "metadata": {
        "title": "...",
        "authors": [...],
        "year": 2017,
        "venue": "..."
    }
}
```

**Lifecycle management**:
- **Temporary** (default): Downloaded articles start as temporary. They are stored in `.flavia/research_downloads/` (separate from the project's main files). They appear in the content catalog with a `[temp]` marker. They can be deleted individually or by search session.
- **Permanent**: When the user marks an article as permanent (via `manage_download`), the PDF is moved to the project's file tree (configurable destination, e.g., `references/` or `papers/`), the content catalog entry is updated, and the article becomes a regular part of the project content.
- **Cleanup**: A `/research-cleanup` command (or option in `manage_download`) deletes all temporary downloads older than a configurable threshold (default: 30 days).

**Download sources** (tried in order):
1. **Unpaywall**: Query Unpaywall API with DOI to find legal OA copies (green or gold OA)
2. **Direct URL**: If a direct PDF URL was provided (e.g., from arXiv, PMC, or institutional repository)
3. **Publisher site**: If accessed from an institutional network (see Task 9.6), attempt to download from the publisher
4. **Preprint servers**: Check arXiv, bioRxiv, medRxiv for preprint versions matching the DOI/title

The tool should inform the agent (and thus the user) about the source and legal status of each download.

**Key files to modify/create**:
- `tools/research/article_download.py` (new)
- `content/catalog.py` (extend `FileEntry` with research metadata fields)
- `content/scanner.py` (extend to scan `.flavia/research_downloads/`)
- `tools/research/__init__.py` (register tools)

**New dependencies**: None (uses `httpx` for downloads, existing PDF converter for processing).

### Task 9.6 -- CAPES/Academic Network Publisher Access

**Difficulty**: Hard | **Dependencies**: Task 9.5 (article download infrastructure), Task 9.4 (Scopus already handles one institutional-access service)

Enable access to licensed academic content when flavIA is running on an institutional network (university, CAPES VPN, etc.). This task involves detecting institutional network access, configuring proxy settings, and maintaining a list of publishers accessible via Brazilian academic networks through the CAPES portal.

**Publishers available via CAPES** (Portal de Periodicos da CAPES):

| Publisher / Database | Coverage | Access Method |
|---------------------|----------|---------------|
| **Elsevier (ScienceDirect)** | ~2,500 journals, 40,000+ books | IP-based + CAFe authentication |
| **Springer Nature** | ~3,000 journals, books, protocols | IP-based |
| **Wiley** | ~1,500 journals | IP-based |
| **IEEE Xplore** | ~200+ journals, conference proceedings | IP-based |
| **ACM Digital Library** | CS journals and conference proceedings | IP-based |
| **Taylor & Francis** | ~2,200 journals | IP-based |
| **SAGE** | ~1,000 journals | IP-based |
| **Oxford University Press** | ~400 journals | IP-based |
| **Cambridge University Press** | ~400 journals | IP-based |
| **ACS (American Chemical Society)** | ~80 journals | IP-based |
| **APS (American Physical Society)** | ~15 journals | IP-based |
| **RSC (Royal Society of Chemistry)** | ~40 journals | IP-based |
| **Web of Science / Clarivate** | Citation index, JCR | IP-based + CAFe |
| **Scopus / Elsevier** | Citation index, metrics | IP-based (covered by Task 9.4) |
| **JSTOR** | Multidisciplinary archive | IP-based |
| **ProQuest** | Dissertations, theses | IP-based + CAFe |
| **EBSCO** | Multidisciplinary databases | IP-based |

**Note**: This list should be maintained as a configuration file (not hardcoded) since CAPES contracts change periodically. A `publishers.yaml` configuration file in the defaults directory would allow easy updates.

**Implementation**:

1. **Network detection tool**:
   - `check_institutional_access`: Detect whether the current network provides institutional access by testing known publisher endpoints. Parameters: none. Returns: list of accessible publishers, network type (direct IP, VPN, CAFe proxy), and access status.
   - Implementation: make HEAD requests to known publisher test URLs (e.g., ScienceDirect API, IEEE API) and check for 200 vs 403 responses.

2. **Publisher access configuration** in `.flavia/services.yaml`:
   ```yaml
   services:
     institutional_access:
       mode: "auto"  # "auto" (detect), "direct" (institutional IP), "proxy", "none"
       proxy:
         http: "${INSTITUTIONAL_PROXY_HTTP}"  # for proxy-based access
         https: "${INSTITUTIONAL_PROXY_HTTPS}"
       cafe:  # CAFe (Comunidade Academica Federada) authentication
         institution: "ITA"
         username: "${CAFE_USERNAME}"
         password: "${CAFE_PASSWORD}"
   ```

3. **Publisher registry** (`src/flavia/defaults/publishers.yaml`):
   ```yaml
   publishers:
     elsevier:
       name: "Elsevier / ScienceDirect"
       base_url: "https://api.elsevier.com"
       pdf_pattern: "https://www.sciencedirect.com/science/article/pii/{pii}/pdfft"
       test_url: "https://api.elsevier.com/authenticate"
       doi_prefix: ["10.1016"]
     springer:
       name: "Springer Nature"
       base_url: "https://link.springer.com"
       pdf_pattern: "https://link.springer.com/content/pdf/{doi}.pdf"
       test_url: "https://link.springer.com"
       doi_prefix: ["10.1007", "10.1038"]
     ieee:
       name: "IEEE Xplore"
       base_url: "https://ieeexplore.ieee.org"
       pdf_pattern: "https://ieeexplore.ieee.org/stamp/stamp.jsp?arnumber={id}"
       test_url: "https://ieeexplore.ieee.org/xpl/apiGateway"
       doi_prefix: ["10.1109"]
     # ... additional publishers
   ```

4. **Enhanced article download flow** (extends Task 9.5):
   When `download_article` is called and the article is behind a paywall:
   - Check if the DOI prefix matches a known publisher
   - Test if the publisher is accessible from the current network
   - If accessible, attempt download using the publisher's PDF URL pattern
   - If not accessible, inform the user and suggest: (a) connecting to institutional VPN, (b) checking Unpaywall for OA copies, (c) requesting via interlibrary loan

**Key files to modify/create**:
- `tools/research/institutional_access.py` (new)
- `src/flavia/defaults/publishers.yaml` (new)
- `tools/research/article_download.py` (extend download flow)
- `config/settings.py` (load institutional access config)
- `tools/research/__init__.py` (register tools)

**New dependencies**: None (uses `httpx` for HTTP requests).

### Task 9.7 -- BibTeX Reference Management

**Difficulty**: Medium | **Dependencies**: Task 9.3 (DOI resolution provides BibTeX entries), Task 9.2 (academic search provides paper metadata), Task 5.1 (write tools for .bib file modification)

Create `tools/research/bibtex_manager.py` with tools for automatically generating, maintaining, and managing BibTeX reference files (`.bib`). The BibTeX manager ensures that all cited works have correct, complete, and consistently formatted entries.

**Tools to implement**:

| Tool | Description |
|------|-------------|
| `add_reference` | Add a BibTeX entry to a .bib file. Parameters: `doi` (string, optional -- auto-generates entry via Task 9.3), `bibtex` (string, optional -- raw BibTeX entry), `bib_file` (string, default "references.bib"), `key` (string, optional -- custom citation key, auto-generated if omitted). Validates the entry, deduplicates, and appends to the file. |
| `search_references` | Search within a .bib file. Parameters: `bib_file`, `query` (searches across all fields), `field` (optional -- search specific field: "author", "title", "year", etc.). Returns matching entries. |
| `list_references` | List all entries in a .bib file with summary info. Parameters: `bib_file`, `sort_by` ("key"/"year"/"author", default "key"). |
| `remove_reference` | Remove an entry from a .bib file. Parameters: `bib_file`, `key`. |
| `validate_references` | Validate a .bib file: check for missing required fields, duplicate keys, DOIs that can be resolved for additional metadata. Parameters: `bib_file`. Returns: list of warnings and suggestions. |
| `export_citations` | Export references in various formats. Parameters: `bib_file`, `keys` (list, optional -- specific entries; all if omitted), `format` ("bibtex"/"apa"/"ieee"/"acm"/"chicago"/"abnt", default "bibtex"). Returns formatted citations. |

**Citation key generation**:
Auto-generated keys follow the pattern `{first_author_lastname}{year}{first_title_word}`, e.g., `vaswani2017attention`, `devlin2019bert`. Duplicate keys are disambiguated with a letter suffix: `smith2020neural`, `smith2020neurala`.

**Integration with other tools**:
- When `download_article` (Task 9.5) successfully downloads a paper, it automatically calls `add_reference` to add the BibTeX entry to the project's default `.bib` file
- When `resolve_doi` (Task 9.3) is called, it returns a BibTeX entry that can be piped to `add_reference`
- The `search_papers` tool (Task 9.2) includes a `save_to_bib` parameter that automatically adds selected results to the `.bib` file

**Configuration** in `.flavia/services.yaml`:
```yaml
services:
  bibtex:
    default_file: "references.bib"  # relative to project root
    citation_style: "bibtex"         # default export format
    auto_add_on_download: true       # auto-add BibTeX when downloading articles
    key_format: "{author}{year}{title_word}"  # citation key pattern
```

**Key files to modify/create**:
- `tools/research/bibtex_manager.py` (new)
- `tools/research/__init__.py` (register tools)

**New dependencies** (optional): `bibtexparser` (for robust BibTeX parsing). Alternative: implement a lightweight parser using regex for basic operations.

### Task 9.8 -- Research Session Management

**Difficulty**: Medium | **Dependencies**: Task 9.1 (web search), Task 9.2 (academic search), Task 9.5 (article download)

Create `tools/research/session_manager.py` with tools for organizing and managing research activities. Each research session groups related searches, results, and downloads under a unique ID, enabling the user to review, export, or clean up the results of a specific research effort.

**Concept**:
A **research session** is a logical grouping of search queries, results, and downloaded articles related to a specific research topic or task (e.g., "literature review on attention mechanisms", "finding datasets for sentiment analysis"). Sessions provide:
- Traceability: know which searches produced which results
- Lifecycle management: delete all temporary results from a specific research session
- Export: generate a summary or report of a research session's findings
- Continuity: resume a previous research session in a new conversation

**Tools to implement**:

| Tool | Description |
|------|-------------|
| `create_research_session` | Create a new research session. Parameters: `name` (string), `description` (string, optional), `topic` (string, optional). Returns: `session_id`. |
| `list_research_sessions` | List all research sessions. Parameters: `status` ("active"/"archived"/"all", default "active"). Returns: sessions with stats (num queries, num results, num downloads). |
| `get_session_details` | Get full details of a research session. Parameters: `session_id`. Returns: all queries performed, results found, articles downloaded, BibTeX entries generated. |
| `archive_session` | Archive a research session (mark as complete, keep data). Parameters: `session_id`. |
| `delete_session` | Delete a research session and all its temporary downloads. Parameters: `session_id`, `keep_permanent` (bool, default true -- keep articles marked as permanent). |
| `export_session` | Export a session summary. Parameters: `session_id`, `format` ("markdown"/"bibtex"/"json", default "markdown"). Returns: formatted summary including queries, key findings, and references. |

**Storage**:
Research sessions are stored in `.flavia/research_sessions/` as YAML files:

```yaml
# .flavia/research_sessions/session_abc123.yaml
id: "session_abc123"
name: "Attention Mechanisms Survey"
description: "Literature review on attention mechanisms in transformers"
created: "2025-02-10T14:30:00"
status: "active"  # active | archived
queries:
  - id: "q1"
    type: "academic_search"
    query: "attention mechanisms transformers survey"
    database: "openalex"
    timestamp: "2025-02-10T14:31:00"
    num_results: 10
  - id: "q2"
    type: "web_search"
    query: "transformer attention visualization tools"
    provider: "brave"
    timestamp: "2025-02-10T14:45:00"
    num_results: 8
results:
  - query_id: "q1"
    doi: "10.48550/arXiv.1706.03762"
    title: "Attention Is All You Need"
    status: "downloaded"
    download_path: ".flavia/research_downloads/vaswani2017attention.pdf"
    bibtex_key: "vaswani2017attention"
    lifecycle: "permanent"
  - query_id: "q1"
    doi: "10.48550/arXiv.2106.04554"
    title: "A Survey of Transformers"
    status: "metadata_only"
    lifecycle: "temporary"
```

**Slash commands** (CLI and Telegram):
- `/research` -- list active research sessions
- `/research <session_id>` -- show session details
- `/research-new <name>` -- create a new session
- `/research-cleanup` -- delete all temporary downloads older than threshold

**Integration with search tools**:
When `web_search` or `search_papers` is called with a `session_id` parameter, the query and results are automatically logged in the session. If no session is active, results are still returned but not tracked.

**Key files to modify/create**:
- `tools/research/session_manager.py` (new)
- `interfaces/cli_interface.py` (add `/research` slash commands)
- `interfaces/telegram_interface.py` (add `/research` command handler)
- `tools/research/__init__.py` (register tools)

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

Area 8 -- Context Window Management:
Task 8.1 (Token Usage Tracking) ── Task 8.2 (Compaction with Confirmation)
                                              └── Task 8.3 (/compact Command)

Area 9 -- Web & Academic Research:
Task 9.1 (Web Search) ─────────────────────────────────────┐
Task 9.2 (Academic Database Search) ───┬── Task 9.5 (Article Download) ── Task 9.6 (CAPES Access)
Task 9.3 (DOI Metadata Resolution) ───┘            │
Task 9.4 (Scopus Integration) ─────────────────────┤
                                                    ├── Task 9.7 (BibTeX Management)
Task 9.8 (Research Session Mgmt) ── depends on Tasks 9.1, 9.2, 9.5

Cross-area dependencies for Area 9:
Task 9.1 enhanced by ── Task 1.5 (YouTube/Web converters, for content extraction)
Task 9.5 depends on ── Task 1.5 (webpage converter for HTML articles)
Task 9.7 depends on ── Task 5.1 (write tools for .bib file modification)
```

## Suggested Implementation Order

Tasks ordered by difficulty (easy first) and dependency readiness. Each task can be implemented independently as long as its dependencies are met.

| Order | Task | Difficulty | Area |
|-------|------|------------|------|
| 1 | ~~**4.1** Consolidate info commands~~ | ~~Easy~~ | ~~CLI~~ | ✓ DONE |
| 2 | **4.2** Runtime agent switching in CLI | Easy | CLI |
| 3 | **4.3** Runtime model switching in CLI | Easy | CLI |
| 4 | **4.7** Unified slash command help system | Easy | CLI |
| 5 | **1.3** Word/Office document converter | Easy | File Processing |
| 6 | **8.1** Token usage tracking & display | Easy | Context Management |
| 7 | **8.3** Manual /compact slash command | Easy | Context Management |
| 8 | **5.1** Write/Edit file tools | Medium | File Modification |
| 9 | **1.1** Audio/Video transcription converter | Medium | File Processing |
| 10 | **1.2** Image description converter | Medium | File Processing |
| 11 | **4.4** In-session provider & model management | Medium | CLI |
| 12 | **4.5** Standard default agent | Medium | CLI |
| 13 | **2.1** Structured agent profiles | Medium | Agents |
| 14 | **8.2** Context compaction with confirmation | Medium | Context Management |
| 15 | **3.1** YAML-based bot configuration | Medium | Messaging |
| 16 | **6.1** LaTeX compilation tool | Medium | Academic Workflow |
| 17 | **4.6** Global agent definitions | Medium | CLI |
| 18 | **2.2** CLI agent management commands | Medium | Agents |
| 19 | **3.2** Per-conversation agent binding | Medium | Messaging |
| 20 | **3.3** Multi-bot support | Medium | Messaging |
| 21 | **1.5** Online source converters (YouTube/Web) | Medium | File Processing |
| 22 | **3.6** Web API interface | Medium | Messaging |
| 23 | **1.4** OCR + LaTeX equation support | Hard | File Processing |
| 24 | **3.4** Abstract messaging interface | Hard | Messaging |
| 25 | **2.3** Meta-agent for agent generation | Hard | Agents |
| 26 | **6.2** Sandboxed script execution (Python/MATLAB) | Hard | Academic Workflow |
| 27 | **7.1** Email integration (IMAP/SMTP) | Hard | External Services |
| 28 | **7.2** Google Calendar integration | Hard | External Services |
| 29 | **3.5** WhatsApp integration | Hard | Messaging |
| 30 | **9.3** DOI metadata resolution | Easy | Web & Academic Research |
| 31 | **9.1** Web search engine | Medium | Web & Academic Research |
| 32 | **9.2** Academic database search | Medium | Web & Academic Research |
| 33 | **9.4** Scopus integration | Medium | Web & Academic Research |
| 34 | **9.7** BibTeX reference management | Medium | Web & Academic Research |
| 35 | **9.8** Research session management | Medium | Web & Academic Research |
| 36 | **9.5** Article download & content integration | Hard | Web & Academic Research |
| 37 | **9.6** CAPES/academic network publisher access | Hard | Web & Academic Research |

This order is a suggestion. Tasks can be implemented in any order that respects the dependency graph above.
