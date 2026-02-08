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
# 1. Find PDFs and offer to convert them
# 2. Analyze the content (if API key is already configured)
# 3. Create a specialized agent
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
flavia --list-models         # Show available models
flavia --list-providers      # Show configured providers
flavia --list-tools          # Show available tools
flavia --config              # Show configuration paths

# Provider management
flavia --setup-provider      # Interactive provider wizard
flavia --test-provider       # Test default provider connection
flavia --test-provider openai  # Test specific provider
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `/help` | Show help |
| `/reset` | Reset conversation and reload config |
| `/setup` | Reconfigure agents (re-analyze content) |
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
    ├── models.yaml
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

### Directory Structure

```
.flavia/
├── .env            # API keys (don't commit!)
├── models.yaml     # Available models (legacy)
├── providers.yaml  # Multi-provider configuration (new)
└── agents.yaml     # Agent configuration
```

### Multi-Provider Configuration

flavIA supports multiple LLM providers. Use the interactive wizard:

```bash
flavia --setup-provider
```

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
DEFAULT_MODEL=hf:moonshotai/Kimi-K2.5
AGENT_MAX_DEPTH=3

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
