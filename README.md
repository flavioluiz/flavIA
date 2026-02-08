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
flavia --model 0             # Use specific model
flavia --list-models         # Show available models
flavia --list-tools          # Show available tools
flavia --config              # Show configuration paths
flavia --configure-provider  # Interactive provider setup wizard
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `/help` | Show help |
| `/reset` | Reset conversation and reload config |
| `/setup` | Reconfigure agents (re-analyze content) |
| `/quit` | Exit |
| `/models` | List available models |
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

### LLM Provider Configuration

flavIA supports multiple LLM providers, allowing you to use different models and services. Providers can be configured globally or per-project.

#### Using the Provider Configuration Wizard

The easiest way to configure providers is using the interactive wizard:

```bash
flavia --configure-provider
```

This wizard will guide you through:
1. Choosing where to save the configuration (local project or global)
2. Adding known providers (Synthetic.new, OpenAI, OpenRouter)
3. Adding custom providers
4. Selecting models for each provider
5. Configuring API keys

#### Provider Configuration File (`providers.yaml`)

You can also manually create or edit the `providers.yaml` file:

```yaml
# providers.yaml - LLM Provider Configurations
providers:
  # Free hosted models via Synthetic.new
  - name: synthetic
    endpoint: https://api.synthetic.new/openai/v1
    api_key_env: SYNTHETIC_API_KEY  # Read from environment variable
    models:
      - id: "hf:moonshotai/Kimi-K2.5"
        name: "Kimi-K2.5"
        description: "Moonshot AI Kimi K2.5"
        max_tokens: 8192
        default: true

      - id: "hf:zai-org/GLM-4.7"
        name: "GLM-4.7"
        description: "Zhipu AI GLM-4.7"
        max_tokens: 8192

  # OpenAI (commercial provider)
  - name: openai
    endpoint: https://api.openai.com/v1
    api_key_env: OPENAI_API_KEY
    models:
      - id: "gpt-4o"
        name: "GPT-4o"
        description: "OpenAI GPT-4o"
        max_tokens: 128000

      - id: "gpt-4o-mini"
        name: "GPT-4o-mini"
        description: "Faster and cheaper"
        max_tokens: 128000

  # OpenRouter (multi-provider aggregator)
  - name: openrouter
    endpoint: https://openrouter.ai/api/v1
    api_key_env: OPENROUTER_API_KEY
    models:
      - id: "anthropic/claude-3.5-sonnet"
        name: "Claude 3.5 Sonnet"
        max_tokens: 200000

      - id: "google/gemini-pro-1.5"
        name: "Gemini Pro 1.5"
        max_tokens: 1000000
```

#### Provider Configuration Options

Each provider can specify:

- **`name`** (required): Unique identifier for the provider
- **`endpoint`** (required): Base API URL endpoint
- **`api_key`** (optional): Direct API key value (not recommended - use `api_key_env` instead)
- **`api_key_env`** (optional): Name of environment variable containing the API key
- **`models`** (optional): List of models provided by this provider
  - **`id`** (required): Model identifier
  - **`name`** (optional): Human-readable model name
  - **`description`** (optional): Model description
  - **`max_tokens`** (optional): Maximum token limit
  - **`default`** (optional): Whether this is the default model (one per provider)

#### API Key Configuration

You can configure API keys in two ways:

**1. Environment Variables (Recommended)**

Set the API key in your `.flavia/.env` file or shell environment:

```bash
# .flavia/.env
SYNTHETIC_API_KEY=your_synthetic_key_here
OPENAI_API_KEY=sk-your_openai_key_here
OPENROUTER_API_KEY=sk-or-v1-your_key_here
```

**2. Direct Value (Less Secure)**

Store the key directly in `providers.yaml` (not recommended for shared configs):

```yaml
providers:
  - name: openai
    endpoint: https://api.openai.com/v1
    api_key: "sk-your_key_here"  # Not recommended
```

#### Provider Configuration Locations

Provider configurations are loaded with the following priority:

1. **Local** (highest priority): `.flavia/providers.yaml` in your current project
2. **Global**: `~/.config/flavia/providers.yaml` for all projects
3. **Package defaults** (lowest priority): Built-in default configurations

This allows you to:
- Use different providers for different projects (local configuration)
- Set up default providers for all projects (global configuration)
- Start with sensible defaults (package defaults)

#### Example: Using Different Providers per Project

**Research Project A** (uses free Synthetic.new models):
```bash
cd ~/research/project-a
flavia --configure-provider  # Choose local, add synthetic provider
flavia  # Uses Synthetic.new models
```

**Production Project B** (uses OpenAI GPT-4):
```bash
cd ~/work/project-b
flavia --configure-provider  # Choose local, add openai provider
flavia  # Uses OpenAI models
```

**Global Default** (fallback for all other projects):
```bash
flavia --configure-provider  # Choose global
# Configures providers available to all projects by default
```

### Directory Structure

```
.flavia/
├── .env              # API keys (don't commit!)
├── providers.yaml    # Provider configurations (local)
├── models.yaml       # Available models
└── agents.yaml       # Agent configuration
```

### Environment Variables (`.flavia/.env`)

```bash
# Required (if not using providers.yaml)
SYNTHETIC_API_KEY=your_api_key_here

# Optional - Provider API keys (when using providers.yaml)
OPENAI_API_KEY=sk-your_openai_key
OPENROUTER_API_KEY=sk-or-v1-your_key

# Legacy settings (used as fallback if no provider matches)
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

Provider configurations are loaded in this order (highest to lowest):

1. `.flavia/providers.yaml` in current directory
2. `~/.config/flavia/providers.yaml` (user defaults)
3. Package default providers
4. Legacy environment variables (`SYNTHETIC_API_KEY`, `API_BASE_URL`)

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
        ├── config/             # Configuration loader
        ├── agent/              # Agent implementation
        ├── tools/
        │   ├── read/           # File reading tools
        │   ├── spawn/          # Agent spawning tools
        │   └── setup/          # Setup-only tools (PDF conversion)
        ├── interfaces/         # CLI and Telegram
        └── defaults/           # Default configs
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
