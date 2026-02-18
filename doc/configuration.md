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
  converted_access_mode: "hybrid"  # strict | hybrid | open
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
    - compile_latex
    - spawn_agent
    - spawn_predefined_agent

  latex:
    compiler: "pdflatex"       # pdflatex | xelatex | lualatex | latexmk
    passes: 2                  # 1..5
    bibtex: true               # run bibtex/biber when bibliography is detected
    clean_aux: true            # remove .aux/.log/.toc/... after successful compile
    shell_escape: false        # secure default; enable only if document requires it
    continue_on_error: true    # continue passes and collect errors/logs automatically

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

`converted_access_mode` controls direct access to `.converted/` files for read tools (`read_file`, `search_files`, `list_files`, `get_file_info`, `analyze_image`):
- `strict`: block direct `.converted/` reads; use `search_chunks` (RAG-only).
- `hybrid` (default): require a `search_chunks` call first, then allow direct fallback reads.
- `open`: always allow direct `.converted/` reads.

`search_chunks` also supports `@arquivo` mentions in the query for explicit file scoping (by original catalog file names/paths, e.g., `@relatorio.pdf`). Mentioned originals are mapped to their indexed converted content automatically.

Legacy key (still accepted): `allow_converted_read: true|false` maps to `open|strict`.

### Available tools

| Tool | Category | Description |
|------|----------|-------------|
| `read_file` | read | Read file contents |
| `list_files` | read | List directory contents |
| `search_files` | read | Search for patterns in files |
| `get_file_info` | read | Get file metadata |
| `query_catalog` | content | Query indexed files by filters (name, type, extension, summary text) |
| `get_catalog_summary` | content | Retrieve a high-level project/content catalog summary |
| `refresh_catalog` | content | Rescan project files and update the content catalog |
| `search_chunks` | content | Hybrid semantic retrieval (vector + FTS) over indexed chunks with citations; supports `@arquivo` scoping and `retrieval_mode=exhaustive` |
| `analyze_image` | content | Analyze an image with a vision-capable model and return a detailed description |
| `compile_latex` | academic | Compile `.tex` into PDF with log parsing and configurable passes |
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

`compile_latex` is non-interactive: it never asks for user confirmation. It returns compilation status plus parsed errors/warnings for the agent to handle automatically.

### LaTeX tool settings (`agents.yaml`)

Per-agent LaTeX defaults live under `latex:`:

```yaml
main:
  tools:
    - compile_latex
  latex:
    compiler: "pdflatex"
    passes: 2
    bibtex: true
    clean_aux: true
    shell_escape: false
    continue_on_error: true
```

Notes:
- `continue_on_error: true` keeps compiling and aggregates issues from log/output so the agent can fix and retry.
- `continue_on_error: false` uses halt-on-error behavior (stop at first LaTeX error in that run).
- `shell_escape` is disabled by default for safety.

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
- **Fail-safe explicit config**: an empty `permissions` block (`permissions: {}`) means no read/write paths are allowed
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
MISTRAL_API_KEY=your_mistral_key   # optional, for PDF OCR and audio/video transcription features
SUMMARY_MODEL=synthetic:hf:moonshotai/Kimi-K2-Instruct-0905  # optional, overrides only catalog summary/quality model
IMAGE_VISION_MODEL=synthetic:hf:moonshotai/Kimi-K2.5  # optional, overrides model used for image analysis and video frame descriptions

# Legacy single-provider config (still works)
API_BASE_URL=https://api.synthetic.new/openai/v1
DEFAULT_MODEL=synthetic:hf:moonshotai/Kimi-K2.5
AGENT_MAX_DEPTH=3
AGENT_PARALLEL_WORKERS=4
AGENT_COMPACT_THRESHOLD=0.9

# RAG diagnostics and tuning (optional)
RAG_DEBUG=false
RAG_CATALOG_ROUTER_K=20
RAG_VECTOR_K=15
RAG_FTS_K=15
RAG_RRF_K=60
RAG_MAX_CHUNKS_PER_DOC=3
RAG_CHUNK_MIN_TOKENS=300
RAG_CHUNK_MAX_TOKENS=800
RAG_VIDEO_WINDOW_SECONDS=60
RAG_EXPAND_VIDEO_TEMPORAL=true

# CLI status panel limits (-1 = unlimited)
STATUS_MAX_TASKS_MAIN=5
STATUS_MAX_TASKS_SUBAGENT=3

# Runtime limits and display settings
MAX_ITERATIONS=20
LLM_REQUEST_TIMEOUT=600
LLM_CONNECT_TIMEOUT=10
IMAGE_MAX_SIZE_MB=20
SUMMARY_MAX_LENGTH=3000
SHOW_TOKEN_USAGE=true
COLOR_THEME=default
TIMESTAMP_FORMAT=iso
LOG_LEVEL=warning
OCR_MIN_CHARS_PER_PAGE=50
TRANSCRIPTION_TIMEOUT=600
EMBEDDER_BATCH_SIZE=64
LATEX_TIMEOUT=120

# Telegram (optional)
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_ALLOWED_USER_IDS=123456789,987654321
TELEGRAM_ALLOW_ALL_USERS=true
```

`RAG_DEBUG=true` enables retrieval diagnostics capture (equivalent to runtime `/rag-debug on`).
Captured traces are persisted to `.flavia/rag_debug.jsonl` and can be inspected with `/rag-debug last` (global) or `/rag-debug turn` (current turn only).

Most of these values can also be edited interactively inside the CLI with `/settings`.

## Connection test

```bash
flavia --test-provider           # test default provider
flavia --test-provider openai    # test specific provider
```
