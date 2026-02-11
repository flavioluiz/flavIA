# Usage

## Interactive CLI

The default mode is the interactive CLI, started with:

```bash
flavia
```

The interface uses [Rich](https://github.com/Textualize/rich) for formatting, with command history (readline) and loading animations.

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
| `--update-convert` | Refresh catalog and convert pending/modified binary documents (PDFs) |
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
| `/agent_setup` | Configure agents (quick model change, revise, or full rebuild) |
| `/agent` | Open interactive agent selection (fallback: list available agents) |
| `/agent <name>` | Switch to a different agent (resets conversation) |
| `/model` | Show the current active model |
| `/model <ref>` | Switch model by index, model ID, or `provider:model_id` (resets conversation) |
| `/model list` | Quick alias for `/providers` |
| `/catalog` | Browse content catalog (overview, search, summaries, online sources) |
| `/providers` | List configured providers with indexed models |
| `/provider-setup` | Run interactive provider configuration wizard |
| `/provider-manage [id]` | Manage provider models and settings |
| `/provider-test [id]` | Test connection to a provider |
| `/tools` | List available tools by category |
| `/tools <name>` | Show tool schema and parameters |
| `/config` | Show configuration paths and active settings |
| `/quit` | Exit session (aliases: `/exit`, `/q`) |

### Help System Details

The unified help system organizes commands into logical categories:

- **Session**: `/quit`, `/reset`
- **Agents**: `/agent`, `/agent_setup`
- **Models & Providers**: `/model`, `/providers`, `/provider-setup`, `/provider-manage`, `/provider-test`
- **Information**: `/tools`, `/config`, `/catalog`, `/help`

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
- Online source converters are currently placeholders (URLs are cataloged, but content fetching/conversion is not implemented yet).
- Online sources are persisted in `.flavia/content_catalog.json`.

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

# Show all configuration details
flavia --config
```
