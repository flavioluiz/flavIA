# flavIA

**AI-powered academic research assistant** with PDF support, recursive agents, and multiple interfaces.

Transform a folder of PDFs into an intelligent research companion that understands your documents, answers questions, and helps you study.

## The Idea

```bash
# 1. Create a folder with your PDFs
mkdir quantum-mechanics && cd quantum-mechanics
cp ~/Downloads/*.pdf .

# 2. Initialize flavIA
flavia --init
# → Converts PDFs to text
# → Analyzes content
# → Creates specialized agent for quantum mechanics

# 3. Start chatting with your documents
flavia
You: What are the main interpretations of quantum mechanics discussed in these papers?
Agent: Based on the documents, there are three main interpretations discussed...

# 4. (Optional) Make it a Telegram bot to study on the go
flavia --telegram
```

## Features

- **PDF to Text Conversion**: Automatically converts PDFs to searchable markdown
- **AI-Assisted Setup**: Analyzes your content and creates specialized agents
- **Multi-Provider Support**: Use OpenAI, OpenRouter, Anthropic, or any OpenAI-compatible API
- **Academic Focus**: Built-in support for summarizing, explaining, finding citations
- **Recursive Agents**: Spawn specialist sub-agents for complex tasks
- **Works Anywhere**: Each folder can have its own configuration
- **Telegram Bot**: Turn your research assistant into a mobile chatbot

## Installation

```bash
# Clone the repository
git clone https://github.com/flavioluiz/flavIA.git
cd flavIA

# Recommended: isolated local venv + locked dependencies
./install.sh

# Then run from the dedicated venv
.venv/bin/flavia --version
```

`flavia` also auto-reexecs into the project `.venv` when available.
To disable this behavior (for debugging), set `FLAVIA_DISABLE_AUTO_VENV=1`.

## Quick Start

```bash
# Go to your research folder
cd ~/research/machine-learning-papers

# Initialize - flavIA will:
# 1. Ask which model/provider to use in the initial setup
# 2. Try a connection test for the selected model/provider
# 3. Find PDFs and offer to convert them
# 4. Analyze the content (if API key is already configured)
# 5. Create a specialized agent
flavia --init
```

The setup wizard will ask:

```
┌─────────────────────────────────────────────────────┐
│         flavIA Setup Wizard                         │
│         AI assistant for academic work              │
│                                                     │
│  Initializing in: ~/research/ml-papers              │
└─────────────────────────────────────────────────────┘

Found 12 PDF file(s):
  attention_is_all_you_need.pdf           2.1 MB
  bert_paper.pdf                          1.8 MB
  gpt3_paper.pdf                          3.2 MB
  ...

Use default model/provider? [Y/n]
Connection check...

Convert PDFs to text for analysis? [Y/n]
Have the AI analyze and suggest agent configuration? [Y/n]

Converting PDFs and analyzing content...
```

If no API key is configured yet, setup falls back to a basic config template.
Then edit your API key and start:

```bash
nano .flavia/.env  # Add your API key
flavia             # Start chatting!
```

`flavia --init` now writes the selected model/provider into:
- `.flavia/.env` as `DEFAULT_MODEL=provider:model`
- `.flavia/agents.yaml` as `main.model`

## Usage

```bash
# Interactive CLI
flavia

# Telegram bot mode
flavia --telegram

# Options
flavia -v                    # Verbose mode
flavia --model 0             # Use specific model by index
flavia -m openai:gpt-4o      # Use specific provider:model
flavia --agent summarizer    # Promote a subagent as the main agent
flavia --no-subagents        # Disable sub-agent spawning
flavia --depth 2             # Override max recursion depth
flavia --parallel-workers 8  # Max parallel sub-agents
flavia --list-models         # Show available models
flavia --list-providers      # Show configured providers
flavia --list-tools          # Show available tools
flavia --config              # Show configuration paths

# Provider management
flavia --setup-provider      # Interactive provider wizard
flavia --manage-provider     # Manage models (add/remove/fetch)
flavia --manage-provider openai  # Manage specific provider
flavia --test-provider       # Test default provider connection
flavia --test-provider openai  # Test specific provider

# Telegram setup
flavia --setup-telegram      # Configure Telegram bot token and access
```

When running `flavia` (CLI or Telegram), flavIA validates connectivity for the active default
provider/model at least once and caches the result, so startup checks are not repeated every time.

## CLI Commands

| Command | Description |
|---------|-------------|
| `/help` | Show help |
| `/reset` | Reset conversation and reload config |
| `/setup` | Reconfigure agents (re-analyze content) |
| `/agents` | Configure model per agent/subagent |
| `/quit` | Exit |
| `/models` | List available models with provider info |
| `/providers` | List configured LLM providers |
| `/tools` | List available tools |

## How It Works

### 1. PDF Conversion

When you run `flavia --init` in a folder with PDFs:

```
my-research/
├── paper1.pdf
├── paper2.pdf
└── paper3.pdf
```

Becomes:

```
my-research/
├── paper1.pdf
├── paper2.pdf
├── paper3.pdf
├── converted/           # ← New folder
│   ├── paper1.md
│   ├── paper2.md
│   └── paper3.md
└── .flavia/
    ├── .env
    ├── providers.yaml
    └── agents.yaml      # ← Specialized for your content
```

### 2. Agent Configuration

The AI analyzes your documents and creates a specialized agent:

```yaml
# .flavia/agents.yaml (auto-generated)
main:
  context: |
    You are a research assistant specializing in machine learning and NLP.
    The documents cover transformer architectures, attention mechanisms,
    and large language models.

    Help the user understand concepts, find specific information,
    and analyze arguments across papers.

  tools:
    - read_file
    - list_files
    - search_files
    - spawn_predefined_agent

  subagents:
    summarizer:
      context: Summarize papers and sections concisely
      tools: [read_file]

    explainer:
      context: Explain complex ML concepts in simple terms
      tools: [read_file, search_files]

    citation_finder:
      context: Find relevant quotes and references
      tools: [read_file, search_files]
```

### 3. Chat with Your Documents

```
You: Explain the attention mechanism from the transformer paper

Agent: Based on "Attention Is All You Need" (converted/attention_is_all_you_need.md),
the attention mechanism works as follows...

The key insight is that attention allows the model to...

Would you like me to explain any specific part in more detail?
```

## Configuration

### Agent Permissions

Control which directories agents can read from and write to. By default, agents have full access to their base directory. Use permissions for fine-grained access control:

```yaml
# .flavia/agents.yaml
main:
  context: |
    You are a research assistant...

  # Granular access control
  permissions:
    read:
      - "."                    # Relative to base_dir
      - "./docs"               # Subfolders
      - "/etc/configs"         # Absolute paths (outside project)
    write:
      - "./output"             # Write access (also grants read)
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
```

**Permission Rules:**
- **Default**: If `permissions` is not specified, the agent has full read/write access to `base_dir`
- **Backward compatibility**: An empty `permissions` block (`permissions: {}`) also falls back to full `base_dir` access
- **Inheritance**: Subagents inherit parent permissions unless they specify their own
- **Dynamic subagents**: Agents created with `spawn_agent` inherit the current agent permissions
- **Write implies read**: Write permission automatically grants read access to the same path
- **Paths**: Accept both relative (to base_dir) and absolute paths

### Directory Structure

```
.flavia/
├── .env            # API keys (don't commit!)
├── .connection_checks.yaml  # Startup connectivity check cache
├── providers.yaml  # Provider + models configuration
└── agents.yaml     # Agent configuration
```

### Multi-Provider Configuration

flavIA supports multiple LLM providers. Use the interactive wizard:

```bash
flavia --setup-provider
```

Package defaults include:
- `default_provider: synthetic`
- default model: `synthetic:hf:moonshotai/Kimi-K2.5`

During setup, you can:
- **Fetch models from API**: Some providers (like Synthetic) expose a `/models` endpoint. The wizard can fetch and display available models automatically.
- **Add custom models**: Manually add models by specifying their ID and display name.
- **Select multiple models**: Choose which models to enable for a provider.

### Managing Provider Models

After initial setup, manage models for existing providers:

```bash
flavia --manage-provider          # Select provider interactively
flavia --manage-provider openai   # Manage specific provider
```

The management menu allows you to:
- **[a] Add model** - Add a new model manually
- **[f] Fetch models** - Fetch available models from provider API
- **[r] Remove model(s)** - Remove models by number
- **[d] Set default** - Change the default model
- **[s] Save** - Save changes to config file

Or create `providers.yaml` manually:

```yaml
# .flavia/providers.yaml
providers:
  synthetic:
    name: "Synthetic"
    api_base_url: "https://api.synthetic.new/openai/v1"
    api_key: "${SYNTHETIC_API_KEY}"  # Reference env var
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
    headers:  # Custom headers for OpenRouter
      HTTP-Referer: "${OPENROUTER_SITE_URL}"
      X-Title: "${OPENROUTER_APP_NAME}"
    models:
      - id: "anthropic/claude-3.5-sonnet"
        name: "Claude 3.5 Sonnet"

default_provider: synthetic
```

Use models with `provider:model_id` format:

```bash
flavia -m openai:gpt-4o
flavia -m openrouter:anthropic/claude-3.5-sonnet
```

When providers are enabled, numeric model indexes (for example `flavia -m 0`)
follow the combined order shown by `flavia --list-models`.

### Environment Variables (`.flavia/.env`)

```bash
# Provider API keys (referenced in providers.yaml)
SYNTHETIC_API_KEY=your_api_key_here
OPENAI_API_KEY=your_openai_key
OPENROUTER_API_KEY=your_openrouter_key

# Legacy single-provider config (still works)
API_BASE_URL=https://api.synthetic.new/openai/v1
DEFAULT_MODEL=synthetic:hf:moonshotai/Kimi-K2.5
AGENT_MAX_DEPTH=3
AGENT_PARALLEL_WORKERS=4

# For Telegram bot
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
# Restrict access to specific Telegram users (comma-separated)
TELEGRAM_ALLOWED_USER_IDS=123456789,987654321

# Optional: explicit public mode (no whitelist)
TELEGRAM_ALLOW_ALL_USERS=true
```

### Configuration Priority

1. `.flavia/` in current directory (highest)
2. `~/.config/flavia/` (user defaults)
3. Package defaults (lowest)

For `providers.yaml`, higher-priority files can override both provider definitions
and `default_provider`.

### Telegram Bot Setup

Turn your research assistant into a Telegram bot accessible from anywhere.

**Quick setup:**

```bash
flavia --setup-telegram
```

The wizard will guide you through:

1. **Getting a bot token from @BotFather**
   - Open Telegram and search for `@BotFather`
   - Send `/newbot` and follow the prompts
   - Copy the token (looks like `123456789:ABCdefGHI...`)

2. **Configuring access control**
   - **Restricted** (recommended): Only specific user IDs can use the bot
   - **Public**: Anyone who finds your bot can use it (uses your API credits!)

3. **Finding your user ID**
   - Search for `@userinfobot` on Telegram
   - Send any message to get your user ID

**Manual configuration** (in `.flavia/.env`):

```bash
# Bot token from @BotFather
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHI...

# Option 1: Restrict to specific users (recommended)
TELEGRAM_ALLOWED_USER_IDS=123456789,987654321

# Option 2: Allow anyone (use with caution!)
TELEGRAM_ALLOW_ALL_USERS=true
```

**Starting the bot:**

```bash
flavia --telegram
```

If not configured, you'll be prompted to run the setup wizard.

## Use Cases

### Research Papers
```bash
cd ~/papers/cognitive-science
flavia --init
# Creates agent specialized in cognitive science research
```

### Course Materials
```bash
cd ~/courses/organic-chemistry
flavia --init
# Creates tutor agent for organic chemistry
```

### Legal Documents
```bash
cd ~/cases/contract-dispute
flavia --init
# Creates legal research assistant
```

### Book Analysis
```bash
cd ~/books/philosophy-collection
flavia --init
# Creates philosophy discussion agent
```

## Future Features

- **OCR Support (planned, not yet available)**: Support for scanned documents, handwritten notes, and equations will be added soon
- **Citation Extraction**: Automatic bibliography building
- **Multi-language**: Support for non-English documents
- **Export**: Generate summaries, notes, flashcards

## Project Structure

```
flavia/
├── pyproject.toml
└── src/
    └── flavia/
        ├── cli.py              # Entry point
        ├── setup_wizard.py     # AI-assisted setup + PDF conversion
        ├── config/
        │   ├── loader.py       # Config file discovery
        │   ├── settings.py     # Settings management
        │   └── providers.py    # Multi-provider support
        ├── setup/
        │   └── provider_wizard.py  # Interactive provider setup
        ├── agent/              # Agent implementation
        ├── tools/
        │   ├── read/           # File reading tools
        │   ├── spawn/          # Agent spawning tools
        │   └── setup/          # Setup-only tools (PDF conversion)
        ├── interfaces/         # CLI and Telegram
        └── defaults/
            ├── models.yaml     # Default models
            └── providers.yaml  # Default provider templates
```

## Development

```bash
pip install -e ".[dev]"
pytest
black src/
ruff check src/
```

## License

MIT
