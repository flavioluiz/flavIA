# Roadmap

Planned features and improvements for flavIA, organized by area. Each task includes a difficulty rating and dependencies, so they can be implemented incrementally in any convenient order.

**Difficulty scale**: Easy (a few hours) | Medium (1-2 days) | Hard (3+ days)

---

## 📋 Executive Summary

This roadmap outlines **41 tasks** across **10 major areas** to extend flavIA from a read-only research assistant into a comprehensive, production-ready AI agent system with multimodal processing, write capabilities, external service integration, web & academic research tools, multi-platform deployment, and file delivery through messaging interfaces.

### Quick Stats
- **9 Easy tasks** (< 1 day each) — Quick wins for immediate value — **4 completed** ✓
- **23 Medium tasks** (1-2 days each) — Core feature development — **3 completed** ✓
- **9 Hard tasks** (3+ days each) — Complex integrations requiring careful design
- **Total completed so far**: **7 / 41 tasks** ✓

### Strategic Priorities
1. **Immediate value** (Tasks 4.1-4.8, 8.1): Improve CLI UX and add token tracking
2. **Core capabilities** (Tasks 5.1, 1.1-1.3): Enable file writing and expand content processing
3. **Academic workflows** (Tasks 6.1-6.2): LaTeX compilation and script execution
4. **Production readiness** (Tasks 3.1-3.6, 8.2-8.3): Multi-platform bots and context management
5. **Web & academic research** (Tasks 9.1-9.8): Web search, academic databases, DOI resolution, Scopus, article download, BibTeX management
6. **Telegram file delivery** (Tasks 10.1-10.3): Structured agent responses, send file tool, and Telegram document delivery
7. **Advanced features** (Tasks 7.1-7.2, 2.3): External services and meta-agents

---

## 📖 Table of Contents

### [Area 1: Multimodal File Processing](roadmap/area-1-multimodal-file-processing.md) (5 tasks)
Expand content processing beyond PDF/text to audio, video, images, Office docs, and online sources.

- **1.1** Audio/Video Transcription (Medium) — Whisper API transcription
- **1.2** Image Description (Medium) — GPT-4o vision for images
- **1.3** Word/Office Documents (Easy) — python-docx, openpyxl, python-pptx
- **1.4** OCR + LaTeX Equations (Hard) — Handwritten docs, scanned PDFs, equation OCR
- **1.5** YouTube/Web Converters (Medium) — yt-dlp, trafilatura

### [Area 2: Agent System Improvements](roadmap/area-2-agent-system-improvements.md) (3 tasks)
Redesign agent configuration for richer, more maintainable agent definitions.

- **2.1** Structured Agent Profiles (Medium) — Replace free-form context with role/expertise/personality fields
- **2.2** CLI Agent Management (Medium) — /agent-create, /agent-edit, /agent-delete commands
- **2.3** Meta-Agent Generation (Hard) — AI-powered agent architect for automatic config generation

### [Area 3: Messaging Platform Framework](roadmap/area-3-messaging-platform-framework.md) (6 tasks)
Transform Telegram integration into a multi-platform bot framework.

- **3.1** YAML Bot Configuration (Medium) — Replace env vars with `.flavia/bots.yaml`
- **3.2** Per-Conversation Agents (Medium) — Each user can switch agents mid-chat
- **3.3** Multi-Bot Support (Medium) — Run multiple bot instances concurrently
- **3.4** Abstract Messaging Interface (Hard) — BaseMessagingBot ABC for platform independence
- **3.5** WhatsApp Integration (Hard) — WhatsApp Business API or third-party bridge
- **3.6** Web API Interface (Medium) — HTTP/WebSocket API for custom frontends

### [Area 4: CLI Improvements](roadmap/area-4-cli-improvements.md) (8 tasks)
Consolidate commands, eliminate redundancies, add runtime switching, and introduce global agents.

- **4.1** ~~Consolidate Info Commands (Easy)~~ — **DONE** ✓ Merged /models into /providers, /tools shows categories + schema, /config shows active settings
- **4.2** ~~Runtime Agent Switching (Easy)~~ — **DONE** ✓ /agent command to list agents or switch mid-session
- **4.3** ~~Runtime Model Switching (Easy)~~ — **DONE** ✓ /model command to change models without restart
- **4.4** ~~In-Session Provider Management (Medium)~~ — **DONE** ✓ /provider-setup, /provider-manage, /provider-test from within CLI
- **4.5** Standard Default Agent (Medium) — Built-in fallback agent always available
- **4.6** Global Agent Definitions (Medium) — User-level agents in ~/.config/flavia/agents.yaml
- **4.7** ~~Unified Help System (Easy)~~ — **DONE** ✓ Structured /help with categories, command registry, and per-command help
- **4.8** ~~Expand questionary Adoption (Medium)~~ — **DONE** ✓ Interactive prompts with arrow-key menus, autocomplete, and non-TTY fallback

### [Area 5: File Modification Tools](roadmap/area-5-file-modification-tools.md) (1 task)
Enable write capabilities using the existing permission infrastructure.

- **5.1** Write/Edit File Tools (Medium) — write_file, edit_file, insert_text, append_file with permission checks

### [Area 6: Academic Workflow Tools](roadmap/area-6-academic-workflow-tools.md) (2 tasks)
Bridge the gap between text generation and actual research output.

- **6.1** LaTeX Compilation (Medium) — Compile .tex to PDF with pdflatex/latexmk
- **6.2** Sandboxed Script Execution (Hard) — Run Python/MATLAB scripts with user confirmation + AST-based safety

### [Area 7: External Service Integration](roadmap/area-7-external-service-integration.md) (2 tasks)
Connect to email and calendar services with read-autonomous, write-confirmed pattern.

- **7.1** Email Integration (Hard) — IMAP/SMTP for Gmail with read/search/send tools
- **7.2** Google Calendar (Hard) — OAuth2 integration for event management

### [Area 8: Context Window Management & Compaction](roadmap/area-8-context-window-management.md) (3 tasks)
Track token usage and automatically summarize conversations approaching context limits.

- **8.1** ~~Token Usage Tracking (Easy)~~ ✅ — Capture response.usage, display utilization in CLI/Telegram
- **8.2** ~~Compaction with Confirmation (Medium)~~ ✅ — Auto-summarize at threshold with user approval
- **8.3** Manual /compact Command (Easy) — On-demand conversation summarization

### [Area 9: Web & Academic Research Tools](roadmap/area-9-web-academic-research-tools.md) (8 tasks)
Comprehensive web and academic search toolkit for literature reviews, deep research, and precise scientific citation management.

- **9.1** Web Search Engine (Medium) — Multi-provider web search (Google, Brave, DuckDuckGo)
- **9.2** Academic Database Search (Medium) — Google Scholar, OpenAlex, Semantic Scholar
- **9.3** DOI Metadata Resolution (Easy) — CrossRef/DataCite DOI lookup and metadata extraction
- **9.4** Scopus Integration (Medium) — Scopus API for journal metrics, author profiles, and citations
- **9.5** Article Download & Content Integration (Hard) — Download PDFs, integrate with content system
- **9.6** CAPES/Academic Network Publisher Access (Hard) — Access licensed publisher content via institutional networks
- **9.7** BibTeX Reference Management (Medium) — Automatic .bib file generation and maintenance
- **9.8** Research Session Management (Medium) — Track, manage, and organize web research results

### [Area 10: Telegram File Delivery](roadmap/area-10-telegram-file-delivery.md) (3 tasks)
Enable the agent to send files directly through the Telegram chat, with structured agent responses to support side effects beyond plain text.

- **10.1** Structured Agent Responses (Medium) — `AgentResponse` dataclass with text + actions, replacing plain `str` return
- **10.2** Send File Tool (Easy) — `send_file(path)` tool that validates and registers a file delivery action
- **10.3** Telegram File Delivery Handler (Medium) — Bot processes `SendFileAction` and calls `reply_document()`

---

## 🎯 Implementation Roadmap Overview

### Phase 1: Foundation & Quick Wins (Tasks 4.1-4.8, 8.1, 1.3)
**Timeline**: 1-2 weeks | **Effort**: 7 Easy + 2 Medium = ~7-9 days

Improve CLI usability, add token tracking, expand file processing to Office docs, and enhance interactive prompts with questionary. All tasks are independent and can be implemented in parallel.

**Deliverables**:
- Unified, consistent CLI commands with better help
- Real-time token usage visibility in CLI and Telegram
- Support for .docx, .xlsx, .pptx files
- Interactive prompts with autocomplete, file paths, and menus

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
Task 4.8 (Expand questionary) ──────┘     depends on Task 4.7
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

Area 10 -- Telegram File Delivery:
Task 10.1 (Structured Agent Responses) ──┬── Task 10.2 (Send File Tool)
                                          └── Task 10.3 (Telegram File Delivery Handler)
Task 10.2 ─────────────────────────────────── Task 10.3

Cross-area dependencies for Area 10:
Task 10.3 benefits from ── Task 3.4 (Abstract Messaging Interface)
Task 10.3 benefits from ── Task 3.1 (YAML Bot Config, for per-bot file size limits)
```

## Suggested Implementation Order

Tasks ordered by a pragmatic implementation sequence that balances dependency readiness and delivery value. Each task can be implemented independently as long as its dependencies are met.

| Order | Task | Difficulty | Area |
|-------|------|------------|------|
| 1 | ~~**4.1** Consolidate info commands~~ | ~~Easy~~ | ~~CLI~~ |
| 2 | ~~**4.2** Runtime agent switching in CLI~~ | ~~Easy~~ | ~~CLI~~ |
| 3 | ~~**4.3** Runtime model switching in CLI~~ | ~~Easy~~ | ~~CLI~~ |
| 4 | ~~**4.7** Unified slash command help system~~ | ~~Easy~~ | ~~CLI~~ |
| 5 | **1.3** Word/Office document converter | Easy | File Processing |
| 6 | ~~**8.1** Token usage tracking & display~~ | ~~Easy~~ | ~~Context Management~~ |
| 7 | **8.3** Manual /compact slash command | Easy | Context Management |
| 8 | **5.1** Write/Edit file tools | Medium | File Modification |
| 9 | **1.1** Audio/Video transcription converter | Medium | File Processing |
| 10 | **1.2** Image description converter | Medium | File Processing |
| 11 | ~~**4.4** In-session provider & model management~~ | ~~Medium~~ | ~~CLI~~ |
| 12 | **4.5** Standard default agent | Medium | CLI |
| 13 | ~~**4.8** Expand questionary adoption for prompts~~ | ~~Medium~~ | ~~CLI~~ |
| 14 | **2.1** Structured agent profiles | Medium | Agents |
| 15 | ~~**8.2** Context compaction with confirmation~~ | ~~Medium~~ | ~~Context Management~~ |
| 16 | **3.1** YAML-based bot configuration | Medium | Messaging |
| 17 | **6.1** LaTeX compilation tool | Medium | Academic Workflow |
| 18 | **4.6** Global agent definitions | Medium | CLI |
| 19 | **2.2** CLI agent management commands | Medium | Agents |
| 20 | **3.2** Per-conversation agent binding | Medium | Messaging |
| 21 | **3.3** Multi-bot support | Medium | Messaging |
| 22 | **1.5** Online source converters (YouTube/Web) | Medium | File Processing |
| 23 | **3.6** Web API interface | Medium | Messaging |
| 24 | **1.4** OCR + LaTeX equation support | Hard | File Processing |
| 25 | **3.4** Abstract messaging interface | Hard | Messaging |
| 26 | **2.3** Meta-agent for agent generation | Hard | Agents |
| 27 | **6.2** Sandboxed script execution (Python/MATLAB) | Hard | Academic Workflow |
| 28 | **7.1** Email integration (IMAP/SMTP) | Hard | External Services |
| 29 | **7.2** Google Calendar integration | Hard | External Services |
| 30 | **3.5** WhatsApp integration | Hard | Messaging |
| 31 | **9.3** DOI metadata resolution | Easy | Web & Academic Research |
| 32 | **9.1** Web search engine | Medium | Web & Academic Research |
| 33 | **9.2** Academic database search | Medium | Web & Academic Research |
| 34 | **9.4** Scopus integration | Medium | Web & Academic Research |
| 35 | **9.7** BibTeX reference management | Medium | Web & Academic Research |
| 36 | **9.8** Research session management | Medium | Web & Academic Research |
| 37 | **9.5** Article download & content integration | Hard | Web & Academic Research |
| 38 | **9.6** CAPES/academic network publisher access | Hard | Web & Academic Research |
| 39 | **10.1** Structured agent responses | Medium | Telegram File Delivery |
| 40 | **10.2** Send file tool | Easy | Telegram File Delivery |
| 41 | **10.3** Telegram file delivery handler | Medium | Telegram File Delivery |

This order is a suggestion. Tasks can be implemented in any order that respects the dependency graph above.
