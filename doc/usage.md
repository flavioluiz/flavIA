# Usage

## Interactive CLI

The default mode is the interactive CLI, started with:

```bash
flavia
```

The interface uses [Rich](https://github.com/Textualize/rich) for formatting, with command history (readline) and loading animations.

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
| `/help` | Show help |
| `/reset` | Reset conversation and reload configuration |
| `/setup` | Reconfigure agents (re-analyze content) |
| `/agents` | Configure model per agent/sub-agent |
| `/agent` | List available agents with configurations |
| `/agent <name>` | Switch to a different agent (resets conversation) |
| `/catalog` | Browse content catalog (overview, search, summaries, online sources) |
| `/providers` | List configured providers with indexed models |
| `/tools` | List available tools by category |
| `/tools <name>` | Show tool schema and parameters |
| `/config` | Show configuration paths and active settings |
| `/quit` | Exit session (aliases: `/exit`, `/q`) |

## `/catalog` quick workflow

Inside the interactive CLI:

1. Run `/catalog`.
2. Use the menu:
   - `1` overview/statistics
   - `2` directory tree
   - `3` search
   - `4` summaries
   - `5` list online sources
   - `6` add online source URL
3. Press `q` to return to chat.

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
