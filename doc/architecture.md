# Architecture

## Overview

flavIA is organized into modules under `src/flavia/`. The entry point is the `flavia` command, defined in `pyproject.toml` as `flavia.cli:main`.

## Project structure

```
src/flavia/
├── __init__.py               # Version (0.1.0)
├── __main__.py               # python -m flavia
├── cli.py                    # Entry point, argument parsing
├── setup_wizard.py           # AI-assisted initialization wizard
├── venv_bootstrap.py         # Automatic re-execution in .venv
│
├── agent/                    # Agent system
│   ├── base.py               # BaseAgent (abstract class)
│   ├── recursive.py          # RecursiveAgent (with parallel sub-agents)
│   ├── profile.py            # AgentProfile + AgentPermissions
│   ├── context.py            # AgentContext (prompt construction, write_confirmation)
│   └── status.py             # ToolStatus + display formatters
│
├── config/                   # Configuration
│   ├── loader.py             # File discovery (ConfigPaths)
│   ├── settings.py           # Settings (dataclass)
│   └── providers.py          # ProviderConfig + ProviderRegistry + merge
│
├── interfaces/               # User interfaces
│   ├── cli_interface.py      # Interactive CLI (Rich + readline + write confirmation)
│   ├── commands.py           # Slash command handlers
│   └── telegram_interface.py # Telegram bot (per user)
│
├── setup/                    # Configuration wizards
│   ├── provider_wizard.py    # Provider configuration
│   ├── telegram_wizard.py    # Telegram bot configuration
│   └── agent_wizard.py       # Per-agent model assignment
│
├── content/                  # Content catalog system
│   ├── scanner.py            # File scanning and metadata extraction
│   ├── catalog.py            # Persistent content index (.flavia/content_catalog.json)
│   ├── summarizer.py         # LLM summarization for files/directories
│   └── converters/           # Document conversion (PDF -> text/markdown)
│
├── tools/                    # Tool system
│   ├── base.py               # BaseTool (abstract class) + ToolSchema
│   ├── registry.py           # ToolRegistry (singleton)
│   ├── permissions.py        # Access permission checking (read + write)
│   ├── write_confirmation.py # WriteConfirmation callback mechanism
│   ├── backup.py             # FileBackup (timestamped backups in .flavia/file_backups/)
│   ├── read/                 # Read tools
│   │   ├── read_file.py
│   │   ├── list_files.py
│   │   ├── search_files.py
│   │   └── get_file_info.py
│   ├── write/                # Write tools (permission + confirmation enforced)
│   │   ├── write_file.py
│   │   ├── edit_file.py
│   │   ├── insert_text.py
│   │   ├── append_file.py
│   │   ├── delete_file.py
│   │   ├── create_directory.py
│   │   └── remove_directory.py
│   ├── spawn/                # Agent creation tools
│   │   ├── spawn_agent.py
│   │   └── spawn_predefined_agent.py
│   ├── content/              # Catalog query/update tools
│   │   ├── query_catalog.py
│   │   ├── get_summary.py
│   │   └── refresh_catalog.py
│   ├── academic/             # Academic workflow tools
│   │   └── compile_latex.py
│   ├── compact/              # Context management tools
│   │   └── compact_context.py
│   └── setup/                # --init exclusive tools
│       ├── convert_pdfs.py   # Conversion via pdfplumber
│       └── create_agents_config.py
│
└── defaults/                 # Package default configurations
    ├── models.yaml
    └── providers.yaml
```

## Agent system

### BaseAgent

Abstract class that defines the agent interface: receives a message, interacts with the LLM (via OpenAI SDK), executes tools, and returns a response.

### RecursiveAgent

Concrete implementation supporting recursion and parallelism:

- Maintains conversation history
- Executes tools called by the LLM
- Can spawn sub-agents in parallel (via `ThreadPoolExecutor`)
- Respects depth limits (`max_depth`) and parallel workers

### Spawn protocol

When a spawn tool is called, it returns a special payload:

- `__SPAWN_AGENT__:{json}` -- for dynamic agents
- `__SPAWN_PREDEFINED__:{json}` -- for sub-agents from `agents.yaml`
- `__COMPACT_CONTEXT__` (optionally with `:{instructions}`) -- for context compaction

The `RecursiveAgent` intercepts these payloads, creates the sub-agent, and executes it in parallel when possible. For compaction sentinels, it calls `compact_conversation()` with the optional instructions.

### AgentProfile

Contains the agent's static configuration:
- Context (system prompt)
- Model
- Enabled tools
- Defined sub-agents
- Access permissions
- Maximum depth

### AgentContext

Manages runtime state:
- System prompt construction
- Variable substitution (such as `{base_dir}`)
- Runtime `setup_mode` attribute used to enable wizard-exclusive tools

## Tool system

### ToolRegistry

Singleton that maintains the registry of all tools. Read/spawn/content tools are automatically registered on import of the `flavia.tools` module, while setup-only tools are registered manually by the setup wizard.

### BaseTool

Abstract class for tools. Each tool defines:
- Name and description
- Category (`read`, `write`, `spawn`, `content`, `academic`, `compact`, `setup`)
- Parameter schema (compatible with OpenAI function calling)
- Execution method

### Permissions

The `permissions.py` module checks whether an agent has read or write access to a path, based on the permissions defined in the `AgentProfile`.

### Write confirmation

Write tools require explicit user confirmation before execution. The `WriteConfirmation` class (in `tools/write_confirmation.py`) delegates to a callback registered by the interface:
- **CLI**: prompts `[y/N]` with temporary terminal restore (agent runs in a background thread with suppressed input)
- **Telegram**: no callback registered, so write operations are denied by default (fail-safe)
- **Testing**: auto-approve mode bypasses the prompt

Before destructive file write operations, the `FileBackup` class (in `tools/backup.py`) saves a timestamped copy to `.flavia/file_backups/`.

## Content Catalog

The content catalog indexes project files and stores metadata (type, timestamps, checksum, optional converted/summarized artifacts) in `.flavia/content_catalog.json`.

- Built during setup (`flavia --init`)
- Updated incrementally via CLI (`--update`, `--update-convert`, `--update-summarize`)
- Queried at runtime through tools (`query_catalog`, `get_catalog_summary`, `refresh_catalog`)
- Injected into the top-level system prompt as compact project context

## Configuration system

### ConfigPaths

Configuration directory discovery across the hierarchy:
1. `.flavia/` in the current directory
2. `~/.config/flavia/`
3. Packaged defaults

### Provider merge

When multiple `providers.yaml` files exist in the hierarchy, they are merged: local configurations override higher-level ones. Environment variables with `${VAR}` syntax are expanded at load time.

### Settings

Central dataclass that aggregates:
- Default model
- API URL
- API key
- Provider configuration (ProviderRegistry)
- Agent configuration
- Limits (depth, parallel workers)
- Flags (verbose, subagents_enabled, active_agent)

## Interfaces

### CLI

Interactive interface based on Rich:
- Markdown formatting
- Command history via readline
- Loading animations during LLM calls
- Real-time tool status updates (`ToolStatus` callbacks from agents)
- Conversation logging
- Slash commands (`/help`, `/reset`, `/agent_setup`, `/agent`, etc.)

### Telegram

Bot based on `python-telegram-bot`:
- One agent instance per user
- Access control by user ID
- Same agent and provider configuration from the directory where it was started
