# Telegram

Turn your assistant into a Telegram bot accessible from anywhere.

## Quick setup

```bash
flavia --setup-telegram
```

The wizard guides you through:

1. **Getting a token from @BotFather**
   - Open Telegram and search for `@BotFather`
   - Send `/newbot` and follow the prompts
   - Copy the token (format: `123456789:ABCdefGHI...`)

2. **Configuring access control**
   - **Restricted** (recommended): only specific user IDs can use the bot
   - **Public**: anyone who finds your bot can use it (uses your API credits!)

3. **Finding your user ID**
   - Search for `@userinfobot` on Telegram
   - Send any message to get your ID

## YAML configuration (recommended)

For richer control, use `.flavia/bots.yaml` (created automatically by `--setup-telegram` or `--init`):

```yaml
bots:
  default:
    platform: telegram
    token: "${TELEGRAM_BOT_TOKEN}"   # references .env secret
    default_agent: main
    allowed_agents: all              # or a list: [main, researcher]
    access:
      allowed_users: [123456789]     # restrict to these user IDs
      allow_all: false               # true = public bot
```

The token secret stays in `.env`; structural config lives in `bots.yaml`.

### Multi-bot example

```yaml
bots:
  research-bot:
    platform: telegram
    token: "${RESEARCH_BOT_TOKEN}"
    default_agent: researcher
    allowed_agents: [researcher, summarizer]
    access:
      allowed_users: [111111111, 222222222]
      allow_all: false

   public-bot:
     platform: telegram
     token: "${PUBLIC_BOT_TOKEN}"
     default_agent: main
     allowed_agents: all
     access:
       allow_all: true
 ```

### Running multiple bots

You can run all configured Telegram bots simultaneously:

```bash
flavia --telegram
```

Or run a specific bot by name:

```bash
flavia --telegram research-bot
flavia --telegram public-bot
```

All bots run concurrently in the same process, each with independent:
- Bot token and Telegram API connection
- Agent configuration (default_agent, allowed_agents)
- User access control list
- Per-user conversation state and agent switch history

Press Ctrl+C to stop all running bots gracefully.

 ## Bot commands

| Command | Description |
|---------|-------------|
| `/start` | Show welcome message and your Telegram user/chat IDs |
| `/help` | Show all available commands |
| `/whoami` | Show your user ID and chat ID |
| `/reset` | Reset your conversation context (keeps current agent) |
| `/compact` | Summarize and compact the conversation context |
| `/agents` | List available agents for this bot |
| `/agent <name>` | Switch to a different agent (resets conversation history) |

### Agent switching examples

```
/agents
# Available agents:
# - main (active)
# - researcher

/agent researcher
# Switched to agent 'researcher'. Conversation has been reset.

/agent secret
# Agent 'secret' is not allowed for this bot. Allowed: main, researcher

/agent ghost
# Unknown agent 'ghost'. Available: main, researcher
```

### `allowed_agents`

Controls which agents a bot's users can switch to via `/agent <name>`:

- `all` (default, or omit the field): no restriction
- `[main, researcher]`: only those agent names are permitted

### Access control semantics (`access`)

- `allow_all: true`: public bot
- `allow_all: false` + `allowed_users: [..]`: only listed users
- `allow_all: false` + `allowed_users: []`: deny all users (safe default if explicitly set)
- Omit `allowed_users`: legacy env whitelist rules may still apply for backward compatibility

### Backward compatibility

If `bots.yaml` is absent or has `bots: {}`, flavIA falls back to the legacy environment variables:

```bash
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHI...
TELEGRAM_ALLOWED_USER_IDS=123456789,987654321
TELEGRAM_ALLOW_ALL_USERS=true
```

Existing setups continue to work without any changes.

## Manual configuration (legacy)

In `.flavia/.env`:

```bash
# Bot token (required)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHI...

# Option 1: restrict to specific users (recommended)
TELEGRAM_ALLOWED_USER_IDS=123456789,987654321

# Option 2: allow anyone (use with caution)
TELEGRAM_ALLOW_ALL_USERS=true
```

## Starting the bot

```bash
flavia --telegram
```

If the bot is not yet configured, the wizard is offered automatically when running in an interactive terminal.

## How it works

- Each Telegram user gets their own agent instance with an independent conversation
- Access control is verified by user ID
- The bot uses the same agent configuration (`.flavia/agents.yaml`) and providers from the folder where it was started
- The session persists as long as the process is running
- Each bot reply includes a context usage footer, for example:
  - `📊 Context: 12,450/128,000 (9.7%)`

## Dependency installation

The Telegram interface requires the `python-telegram-bot` package:

```bash
.venv/bin/pip install python-telegram-bot==22.6
```

Or via extras:

```bash
.venv/bin/pip install -e ".[telegram]"
```
