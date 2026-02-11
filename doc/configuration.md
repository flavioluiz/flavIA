# Configuration

## Overview

flavIA uses a configuration hierarchy with three priority levels:

1. `.flavia/` in the current directory (highest priority)
2. `~/.config/flavia/` (user defaults)
3. Package defaults (lowest priority)

For `providers.yaml`, higher-priority files can override both provider definitions and `default_provider`.

Important `.env` behavior:
- flavIA loads only one `.env` file, using the same priority (`.flavia/.env` first, then `~/.config/flavia/.env`)
- `.env` files are not merged across levels

## `.flavia/` directory structure

```
.flavia/
├── .env                       # API keys (don't commit!)
├── .gitignore                 # Ignores .env, cache, and file_backups/
├── .connection_checks.yaml    # Startup connection check cache
├── providers.yaml             # Provider and model configuration
├── agents.yaml                # Agent configuration
└── file_backups/              # Automatic backups before write operations
```

## Providers

flavIA supports multiple LLM providers. The default includes Synthetic as the provider and `hf:moonshotai/Kimi-K2.5` as the default model.

### Interactive wizard

```bash
flavia --setup-provider
```

The wizard allows you to:
- Fetch models automatically from the provider API (when available)
- Add models manually
- Select which models to enable
- Redirect to provider management when selecting a provider that is already configured

### Model management

```bash
flavia --manage-provider          # select provider interactively
flavia --manage-provider openai   # manage specific provider
```

Management menu:
- **[a] Add model** -- add a model manually
- **[f] Fetch models** -- fetch models from the provider API
- **[r] Remove model(s)** -- remove models
- **[d] Set default** -- change the default model
- **[n] Change display name** -- update provider display name
- **[i] Change provider ID** -- rename provider identifier
- **[u] Change API base URL** -- update endpoint URL
- **[k] Change API key** -- update key source/value
- **[h] Change headers** -- add/edit/remove custom headers
- **[x] Delete provider** -- remove the provider entry from config
- **[s] Save** -- save changes
- **[q] Quit** -- exit without saving

### Manual configuration (`providers.yaml`)

```yaml
providers:
  synthetic:
    name: "Synthetic"
    api_base_url: "https://api.synthetic.new/openai/v1"
    api_key: "${SYNTHETIC_API_KEY}"
    models:
      - id: "hf:moonshotai/Kimi-K2.5"
        name: "Kimi-K2.5"
        default: true

  openai:
    name: "OpenAI"
    api_base_url: "https://api.openai.com/v1"
    api_key: "${OPENAI_API_KEY}"
    models:
      - id: "gpt-4o"
        name: "GPT-4o"

  openrouter:
    name: "OpenRouter"
    api_base_url: "https://openrouter.ai/api/v1"
    api_key: "${OPENROUTER_API_KEY}"
    headers:
      HTTP-Referer: "${OPENROUTER_SITE_URL}"
      X-Title: "${OPENROUTER_APP_NAME}"
    models:
      - id: "anthropic/claude-3.5-sonnet"
        name: "Claude 3.5 Sonnet"

default_provider: synthetic
```

API keys are referenced with `${ENV_VAR}` syntax, resolved from the active `.env` file (highest priority) or system environment variables.

### Command-line model selection

```bash
flavia -m openai:gpt-4o
flavia -m openrouter:anthropic/claude-3.5-sonnet
flavia -m 0     # by index (order from --list-providers)
```

## Agents

Agent configuration lives in `agents.yaml`. It can be generated automatically by the wizard (`flavia --init`) or edited manually.

### `agents.yaml` structure

```yaml
main:
  model: "synthetic:hf:moonshotai/Kimi-K2.5"
  context: |
    You are a research assistant specializing in machine learning and NLP.
    The documents cover transformer architectures, attention mechanisms,
    and large language models.
    Working directory: {base_dir}

  tools:
    - read_file
    - list_files
    - search_files
    - get_file_info
    - spawn_agent
    - spawn_predefined_agent

  subagents:
    summarizer:
      model: "synthetic:hf:moonshotai/Kimi-K2.5"
      context: Summarize papers and sections concisely
      tools: [read_file]

    explainer:
      model: "synthetic:hf:moonshotai/Kimi-K2.5"
      context: Explain complex ML concepts in simple terms
      tools: [read_file, search_files]

    researcher:
      model: "synthetic:hf:moonshotai/Kimi-K2.5"
      context: Find information, citations, and references in documents
      tools: [read_file, list_files, search_files]
```

The `{base_dir}` placeholder in the context is replaced with the base directory at runtime.

### Available tools

| Tool | Category | Description |
|------|----------|-------------|
| `read_file` | read | Read file contents |
| `list_files` | read | List directory contents |
| `search_files` | read | Search for patterns in files |
| `get_file_info` | read | Get file metadata |
| `write_file` | write | Create or overwrite a file |
| `edit_file` | write | Replace exact text in a file (single match required) |
| `insert_text` | write | Insert text at a specific line number |
| `append_file` | write | Append content to a file |
| `delete_file` | write | Delete a file (with automatic backup) |
| `create_directory` | write | Create a directory |
| `remove_directory` | write | Remove a directory |
| `spawn_agent` | spawn | Create dynamic sub-agents |
| `spawn_predefined_agent` | spawn | Invoke predefined sub-agents from `agents.yaml` |
| `convert_pdfs` | setup | Convert PDFs to markdown (only available during `--init`) |
| `create_agents_config` | setup | Create `agents.yaml` (only available during `--init`) |

All write tools enforce `AgentPermissions.write_paths` and require user confirmation in the CLI. Write operations are denied in Telegram (no confirmation handler).

### Per-agent model configuration

Inside the CLI:
- `/agent_setup` (Quick mode) allows assigning different models to each agent and sub-agent.
- `/agent` opens interactive agent selection (or lists available agents in fallback mode).
- `/agent <name>` switches the active agent at runtime (conversation is reset).

From the command line:

```bash
flavia --agent summarizer    # promote sub-agent as main
```

## Permissions

Control which directories agents can read from and write to.

### Default behavior

If the `permissions` block is not specified (or is empty), the agent has full read/write access to `base_dir`.

### Granular configuration

```yaml
main:
  context: |
    You are a research assistant...

  permissions:
    read:
      - "."                    # relative to base_dir
      - "./docs"
      - "/etc/configs"         # absolute paths (outside project)
    write:
      - "./output"             # write also grants read
      - "./generated"

  tools:
    - read_file
    - list_files
    - search_files
    - spawn_predefined_agent

  subagents:
    researcher:
      context: Research and analyze documents
      # Inherits permissions from parent if not specified
      tools:
        - read_file
        - search_files

    writer:
      context: Generate output files
      # Override with specific permissions
      permissions:
        read:
          - "./sources"
        write:
          - "./drafts"
      tools:
        - read_file
        - write_file
        - edit_file
        - append_file
```

### Permission rules

- **Default**: without a `permissions` block, full access to `base_dir`
- **Backward compatibility**: an empty `permissions` block (`permissions: {}`) also falls back to full `base_dir` access
- **Inheritance**: sub-agents inherit parent permissions unless they specify their own
- **Dynamic sub-agents**: agents created with `spawn_agent` inherit the current agent's permissions
- **Write implies read**: write permission automatically grants read access to the same path
- **Paths**: accepts both relative (to `base_dir`) and absolute paths

## Environment variables (`.flavia/.env`)

```bash
# Provider API keys (referenced in providers.yaml)
SYNTHETIC_API_KEY=your_key_here
OPENAI_API_KEY=your_openai_key
OPENROUTER_API_KEY=your_openrouter_key

# Legacy single-provider config (still works)
API_BASE_URL=https://api.synthetic.new/openai/v1
DEFAULT_MODEL=synthetic:hf:moonshotai/Kimi-K2.5
AGENT_MAX_DEPTH=3
AGENT_PARALLEL_WORKERS=4

# Telegram (optional)
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_ALLOWED_USER_IDS=123456789,987654321
TELEGRAM_ALLOW_ALL_USERS=true
```

## Connection test

```bash
flavia --test-provider           # test default provider
flavia --test-provider openai    # test specific provider
```
