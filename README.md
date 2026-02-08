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
git clone https://github.com/flavioribeiro/flavia.git
cd flavia

# Install (creates 'flavia' command)
pip install -e .

# With Telegram support
pip install -e ".[telegram]"

# With OCR support (for scanned documents, handwriting)
pip install -e ".[ocr]"

# Everything
pip install -e ".[all]"
```

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
flavia -v              # Verbose mode
flavia --model 0       # Use specific model
flavia --list-models   # Show available models
flavia --list-tools    # Show available tools
flavia --config        # Show configuration paths
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

### Directory Structure

```
.flavia/
├── .env           # API keys (don't commit!)
├── models.yaml    # Available models
└── agents.yaml    # Agent configuration
```

### Environment Variables (`.flavia/.env`)

```bash
# Required
SYNTHETIC_API_KEY=your_api_key_here

# Optional
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

- **OCR Support**: Read scanned documents, handwritten notes, equations
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
