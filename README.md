# flavIA

**Intelligent academic assistant** -- turn any working folder into an environment with AI agents ready to understand your documents, answer questions, generate ideas, and help with your research or study workflow.

The core idea: you have a folder with PDFs, code, notes, or any working material. With a single command, flavIA analyzes the content, creates specialized agents, and is ready to chat -- via terminal or Telegram.

```bash
# In any folder with your materials
cd ~/research/quantum-mechanics

# Initialize: converts PDFs, analyzes content, creates specialized agents
flavia --init

# Chat in the terminal
flavia
> What are the main interpretations of quantum mechanics discussed in these papers?

# Or via Telegram, from anywhere
flavia --telegram
```

## What flavIA does

- **Understands your documents**: converts PDFs to searchable text and analyzes content to create agents specialized in the subject matter
- **Contextual conversation**: answers questions, explains concepts, finds citations, compares arguments -- all grounded in your materials
- **Works in any folder**: each directory can have its own configuration with agents adapted to its content
- **Multiple interfaces**: chat via terminal (interactive CLI) or set up a Telegram bot for access from anywhere
- **Recursive agents**: the main agent can delegate tasks to specialized sub-agents (summarizer, explainer, researcher)
- **Multi-provider**: use OpenAI, OpenRouter, Anthropic, Synthetic, or any OpenAI-compatible API

## Coming soon

- Course material generation (summaries, exercise lists, flashcards)
- Programming prototype development assistance
- OCR support for scanned documents
- Automatic citation and bibliography extraction

## Quick install

```bash
git clone https://github.com/flavioluiz/flavIA.git
cd flavIA
./install.sh            # creates isolated venv with locked dependencies
.venv/bin/flavia --version
```

Details in [doc/installation.md](doc/installation.md).

## Getting started

```bash
cd ~/folder-with-your-materials
flavia --init    # interactive wizard: picks model, converts PDFs, creates agents
flavia           # start chatting
```

The wizard guides you through each step: model/provider selection, connection test, PDF conversion, and AI-assisted agent configuration generation.

## Documentation

| Document | Contents |
|----------|----------|
| [Installation](doc/installation.md) | Requirements, installation, venv, first use |
| [Usage](doc/usage.md) | CLI, flags, interactive commands, examples |
| [Configuration](doc/configuration.md) | Providers, agents, permissions, environment variables |
| [Telegram](doc/telegram.md) | Telegram bot setup and usage |
| [Architecture](doc/architecture.md) | Project structure, agent system, and tools |
| [Use cases](doc/use-cases.md) | Practical examples for different contexts |

## License

MIT
