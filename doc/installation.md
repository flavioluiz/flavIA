# Installation

## Requirements

- Python >= 3.10
- Git

## Standard installation

```bash
git clone https://github.com/flavioluiz/flavIA.git
cd flavIA
./install.sh
```

The `install.sh` script creates an isolated virtualenv at `.venv/`, installs locked dependencies (`requirements.lock`), and installs flavIA itself in editable mode.

After installation:

```bash
.venv/bin/flavia --version
```

## Manual installation (alternative)

If you prefer to install manually:

```bash
git clone https://github.com/flavioluiz/flavIA.git
cd flavIA
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/pip install --no-deps -e .
```

## Automatic venv re-execution

`flavia` automatically detects the project venv and re-executes inside it. This means that even if invoked outside the venv, it re-launches in the correct environment.

To disable this behavior (useful for debugging):

```bash
export FLAVIA_DISABLE_AUTO_VENV=1
```

## Telegram (optional)

To use the Telegram interface, install the extra dependency:

```bash
.venv/bin/pip install python-telegram-bot==22.6
```

Or install with the extra:

```bash
.venv/bin/pip install -e ".[telegram]"
```

## Development dependencies

```bash
.venv/bin/pip install -e ".[dev]"
pytest
black src/
ruff check src/
```

## First use

After installation, go to a folder with your materials and initialize:

```bash
cd ~/research/my-topic
flavia --init
```

The interactive wizard will:

1. Ask which model/provider to use (and test the connection)
2. Find PDFs and offer to convert them to text
3. Analyze the content with AI and create specialized agents (with iterative revision)
4. Generate the configuration in `.flavia/`

If no API key is configured, the wizard creates a basic template. Edit `.flavia/.env` with your key and start:

```bash
nano .flavia/.env    # add your API key
flavia               # start chatting
```

If you run `flavia` in an interactive terminal without any existing local or user configuration and without an API key, the setup wizard is offered automatically.
